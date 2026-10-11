"""The product surface: ask the database in plain language, and review what the agent
wants to change about itself.

Deliberately not a dashboard. Two things a person can do here that a report cannot do:

    ask      one question in plain language, answered against the live sample_mflix
             database, with the query it wrote and whether it agrees with the reference
    review   the gate's last refusal, with the maths behind it, and a written override
             that a human can apply and that lands in MongoDB as a fact

Everything it shows is read from the same ledger the command line writes: this is a
window onto the harness, not a second implementation of it.

    MONGODB_URI=... python -m web.app          # http://127.0.0.1:8080
"""

from __future__ import annotations

import difflib
import json
import os
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from mh import agent, loop, scorer, store, tasks

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("MH_WEB_PORT", "8080"))
HOST = os.environ.get("MH_WEB_HOST", "127.0.0.1")


# --------------------------------------------------------------------- data layer


def database():
    """The sample database the questions are asked against."""
    uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    name = os.environ.get("MH_MFLIX_DB", "sample_mflix")
    return scorer.connect(uri).get_database(name)


def all_tasks() -> list[dict]:
    """Every question in the harness suite, both splits."""
    return list(tasks.by_split("train")) + list(tasks.by_split("holdout"))


def find_task(question: str) -> dict | None:
    """The suite question that matches what the person typed, if any.

    Exact text first. Failing that, the closest suite question above a high similarity
    ratio, so that retyping a question with different punctuation still gets a verdict
    instead of falling through to ad hoc mode.
    """
    wanted = " ".join(question.lower().split())
    suite = all_tasks()
    for task in suite:
        if " ".join(task["question"].lower().split()) == wanted:
            return task
    best, score = None, 0.0
    for task in suite:
        ratio = difflib.SequenceMatcher(
            None, wanted, " ".join(task["question"].lower().split())
        ).ratio()
        if ratio > score:
            best, score = task, ratio
    if best is not None and score >= 0.9:
        best = dict(best)
        best["matched_by"] = f"closest suite question ({score:.2f} similar)"
        return best
    return None


