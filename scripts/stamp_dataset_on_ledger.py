"""One-time repair: make every already recorded ledger document say which data it belongs to.

Old documents carry no stamp, and the first batch of stamps used the question wording's fingerprint
as the key — which is exactly the thing memory must not be scoped by, since regenerating an exam
would orphan everything learned about the same data. This rewrites those stamps to the data scope,
decided from evidence rather than assumption:

* a **run** is identified by the task ids inside its steps;
* a **lesson** is identified by its own ``task_id``;
* a provenance is matched only when the document's ids are a subset of that pack's ids — the shipped
  film suite for the built-in questions, or one of the packs in ``datasets/`` for the rest.

A document whose owner cannot be decided is left untouched and reported, because guessing is the
thing this project exists to avoid. The recorded ``pack`` fingerprint is only rewritten when it is
certain — the shipped suite never changes — since the exact wording a generated exam used is not
recoverable from the file that produced it.

    python scripts/stamp_dataset_on_ledger.py --dry-run
    python scripts/stamp_dataset_on_ledger.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mh import datasets, store, tasks


def provenance(name: str, database: str | None, question_ids: set[str]) -> dict:
    """The stamp for a question set, with the scope of its data as the key."""
    return {
        "name": name,
        "database": database,
        "ids": question_ids,
        "scope": tasks.pack_scope(),
        "fingerprint": tasks.pack_key(),
        "collections": tasks.pack_collections(),
        "generated": tasks.is_generated(),
    }


def known_provenances(pack_dir: Path) -> list[dict]:
    """Every question set this repository can account for: the shipped suite and each pack on disk."""
    tasks.reset_pack()
    found = [provenance("sample_mflix", tasks.pack_database(), {str(t["id"]) for t in tasks.TASKS})]

    for path in sorted(pack_dir.glob("*.json")):
        if path.name.endswith(".report.json"):
            continue
        try:
            pack = datasets.load(path)
        except Exception as exc:  # noqa: BLE001 - a broken pack must not stop the repair
            print(f"  skipped {path.name}: {exc}")
            continue
        tasks.use_pack(pack.tasks, database=pack.database, name=pack.name or path.stem)
        found.append(
            provenance(
                pack.name or path.stem,
                pack.database,
                {str(t["id"]) for t in pack.tasks},
            )
        )

    tasks.reset_pack()
    return found


def decide(ids: set[str], provenances: list[dict]) -> tuple[dict | None, str]:
    """The provenance whose questions cover these ids, or a reason why none does."""
    if not ids:
        return None, "no task ids to go on"
    matches = [item for item in provenances if ids <= item["ids"]]
    if not matches:
        return None, f"task ids {sorted(ids)[:3]} belong to no known question set"
    # the tightest covering set wins, so a one-collection pack is not swallowed by the film suite
    best = min(matches, key=lambda item: len(item["ids"]))
    stamp = {
        "key": best["scope"],
        "questions": len(ids),
        "name": best["name"],
        "collections": best["collections"],
        "generated": best["generated"],
    }
    if not best["generated"]:
        # certain: the shipped suite is the same every time the repository is checked out
        stamp["pack"] = best["fingerprint"]
    return stamp, ""


def decide_run(ids: set[str], databases: set[str], provenances: list[dict]) -> tuple[dict | None, str]:
    """The provenance of a run: exact question ids first, then the database it actually ran against.

    A run whose exam has been regenerated since cannot be matched by ids, but its steps still record
    the database they executed against. That is weaker evidence, so it is reported as approximate
    rather than passed off as certain.
    """
    stamp, problem = decide(ids, provenances)
    if stamp is not None:
        return stamp, ""
    if not databases:
        return None, problem + ", and its steps name no database"
    overlap = [
        (len(ids & item["ids"]), item)
        for item in provenances
        if item["database"] in databases and len(ids & item["ids"]) >= max(1, len(ids) // 2)
    ]
    if not overlap:
        return None, problem + f", and nothing in {sorted(databases)} overlaps its questions"
    overlap.sort(key=lambda pair: -pair[0])
    if len(overlap) > 1 and overlap[0][0] == overlap[1][0]:
        return None, "two known question sets share as many of its ids"
    shared, best = overlap[0]
    stamp = {
        "key": best["scope"],
        "questions": len(ids),
        "name": best["name"],
        "collections": best["collections"],
        "generated": best["generated"],
    }
    return stamp, f"approximate: same database and {shared} shared question ids — the exam was regenerated"


def stamp_for(collection: str, doc: dict, provenances: list[dict], db) -> tuple[dict | None, str]:
    """The correct stamp for one ledger document, from its own evidence."""
    if collection == "runs":
        steps = list(db.steps.find({"run_id": doc.get("run_id")}))
        if not steps:
            return None, "no steps to read"
        ids = {str(step.get("task_id", "")) for step in steps if step.get("task_id")}
        databases = {str(step["db"]) for step in steps if step.get("db")}
        return decide_run(ids, databases, provenances)
    task_id = str(doc.get("task_id") or "")
    ids = {task_id} if task_id else set()
    return decide(ids, provenances)


def main() -> int:
    """Bring every stamp in the ledger in line with the data it was measured on."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show what would change")
    parser.add_argument(
        "--what",
        default="runs,lessons",
        help="which ledger documents to repair (default: runs,lessons)",
    )
    parser.add_argument("--packs", default="datasets", help="where to look for question packs")
    args = parser.parse_args()
    wanted = {name.strip() for name in args.what.split(",") if name.strip()}

    provenances = known_provenances(Path(args.packs))
    print("known question sets:")
    for item in provenances:
        print(f"  {item['name']:14} scope {item['scope']} · {len(item['ids'])} questions · {item['collections']}")

    db = store.get_db()
    changed, correct, undecided = 0, 0, []
    for collection in ("runs", "lessons"):
        if collection not in wanted:
            continue
        docs = list(db[collection].find({}))
        print(f"\n{collection}: {len(docs)} document(s) in the ledger")
        for doc in docs:
            stamp, problem = stamp_for(collection, doc, provenances, db)
            label = doc.get("run_id") or f"{doc.get('task_id')} · {str(doc.get('question'))[:40]}"
            if stamp is None:
                undecided.append((collection, label, problem))
                continue
            current = doc.get("dataset") or {}
            if {k: current.get(k) for k in stamp} == stamp and current.get("pack") == stamp.get("pack"):
                correct += 1
                continue
            action = "would set" if args.dry_run else "set"
            note = f" · {problem}" if problem else ""
            print(f"  {action} {label} · {stamp['name']} · scope {stamp['key']}{note}")
            if not args.dry_run:
                update = {"dataset.key": stamp["key"], "dataset.questions": stamp["questions"]}
                for field, value in stamp.items():
                    update[f"dataset.{field}"] = value
                db[collection].update_one({"_id": doc["_id"]}, {"$set": update})
            changed += 1

    for collection, label, problem in undecided:
        print(f"  left alone: {collection} {label} · {problem}")
    print(f"\n{changed} rewritten, {correct} already right, {len(undecided)} left alone")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
