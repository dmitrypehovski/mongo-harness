#!/usr/bin/env bash
# The instrument check, in three beats. No model is involved in any of them.
#
#   1. the audit as it stands: the sandbox must accept what MongoDB accepts
#   2. the same audit with the historical defect switched back on: it must fail
#   3. the defect removed: it must go quiet again
#
# Beat 2 is the point. A detector that has never reported a defect is
# indistinguishable from a detector that cannot report one.
set -u

cd "$(dirname "$0")/.." || exit 1

PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"

green() { printf '\033[32m%s\033[0m\n' "$1"; }
red() { printf '\033[31m%s\033[0m\n' "$1"; }

echo
echo "### 1. the audit as it stands"
"$PY" -m mh.cli audit-ruler
clean=$?

echo
echo "### 2. the same audit, with the defect that cost us 38 answers switched back on"
"$PY" -m mh.cli audit-ruler --inject regex
injected=$?

echo
echo "### 3. the defect removed again"
"$PY" -m mh.cli audit-ruler >/dev/null
restored=$?

echo
echo "------------------ verdict ------------------"
[ "$clean" -eq 0 ] && green "clean run: no defects" || red "clean run failed unexpectedly"
if [ "$injected" -eq 1 ]; then
  green "injected run: refused, as it must be"
else
  red "THE DETECTOR DID NOT NOTICE THE DEFECT, so it proves nothing"
fi
[ "$restored" -eq 0 ] && green "restored run: no defects" || red "restored run failed"

if [ "$clean" -eq 0 ] && [ "$injected" -eq 1 ] && [ "$restored" -eq 0 ]; then
  exit 0
fi
exit 1
