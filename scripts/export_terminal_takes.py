"""Capture real command output for the film, so the terminal in it is not staged.

Every line the video shows running in a shell is produced here, by running the actual
command against the live ledger, and written to ``video/src/terminal-takes.json``. If the
ledger changes, re-running this changes what the film says.

    MONGODB_URI=... python scripts/export_terminal_takes.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "video" / "src" / "terminal-takes.json"

TAKES = [
    ("edits", ["-m", "mh.cli", "edits"]),
    ("audit_clean", ["-m", "mh.cli", "audit-ruler"]),
    ("audit_injected", ["-m", "mh.cli", "audit-ruler", "--inject", "regex"]),
    ("status", ["-m", "mh.cli", "status"]),
]


def main() -> int:
    """Run each command and keep its output verbatim."""
    env = dict(os.environ)
    env.setdefault("MH_TEMPERATURE", "0")
    captured: dict[str, dict] = {}
    for name, argv in TAKES:
        print(f"running {name}: {' '.join(argv)}", flush=True)
        completed = subprocess.run(
            [sys.executable, *argv], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900
        )
        output = completed.stdout
        captured[name] = {
            "command": "python " + " ".join(argv),
            "exit_code": completed.returncode,
            "output": output,
            "lines": [line for line in output.splitlines() if line.strip()],
        }
        print(f"  exit {completed.returncode}, {len(captured[name]['lines'])} lines", flush=True)

    OUT.write_text(json.dumps(captured, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
