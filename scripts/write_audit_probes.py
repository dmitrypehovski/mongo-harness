"""Give an existing pack an instrument audit of its own data.

A pack written before probes existed can be audited as it stands: the probes are derived from what
is actually in its collections — an ObjectId field gets the spelling probe, a date field gets the
date probe, and the first string field gets the equality probe. Nothing here is specific to any
dataset, which is the point: the audit checks the sandbox, and the sandbox is the same everywhere.

    python scripts/write_audit_probes.py --dataset datasets/theaters.json --dry-run
    python scripts/write_audit_probes.py --dataset datasets/theaters.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mh import datasets, scaffold, scorer


def main() -> int:
    """Derive probes for a pack's collections and write them into the pack."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="the pack to give an audit")
    parser.add_argument("--database", help="override the database the pack names")
    parser.add_argument("--dry-run", action="store_true", help="only show what would be written")
    args = parser.parse_args()

    path = Path(args.dataset)
    pack = datasets.load(path)
    database = args.database or pack.database
    if not database:
        print(f"{path}: the pack names no database, so no probe can be anchored")
        return 1

    collections = pack.summary()["collections"]
    db = scorer.connect().get_database(database)
    print(f"{path.name} · database {database} · collections {collections}")

    probes = scaffold.audit_probes_for(db, collections)
    for probe in probes:
        rendered = probe["sugar"].replace("{{value}}", "…")
        print(f"  would add: {probe['name']}\n             {rendered}")

    if not probes:
        print("nothing could be anchored; the pack is left as it is")
        return 1
    if args.dry_run:
        print(f"would write {len(probes)} probe(s) into {path}")
        return 0

    pack.audit_probes = probes
    datasets.write(pack, path)
    written = datasets.load(path)
    print(f"wrote {len(written.audit_probes)} probe(s) into {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
