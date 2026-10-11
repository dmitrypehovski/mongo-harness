"""Export the self-written exam for the project page, from files rather than by hand.

    python scripts/export_exam.py --report datasets/theaters.report.json \
        --measure measure.txt --out docs/exam.json

Every number in the output is read from the scaffolding report and from the captured output of
``mh.cli run`` on that pack. Nothing is typed in, so the page cannot drift from what the
harness actually did.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MEASURE = re.compile(r"^(train|holdout)\s+(\d+)/(\d+)\s*=\s*([\d.]+)%", re.MULTILINE)


def parse_measure(text: str) -> dict:
    """The measured percentages, read out of the run's own output."""
    return {
        split: {"passed": int(passed), "total": int(total), "rate": float(rate) / 100}
        for split, passed, total, rate in MEASURE.findall(text)
    }


def main() -> int:
    """Write the exam export."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="report written by scaffold-dataset")
    parser.add_argument("--measure", help="captured output of mh.cli run on that pack")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    export = {
        "database": report["summary"]["database"],
        "collections": report["summary"]["collections"],
        "summary": report["summary"],
        "kept": report["kept"],
        "dropped": report["dropped"],
        "rates": parse_measure(Path(args.measure).read_text(encoding="utf-8"))
        if args.measure
        else {},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(export, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {args.out}: {export['summary']['kept']} kept, "
        f"{export['summary']['dropped']} refused, rates {export['rates']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
