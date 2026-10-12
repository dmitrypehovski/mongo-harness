"""The loop: run the harness, let it propose changes to itself, let the gate decide.

One *generation* is:

1. the current version answers the selection set (``train``);
2. it proposes several new versions of itself, with reasons;
3. every proposal is checked against the envelope, then measured on the selection
   set and on the verification set (``holdout``);
4. the gate accepts or refuses each one, and the decision is written to the ledger
   together with the evidence and the reason.

The loop never promotes a version by itself. Promotion happens only where
:mod:`mh.gate` says so.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from mh import agent, gate, scorer, store, tasks

log = logging.getLogger(__name__)

CACHE_DIR = Path(os.environ.get("MH_CACHE_DIR", ".cache"))
GENESIS_LESSON = "genesis: the starting configuration, taken from the MongoDB query-writing guidance"


def _now() -> datetime:
    """Current UTC time."""
    return datetime.now(timezone.utc)


def fingerprint(config: dict) -> str:
    """Stable fingerprint of a version, used to spot duplicates."""
    payload = json.dumps({key: config.get(key) for key in sorted(agent.EDITABLE_KEYS)}, sort_keys=True)
    import hashlib

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def init_db(db=None) -> dict:
    """Prepare collections and make sure a starting version exists."""
    schema = store.ensure_schema(db)
    if store.latest_version() is None:
        config = dict(agent.GENESIS)
        store.record_version(
            {
                "version_id": 0,
                "config": config,
                "parent": None,
                "created_at": _now(),
                "fingerprint": fingerprint(config),
                "promoted_by": "genesis",
                "note": GENESIS_LESSON,
            }
        )
        log.info("recorded the starting version")
    return schema


def order_sensitive(task: dict) -> bool:
    """Whether the task's answer is a sequence rather than a set."""
    parsed = scorer.parse_mql(task["reference"])
    if any(name == "sort" for name, _ in parsed.chain):
        return True
    return scorer._sorts(parsed)


def reset_dataset_caches() -> None:
    """Forget the reference rows and answers computed for the previous question set."""
    _EXPECTED_ROWS.clear()


