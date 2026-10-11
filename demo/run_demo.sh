#!/usr/bin/env bash
# The whole story, in the order it should be shown:
#
#   1. the questions and their reference answers are sound   (seconds)
#   2. the starting harness is weak                          (about 30 seconds)
#   3. the harness proposes changes to itself, the gate decides   (a few minutes)
#   4. the ledger, including the refusals
#   5. rolling the promotion back
#
# Usage:  bash demo/run_demo.sh            (against MONGODB_URI from .env)
#         FRESH=1 bash demo/run_demo.sh    (drop the ledger first, for a clean recording)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export MONGODB_URI="${MONGODB_URI:-mongodb://localhost:27017}"
export MH_DB="${MH_DB:-harness}"
export MH_MFLIX_DB="${MH_MFLIX_DB:-sample_mflix}"
export MH_WORKERS="${MH_WORKERS:-8}"
export MH_HOLDOUT_REPEATS="${MH_HOLDOUT_REPEATS:-2}"

PY=".venv/bin/python"

banner() {
  echo
  echo "==============================================================================="
  echo "  $1"
  echo "==============================================================================="
}

if [[ "${FRESH:-0}" == "1" ]]; then
  banner "0. clearing the ledger so the run starts from nothing"
  "$PY" - <<'PY'
import os
from mh import store

database = store.get_db()
for name in ("versions", "runs", "steps", "edits", "lessons"):
    database[name].delete_many({})
print("  ledger cleared")
PY
fi

banner "1. the questions, and proof that the reference answers are stable"
"$PY" scripts/check_tasks.py --once | tail -6

banner "2. the starting harness, measured on questions nobody tuned it for"
"$PY" -m mh.cli init >/dev/null
"$PY" -m mh.cli run

banner "3. the harness proposes changes to itself; the gate decides"
"$PY" -m mh.cli generation --forced demo/proposals.json

banner "4. the ledger: every proposal, its evidence and the reason for the decision"
"$PY" -m mh.cli edits

banner "5. undoing the promotion"
"$PY" -m mh.cli rollback

banner "6. where the harness stands now"
"$PY" -m mh.cli status

echo
echo "done."
