#!/usr/bin/env bash
# A mechanism check with outcomes that do not depend on the model.
#
# The two guards in this harness are supposed to hold whatever the language model
# does. This script proves both on questions whose outcome is decided before any
# model call: a question that needs a tool the harness is not allowed to use is
# refused by the harness itself, every time.
#
#   1. a human takes the aggregation tool away and the loss is measured
#   2. the harness asks for it back  -> the envelope refuses
#   3. it tries $where instead       -> the envelope refuses again
#
# Usage:  bash demo/gate_proof.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY="${PY:-.venv/bin/python}"
export MONGODB_URI="${MONGODB_URI:-mongodb://localhost:27017}"
export MH_DB="${MH_DB:-harness}"
export MH_MFLIX_DB="${MH_MFLIX_DB:-sample_mflix}"
export MH_WORKERS="${MH_WORKERS:-8}"
export MH_HOLDOUT_REPEATS="${MH_HOLDOUT_REPEATS:-2}"
export MH_TEMPERATURE="${MH_TEMPERATURE:-0}"

banner() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

banner "a clean ledger"
docker exec mh-mongo mongosh --quiet "$MH_DB" --eval 'db.dropDatabase()' >/dev/null
$PY -m mh.cli init | tail -1

banner "a human takes the aggregation tool away (this is not a harness decision)"
docker exec mh-mongo mongosh --quiet "$MH_DB" --eval '
  const result = db.versions.updateOne({ version_id: 0 }, { $set: { "config.tools": ["find"] } });
  print("versions updated: " + result.modifiedCount);
'
docker exec mh-mongo mongosh --quiet "$MH_DB" --eval '
  print("tools now: " + JSON.stringify(db.versions.findOne({ version_id: 0 }).config.tools));
'

banner "measure it: questions that need the missing tool"
$PY -m mh.cli run | tail -2

banner "what the ledger says about those failures"
docker exec mh-mongo mongosh --quiet "$MH_DB" --eval '
  db.steps.aggregate([
    { $match: { passed: false, status: { $ne: "" } } },
    { $group: { _id: "$status", questions: { $addToSet: "$task_id" } } },
    { $project: { _id: 1, questions: { $size: "$questions" } } },
    { $sort: { questions: -1 } },
  ]).forEach((row) => print("  " + row.questions + " questions: " + row._id));
'

banner "it asks for the tool back, and for a way round it"
$PY -m mh.cli generation --forced demo/proposals_tools.json | grep -E "proposal|decision|reason" || true

banner "the ledger, as it will be read on stage"
$PY -m mh.cli edits | tail -30

banner "put the tool back (again: a human decision, not a harness one)"
docker exec mh-mongo mongosh --quiet "$MH_DB" --eval '
  db.versions.updateOne({ version_id: 0 }, { $set: { "config.tools": ["find", "aggregate", "count"] } });
' >/dev/null
$PY -m mh.cli run | tail -2