def _iso(value) -> str:
    """Timestamps as plain strings for the browser."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
    return str(value) if value is not None else ""


def state() -> dict:
    """Everything the page needs to draw itself."""
    db = store.get_db()
    version = store.latest_version()
    if version is None:
        return {"error": "no version yet: run `python -m mh.cli init`"}
    version_id = version["version_id"]
    config = version["config"]

    rates = {}
    for split in ("train", "holdout"):
        latest = list(
            db.runs.find({"version_id": version_id, "suite": split}).sort("started_at", -1).limit(1)
        )
        if latest:
            rates[split] = {
                "passed": latest[0]["passed"],
                "total": latest[0]["total"],
                "rate": latest[0]["rate"],
                "at": _iso(latest[0].get("finished_at") or latest[0].get("started_at")),
            }

    edits = []
    for edit in db.edits.find({}).sort("created_at", -1).limit(12):
        evidence = edit.get("evidence") or {}
        edits.append(
            {
                "strategy": edit.get("strategy", ""),
                "decision": edit.get("decision", ""),
                "reason": edit.get("reason", ""),
                "rationale": edit.get("rationale", ""),
                "at": _iso(edit.get("created_at")),
                "evidence": {
                    "train_before": evidence.get("train_rate_before"),
                    "train_after": evidence.get("train_rate_after"),
                    "holdout_before": evidence.get("holdout_rate_before"),
                    "holdout_after": evidence.get("holdout_rate_after"),
                    "p_value": evidence.get("p_value"),
                    "gained": evidence.get("only_candidate"),
                    "lost": evidence.get("only_incumbent"),
                    "repeats": evidence.get("repeats"),
                },
            }
        )

    reviews = list(db.reviews.find({}).sort("created_at", -1).limit(5)) if "reviews" in db.list_collection_names() else []

    return {
        "version": {
            "id": version_id,
            "promoted_by": version.get("promoted_by", ""),
            "rules": len(config.get("rules") or []),
            "tools": config.get("tools") or [],
        },
        "rates": rates,
        "counts": {
            "runs": db.runs.count_documents({}),
            "steps": db.steps.count_documents({}),
            "lessons": db.lessons.count_documents({}),
            "edits": db.edits.count_documents({}),
        },
        "edits": edits,
        "reviews": [
            {
                "decision": review.get("decision", ""),
                "note": review.get("note", ""),
                "strategy": review.get("strategy", ""),
                "at": _iso(review.get("created_at")),
            }
            for review in reviews
        ],
        "questions": [
            {"id": task["id"], "question": task["question"], "split": task.get("split", "")}
            for task in all_tasks()
        ],
    }


def ask(question: str) -> dict:
    """Answer one plain-language question with the current version of the agent."""
    db = database()
    version = store.latest_version()
    config = version["config"]
    answers = loop.expected_answers(db)
    task = find_task(question)

    if task is None:
        # A question outside the suite: still answer it, but say plainly that there is
        # no reference answer to compare against, so nothing here is a measurement.
        task = {
            "id": "free",
            "question": question,
            "split": "free",
            "expected": {},
        }

    lessons = loop.lessons_for(task, config, db)
    started = time.time()
    result = agent.solve(config, task, db, lessons)
    elapsed = round((time.time() - started) * 1000)

    payload = {
        "question": question,
        "matched_by": task.get("matched_by", ""),
        "task_id": task["id"],
        "measured": task["id"] in answers,
        "ms": elapsed,
        "query": result.get("readable_query") or result.get("query") or "",
        "rows": result.get("rows"),
        "status": result.get("status"),
        "error": result.get("error") or "",
        "reason": result.get("reason") or "",
        "passed": None,
        "how": "",
        "reference_rows": [],
        "answer_rows": [],
    }

    if task["id"] in answers and result.get("status") == "ok":
        answer = answers[task["id"]]
        expected = list(loop.expected_rows(db, task))
        matched, how = scorer.compare(
            expected,
            result.get("rows_full") or [],
            order_sensitive=answer["order_sensitive"],
            drop_id=answer["drop_id"],
        )
        payload["passed"] = bool(matched)
        payload["how"] = how
        payload["reference_rows"] = json.loads(json.dumps(expected[:3], default=str))
        payload["answer_rows"] = json.loads(json.dumps((result.get("rows_full") or [])[:3], default=str))

    return payload


def review(decision: str, note: str, strategy: str) -> dict:
    """Record a human decision on the gate's last refusal.

    The gate still decides on its own; this is the human's written override, kept as a
    fact in the same database, with who decided and why.
    """
    db = store.get_db()
    document = {
        "decision": decision,
        "note": note,
        "strategy": strategy,
        "reviewed_by": os.environ.get("MH_REVIEWER", "human"),
        "created_at": datetime.now(timezone.utc),
        "gate_decision": "rejected",
        "version_id": (store.latest_version() or {}).get("version_id"),
    }
    db.reviews.insert_one(document)
    return {"ok": True, "decision": decision, "logged": _iso(document["created_at"])}


# ------------------------------------------------------------------------ server


class Handler(BaseHTTPRequestHandler):
    """A very small JSON API, plus one page."""

    server_version = "harness/1.0"

    def log_message(self, format, *args):  # quieter output
        print(f"{self.address_string()} {format % args}", flush=True)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200) -> None:
        self._send(status, json.dumps(payload, default=str).encode("utf-8"), "application/json")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                html = (ROOT / "index.html").read_bytes()
                self._send(200, html, "text/html; charset=utf-8")
            elif path == "/api/state":
                self._json(state())
            elif path == "/health":
                self._json({"ok": True, "database": store.get_db().name})
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:  # pragma: no cover - surfaced to the page
            traceback.print_exc()
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            body = self._read_json()
            if path == "/api/ask":
                question = (body.get("question") or "").strip()
                if not question:
                    self._json({"error": "empty question"}, 400)
                    return
                self._json(ask(question))
            elif path == "/api/review":
                self._json(
                    review(
                        body.get("decision") or "uphold",
                        (body.get("note") or "").strip(),
                        body.get("strategy") or "",
                    )
                )
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"harness product surface on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
