"""One-time repair: say which question set each already recorded run measured.

Runs written before the ledger carried a dataset fingerprint are stamped from evidence rather
than assumption: the ids of the tasks inside their steps. The film suite asks about a01, a02…,
the generated exam about g01, g02…. A run whose steps cannot be read is left untouched and
reported, because guessing is the thing this project exists to avoid.

    python scripts/stamp_dataset_on_runs.py --dry-run
    python scripts/stamp_dataset_on_runs.py
"""

from __future__ import annotations

import argparse

from mh import store, tasks

GENERATED_PREFIX = "g"


def identity_for(db, run: dict) -> tuple[dict | None, str]:
    """The question set a run measured, decided from the task ids in its steps."""
    steps = list(db.steps.find({"run_id": run.get("run_id")}))
    if not steps:
        return None, "no steps to read"
    ids = [str(step.get("task_id", "")) for step in steps]
    if not any(ids):
        return None, "steps carry no task ids"
    if all(task_id.startswith(GENERATED_PREFIX) for task_id in ids):
        return {"key": f"generated:{len(ids)}", "questions": len(ids), "name": "generated"}, ""
    return {"key": tasks.pack_key(), "questions": len(ids), "name": "sample_mflix"}, ""


def main() -> int:
    """Stamp every unstamped run, reporting the ones that could not be decided."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show what would be stamped")
    args = parser.parse_args()

    db = store.get_db()
    unstamped = list(db.runs.find({"dataset": {"$exists": False}}))
    print(f"{len(unstamped)} run(s) without a dataset stamp; the film suite key is {tasks.pack_key()}")

    stamped, undecided = 0, []
    for run in unstamped:
        identity, problem = identity_for(db, run)
        if identity is None:
            undecided.append((run.get("run_id"), problem))
            continue
        action = "would stamp" if args.dry_run else "stamped"
        print(f"  {action} {run.get('run_id')} · {run.get('suite')} {run.get('passed')}/{run.get('total')} · {identity['name']}")
        if not args.dry_run:
            db.runs.update_one({"_id": run["_id"]}, {"$set": {"dataset": identity}})
        stamped += 1

    for run_id, problem in undecided:
        print(f"  left alone: {run_id} · {problem}")
    print(f"{stamped} stamped, {len(undecided)} left alone")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
