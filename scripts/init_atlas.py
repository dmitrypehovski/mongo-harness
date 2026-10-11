#!/usr/bin/env python3
"""Ensure harness schema and attempt Atlas Vector Search index creation.

Prints a readable status report. Never prints the MongoDB URI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running as `python scripts/init_atlas.py` from the repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mh import config  # noqa: E402
from mh import store  # noqa: E402


def main() -> int:
    """Create schema, try vector index, print status; exit 0 on success."""
    status = store.ok()
    print("=== mongo-harness init ===")
    print(f"ok:             {status['ok']}")
    print(f"uri_kind:       {status['uri_kind']}")
    print(f"db:             {status['db']}")
    print(f"server_version: {status['server_version']}")
    print(f"MH_USE_VECTOR:  {int(config.use_vector())}")

    if not status["ok"]:
        print("ERROR: cannot reach MongoDB (check MONGODB_URI)")
        return 1

    schema = store.ensure_schema()
    print("\n--- schema ---")
    print(f"collections: {', '.join(schema['collections'])}")
    for coll, names in schema["indexes"].items():
        print(f"  {coll} indexes: {', '.join(names)}")

    vec = store.ensure_vector_index()
    print("\n--- vector index ---")
    print(f"created: {vec.get('created')}")
    if vec.get("reason"):
        print(f"reason:  {vec['reason']}")
    if vec.get("name"):
        print(f"name:    {vec['name']}")

    if not vec.get("created"):
        spec = store.vector_index_spec()
        print("\nTo create the Atlas Vector Search index by hand, run in mongosh")
        print("(Atlas UI → Search → Create Index also works) with this definition:")
        print(json.dumps(spec, indent=2))
        print(
            "\nExample (Atlas only):\n"
            "  db.lessons.createSearchIndex("
            f"{json.dumps(spec['name'])}, "
            f"{json.dumps(spec['type'])}, "
            f"{json.dumps(spec['definition'])}"
            ")"
        )

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
