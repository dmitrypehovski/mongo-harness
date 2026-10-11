"""Export the numbers the submission video shows, straight out of the live ledger.

Nothing in the video is typed by hand. This script reads the Atlas ledger, runs the
ruler audit in both its clean and fault-injected state, and writes the result to
``video/src/harness-data.json``, which the Remotion composition imports.

    .venv/bin/python scripts/export_video_data.py --out video/src/harness-data.json

Re-run it after any generation and the video follows the ledger.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo import MongoClient  # noqa: E402

from mh import ruler, scorer  # noqa: E402


def _rate(run: dict) -> str:
    """Render a run as '23/32 = 71.9%'."""
    return f"{run['passed']}/{run['total']} = {round(100 * run['rate'], 1)}%"


def collect(uri: str) -> dict:
    """Everything the composition needs, and nothing that was not measured."""
    db = MongoClient(uri)["harness"]

    edits = []
    for doc in db.edits.find({}).sort("created_at", 1):
        evidence = doc.get("evidence") or {}
        edits.append(
            {
                "strategy": doc.get("strategy") or "",
                "decision": doc.get("decision") or "",
                "reason": doc.get("reason") or "",
                "train_before": evidence.get("train_rate_before"),
                "train_after": evidence.get("train_rate_after"),
                "holdout_before": evidence.get("holdout_rate_before"),
                "holdout_after": evidence.get("holdout_rate_after"),
                "p_value": evidence.get("p_value"),
            "gained": evidence.get("only_candidate"),
            "lost": evidence.get("only_incumbent"),
                "repeats": evidence.get("repeats"),
            }
        )

    version = db.versions.find_one({}) or {}
    config = version.get("config") or {}
    rates: dict[str, str] = {}
    for suite in ("train", "holdout"):
        run = db.runs.find_one(
            {"version_id": version.get("version", 0), "suite": suite}, sort=[("finished_at", -1)]
        )
        if run:
            rates[suite] = _rate(run)

    sample_db = ruler.connection()
    clean = ruler.report(ruler.audit(sample_db)).splitlines()

    original = scorer._regex_literals
    try:
        ruler.inject_fault("regex")
        injected = ruler.report(ruler.audit(sample_db)).splitlines()
    finally:
        scorer._regex_literals = original

    return {
        "current": {
            "version": version.get("version", 0),
            "promoted_by": version.get("promoted_by") or "genesis",
            "tools": config.get("tools") or [],
            "rules": len(config.get("rules") or []),
            "train": rates.get("train", ""),
            "holdout": rates.get("holdout", ""),
        },
        "edits": edits,
        "counts": {
            name: db[name].count_documents({})
            for name in ("runs", "steps", "lessons", "edits", "versions")
        },
        "audit": {
            "clean": [line for line in clean if "probe(s)" in line or "instrument agrees" in line],
            "injected": [
                line for line in injected if "probe(s)" in line or "instrument is lying" in line
            ]
            + [line.strip() for line in injected if line.strip().startswith("*")],
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Write the video's data file from the live ledger."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="video/src/harness-data.json",
        help="where to write the JSON the composition imports",
    )
    parser.add_argument(
        "--uri", default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    )
    args = parser.parse_args(argv)

    data = collect(args.uri)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n")

    print(f"wrote {target}")
    print(f"  current version {data['current']['version']}, train {data['current']['train']}")
    print(f"  proposals: {len(data['edits'])}")
    print(f"  ledger: {data['counts']}")
    print(f"  audit clean: {data['audit']['clean'][:2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