def expected_answers(db, refresh: bool = False) -> dict[str, dict]:
    """Reference answer for every task, cached on disk.

    The reference answers depend only on the data, not on the harness, so they are
    computed once and reused; nothing the harness does can influence them. The
    rows themselves are kept in memory for the current process and compared with
    :func:`mh.scorer.compare`.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"expected-{tasks.pack_key()}.json"
    if cache_file.exists() and not refresh:
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if len(cached) == len(tasks.TASKS) and all("drop_id" in value for value in cached.values()):
            expected_rows(db)  # warm the in-process reference rows
            return cached

    answers: dict[str, dict] = {}
    for task in tasks.TASKS:
        parsed = scorer.parse_mql(task["reference"])
        execution = scorer.execute(db, parsed, ["find", "aggregate", "count"])
        if not execution.ok:
            raise RuntimeError(f"reference query for {task['id']} failed: {execution.error}")
        _EXPECTED_ROWS[task["id"]] = execution.rows
        answers[task["id"]] = {
            "digest": execution.digest,
            "rows": len(execution.rows),
            "order_sensitive": order_sensitive(task),
            "drop_id": parsed.method in ("find", "countDocuments"),
        }
    cache_file.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")
    return answers


#: Reference rows for this process, keyed by task id.
_EXPECTED_ROWS: dict[str, list] = {}


def expected_rows(db, task: dict | None = None) -> list | dict:
    """Reference rows for one task, or for every task, computed once per process."""
    if task is None:
        for every in tasks.TASKS:
            expected_rows(db, every)
        return _EXPECTED_ROWS
    if task["id"] not in _EXPECTED_ROWS:
        parsed = scorer.parse_mql(task["reference"])
        execution = scorer.execute(db, parsed, ["find", "aggregate", "count"])
        if not execution.ok:
            raise RuntimeError(f"reference query for {task['id']} failed: {execution.error}")
        _EXPECTED_ROWS[task["id"]] = execution.rows
    return _EXPECTED_ROWS[task["id"]]


def lessons_for(task: dict, config: dict, db) -> list[dict]:
    """Retrieve memories of similar past failures, as configured."""
    count = int(config.get("retrieve_k") or 0)
    if count <= 0:
        return []
    try:
        vector = agent.embed.embed_one(task["question"])
        return store.vector_search(vector, k=count, dataset_key=tasks.pack_scope())
    except Exception as exc:
        log.warning("memory retrieval failed: %s", exc)
        return []


def evaluate(
    config: dict,
    split: str,
    db,
    answers: dict[str, dict],
    version_id: int,
    run_id: str | None = None,
    bank: list[dict] | None = None,
    record: bool = True,
    repeats: int = 1,
) -> dict:
    """Run one harness version over one split and record everything.

    ``repeats`` above one runs the whole split again: a single run of twenty-five
    questions cannot tell a real improvement from the model having a good day, so
    the verification set is measured more than once.
    """
    suite = tasks.by_split(split)
    run_id = run_id or f"v{version_id}-{split}-{int(time.time())}"

    def work_and_score(task: dict) -> dict:
        lessons = lessons_for(task, config, db)
        result = agent.solve(config, task, db, lessons, bank=bank)
        answer = answers[task["id"]]
        if result.get("status") == "ok":
            matched, how = scorer.compare(
                expected_rows(db, task),
                result.get("rows_full") or [],
                order_sensitive=answer["order_sensitive"],
                drop_id=answer["drop_id"],
            )
            result["passed"] = bool(matched)
            result["match"] = how
            result["reason"] = (
                ""
                if matched
                else "the query ran but returned different rows than the reference answer"
            )
        else:
            result["reason"] = result.get("reason") or result.get("error") or "the query did not run"
        result.pop("rows_full", None)
        return result

    repeats = max(1, repeats)
    gathered: list[dict] = []
    for repeat in range(repeats):
        attempt_id = run_id if repeats == 1 else f"{run_id}-r{repeat + 1}"
        started = _now()
        attempt = agent.fan_out(work_and_score, suite)
        finished = _now()
        for result in attempt:
            result["repeat"] = repeat + 1
        gathered.extend(attempt)
        if record:
            store.record_run(
                {
                    "run_id": attempt_id,
                    "version_id": version_id,
                    "suite": split,
                    "started_at": started,
                    "finished_at": finished,
                    "total": len(attempt),
                    "passed": sum(1 for result in attempt if result.get("passed")),
                    "rate": round(gate.rate(attempt), 4),
                    "notes": f"generation run of version {version_id}, repeat {repeat + 1} of {repeats}",
                }
            )
            for result in attempt:
                store.record_step(
                    {
                        "run_id": attempt_id,
                        "task_id": result["task_id"],
                        "question": result["question"][:300],
                        "db": "sample_mflix",
                        "collection": "",
                        "generated_query": str(result.get("query", ""))[:2000],
                        "executed_ok": result.get("status") == "ok",
                        "status": str(result.get("status", "")),
                        "result_digest": result.get("digest", ""),
                        "expected_digest": answers[result["task_id"]]["digest"],
                        "passed": bool(result.get("passed")),
                        "latency_ms": int(result.get("latency_ms") or 0),
                        "error": str(result.get("error", ""))[:400],
                        "replayed": bool(result.get("replayed")),
                        "repeat": repeat + 1,
                    }
                )
            store_lessons(attempt, answers, db)

    return {
        "run_id": run_id,
        "version_id": version_id,
        "split": split,
        "total": len(gathered),
        "passed": sum(1 for result in gathered if result.get("passed")),
        "rate": round(gate.rate(gathered), 4),
        "repeats": repeats,
        "results": gathered,
    }


def store_lessons(results: list[dict], answers: dict[str, dict], db) -> int:
    """Write a memory entry for every question this version failed."""
    stored = 0
    for result in results:
        if result.get("passed"):
            continue
        reason = result.get("reason") or result.get("status") or "unknown"
        text = f"{result['question']}\nwhy it failed: {reason}"
        try:
            vector = agent.embed.embed_one(text)
        except Exception as exc:
            log.warning("could not embed a lesson: %s", exc)
            continue
        store.record_lesson(
            {
                "task_id": result["task_id"],
                "question": result["question"][:300],
                "reason": str(reason)[:400],
                "failed_query": str(result.get("query", ""))[:1500],
                "expected_digest": answers[result["task_id"]]["digest"],
                "got_digest": result.get("digest", ""),
                "embedding": vector,
                "created_at": _now(),
            }
        )
        stored += 1
    return stored


def bank_from_db(db, version_id: int) -> list[dict]:
    """Rebuild the memory of working answers from the ledger itself."""
    database = store.get_db()
    run_ids = [
        run["run_id"]
        for run in database.runs.find({"version_id": version_id, "suite": "train"}, {"run_id": 1})
    ]
    if not run_ids:
        return []
    entries = []
    for step in database.steps.find(
        {"run_id": {"$in": run_ids}, "passed": True}, {"task_id": 1, "question": 1, "generated_query": 1}
    ):
        entries.append(
            {
                "task_id": step.get("task_id"),
                "question": step.get("question", ""),
                "query": step.get("generated_query", ""),
            }
        )
    return entries


def run_generation(
    db,
    answers: dict[str, dict],
    want: int = 4,
    forced: list[dict] | None = None,
    max_holdout_runs: int = 6,
) -> dict:
    """One full cycle of propose, measure and decide."""
    version = store.latest_version()
    if version is None:
        raise RuntimeError("no version in the database: run init_db() first")
    current = version["config"]
    version_id = int(version["version_id"])
    repeats = max(1, int(os.environ.get("MH_HOLDOUT_REPEATS", "2")))

    incumbent_train = evaluate(current, "train", db, answers, version_id)
    incumbent_holdout = evaluate(current, "holdout", db, answers, version_id, repeats=repeats)

    bank = bank_from_db(db, version_id) if current.get("replay_train_answers") else []

    if forced:
        proposals = [dict(item) for item in forced]
    else:
        proposals = agent.propose_edits(
            current, incumbent_train["results"], incumbent_holdout["rate"], incumbent_train["rate"],
            store.vector_search(agent.embed.embed_one("questions the harness answers wrongly"), k=5)
            if int(current.get("retrieve_k") or 0) > 0
            else [],
            want=want,
        )
    log.info("generation %s: %s proposal(s)", version_id, len(proposals))

    ledger = []
    for index, proposal in enumerate(proposals):
        candidate_config = dict(current)
        candidate_config.update(
            {key: value for key, value in proposal.get("config", {}).items() if key in agent.EDITABLE_KEYS}
        )
        allowed, reason = gate.envelope_check(current, proposal.get("config", {}))
        entry = {
            "strategy": proposal.get("strategy", f"proposal {index + 1}"),
            "rationale": proposal.get("reasoning", ""),
            "proposal": {key: candidate_config[key] for key in agent.EDITABLE_KEYS if candidate_config.get(key) != current.get(key)},
            "decision": "",
            "reason": "",
            "evidence": {},
        }
        if not allowed:
            entry.update({"decision": "rejected_envelope", "reason": reason})
            ledger.append(entry)
            log.info("proposal %s refused by the envelope: %s", index + 1, reason)
            continue

        candidate_id = version_id + 1 + index
        if len([item for item in ledger if item["decision"] != "rejected_envelope"]) >= max_holdout_runs:
            entry.update({"decision": "rejected_insignificant", "reason": "the evaluation budget for this generation is used up"})
            ledger.append(entry)
            continue

        candidate_train = evaluate(candidate_config, "train", db, answers, candidate_id)
        candidate_holdout = evaluate(candidate_config, "holdout", db, answers, candidate_id, repeats=repeats)
        decision, reason, evidence = gate.decide(
            incumbent_holdout["results"], candidate_holdout["results"],
            incumbent_train["results"], candidate_train["results"],
        )
        entry.update({"decision": decision, "reason": reason, "evidence": evidence})
        entry["candidate_config"] = candidate_config
        entry["holdout_rate"] = candidate_holdout["rate"]
        entry["train_rate"] = candidate_train["rate"]
        ledger.append(entry)
        log.info("proposal %s (%s): %s", index + 1, entry["strategy"], decision)

    promoted = [item for item in ledger if item["decision"] == "promoted"]
    winner = None
    if promoted:
        winner = max(promoted, key=lambda item: item.get("holdout_rate", 0.0))
        new_version_id = version_id + 1
        store.record_version(
            {
                "version_id": new_version_id,
                "config": winner["candidate_config"],
                "parent": version_id,
                "created_at": _now(),
                "fingerprint": fingerprint(winner["candidate_config"]),
                "promoted_by": "gate",
                "note": winner["strategy"],
            }
        )
        winner["promoted_version"] = new_version_id

    for item in ledger:
        store.record_edit(
            {
                "version_from": version_id,
                "version_to": item.get("promoted_version", version_id + 1),
                "proposal": item["proposal"],
                "rationale": item["rationale"] or item["strategy"],
                "strategy": item["strategy"],
                "evidence": item.get("evidence", {}),
                "decision": item["decision"],
                "reason": item["reason"],
                "created_at": _now(),
                "rolled_back": False,
            }
        )

    return {
        "version_id": version_id,
        "incumbent": {
            "train_rate": incumbent_train["rate"],
            "holdout_rate": incumbent_holdout["rate"],
            "train_passed": incumbent_train["passed"],
            "train_total": incumbent_train["total"],
            "holdout_passed": incumbent_holdout["passed"],
            "holdout_total": len(tasks.by_split("holdout")),
            "repeats": repeats,
        },
        "proposals": ledger,
        "promoted": winner["promoted_version"] if winner else None,
        "promoted_strategy": winner["strategy"] if winner else "",
    }


def rollback(db, steps: int = 1) -> dict:
    """Undo the last promotion by recording the earlier version as current again."""
    database = store.get_db()
    versions = list(database.versions.find({}).sort("version_id", -1).limit(steps + 1))
    if len(versions) < 2:
        return {"ok": False, "reason": "there is no promotion to undo"}

    current = versions[0]
    target = versions[steps]
    for edit in database.edits.find({"version_to": current["version_id"], "decision": "promoted"}):
        database.edits.update_one({"_id": edit["_id"]}, {"$set": {"rolled_back": True}})
    new_version_id = int(current["version_id"]) + 1
    store.record_version(
        {
            "version_id": new_version_id,
            "config": target["config"],
            "parent": int(current["version_id"]),
            "created_at": _now(),
            "fingerprint": fingerprint(target["config"]),
            "promoted_by": "manual",
            "note": f"rollback to version {target['version_id']}",
        }
    )
    return {
        "ok": True,
        "rolled_back_from": int(current["version_id"]),
        "restored": int(target["version_id"]),
        "now_current": new_version_id,
    }
