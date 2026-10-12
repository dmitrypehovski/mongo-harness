"""Bring the live Atlas Vector Search index in line with what the code now expects.

The index was created before lessons carried a dataset fingerprint, so it does not know the
``dataset.key`` field and a filtered ``$vectorSearch`` against it would be refused. This updates
the definition in place and waits until Atlas reports the index queryable again.

    python scripts/update_vector_index.py --dry-run
    python scripts/update_vector_index.py
"""

from __future__ import annotations

import argparse
import time

from mh import store

COLLECTION = "lessons"


def index_state(collection, name: str) -> dict | None:
    """The named search index as Atlas currently holds it, or None."""
    for index in collection.list_search_indexes():
        if index.get("name") == name:
            return index
    return None


def main() -> int:
    """Update the index definition and wait for it to become queryable."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="only report the difference")
    parser.add_argument("--wait", type=int, default=300, help="seconds to wait for readiness")
    args = parser.parse_args()

    db = store.get_db()
    spec = store.vector_index_spec()
    collection = db[COLLECTION]

    before = index_state(collection, spec["name"])
    if before is None:
        print(f"index {spec['name']} does not exist yet — run `mh init` or ensure_vector_index()")
        return 1

    current = before.get("latestDefinition") or {}
    problems = store.index_differences(current, spec["definition"])
    print(f"index {spec['name']}: state {before.get('status')}")
    print(f"  now:    {store.index_shape(current)}")
    print(f"  wanted: {store.index_shape(spec['definition'])}")
    if not problems:
        print("already in line — nothing to do")
        return 0
    for problem in problems:
        print(f"  differs · {problem}")
    if args.dry_run:
        print("would update the definition")
        return 0

    db.command(
        {
            "updateSearchIndex": COLLECTION,
            "name": spec["name"],
            "definition": spec["definition"],
        }
    )
    print("update submitted; waiting for Atlas to finish rebuilding")

    deadline = time.time() + args.wait
    while time.time() < deadline:
        state = index_state(collection, spec["name"])
        status = (state or {}).get("status")
        if status == "READY":
            latest = (state or {}).get("latestDefinition") or {}
            remaining = store.index_differences(latest, spec["definition"])
            print(f"  READY · {store.index_shape(latest)}")
            for problem in remaining:
                print(f"  still differs · {problem}")
            print("in line" if not remaining else "the index still does not match")
            return 0 if not remaining else 1
        print(f"  status {status} …")
        time.sleep(15)
    print("timed out waiting; the index may still finish on its own")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
