#!/usr/bin/env bash
# The stranger's journey: a fresh environment, someone else's data, the installed package.
#
# No Atlas, no films, no repository on the Python path. This is the claim "it works on your data"
# put through a run rather than asserted in a README.
#
#   bash scripts/stranger_journey.sh
#
# Requirements: a local MongoDB on 27017, and an OpenRouter key for the exam generator, either in
# OPENROUTER_API_KEY or in the file OPENROUTER_KEY_FILE names.
set -uo pipefail

WORK="${WORK:-/tmp/harness-stranger-journey}"
WHEEL="${WHEEL:-}"
rm -rf "$WORK"
mkdir -p "$WORK"
cd "$WORK"

export MONGODB_URI="${MONGODB_URI:-mongodb://localhost:27017}"
export MH_DB="cafe_harness"
export MH_MFLIX_DB="cafe"
export MH_TEMPERATURE=0

if [ -z "$WHEEL" ]; then
  echo "set WHEEL to the built wheel, e.g. WHEEL=dist/mongo_harness-0.1.0-py3-none-any.whl"
  exit 2
fi
WHEEL=$(readlink -f "$WHEEL")

echo "=== 1. a fresh environment, installed from the built wheel"
python3 -m venv venv
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q "${WHEEL}[memory]"
./venv/bin/pip show mongo-harness | grep -E "^(Name|Version|License)"
./venv/bin/mh --help 2>&1 | head -3

if ! ./venv/bin/mh scaffold-dataset --help >/dev/null 2>&1; then
  echo "the installed package has no exam generator; stopping"
  exit 1
fi

echo
echo "=== 2. someone else's data: a cafe the harness has never seen"
./venv/bin/python - <<'PY'
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo import MongoClient

db = MongoClient("mongodb://localhost:27017")["cafe"]
db.orders.drop()
db.menu.drop()

menu = [
    {"name": "Flat white", "category": "coffee", "price": 4.2},
    {"name": "Filter", "category": "coffee", "price": 3.6},
    {"name": "Cold brew", "category": "coffee", "price": 4.8},
    {"name": "Croissant", "category": "bakery", "price": 3.1},
    {"name": "Cinnamon bun", "category": "bakery", "price": 3.4},
    {"name": "Cheesecake", "category": "bakery", "price": 5.5},
]
channels = ["counter", "app", "app", "counter", "office"]
start = datetime(2024, 5, 1, 7, 30, tzinfo=timezone.utc)
orders = [
    {
        "_id": ObjectId(),
        "item": menu[index % len(menu)]["name"],
        "category": menu[index % len(menu)]["category"],
        "qty": 1 + (index % 3),
        "price": menu[index % len(menu)]["price"],
        "channel": channels[index % len(channels)],
        "placed": start + timedelta(hours=index * 3),
    }
    for index in range(48)
]
db.menu.insert_many([dict(item) for item in menu])
db.orders.insert_many(orders)
print(f"cafe: {db.orders.count_documents({})} orders, {db.menu.count_documents({})} menu items")
PY
[ $? -ne 0 ] && { echo "could not create the sample data"; exit 1; }

echo
echo "=== 3. the harness writes itself an exam for this database"
./venv/bin/mh scaffold-dataset --database cafe --collections orders,menu --want 8 \
  --out "$WORK/pack.json" --report "$WORK/report.json" 2>&1 | tail -16

echo
echo "=== 4. what the pack contains"
./venv/bin/python - <<PY
import json, pathlib
path = pathlib.Path("$WORK/pack.json")
if not path.exists():
    print("no pack was written")
    raise SystemExit(0)
pack = json.loads(path.read_text())
print(f"name {pack['name']} · database {pack['database']} · {len(pack['tasks'])} questions")
for probe in pack.get("audit_probes", []):
    print(f"  audit probe: {probe['name']} · anchor {probe['anchor']}")
PY

echo
echo "=== 5. init: reference answers computed against this database"
./venv/bin/mh init --dataset "$WORK/pack.json" 2>&1 | tail -6

echo
echo "=== 6. measuring on someone else's data"
./venv/bin/mh run --dataset "$WORK/pack.json" --show-failures 2>&1 | tail -12

echo
echo "=== 7. auditing the instrument with the pack's own probes"
./venv/bin/mh audit-ruler --dataset "$WORK/pack.json" 2>&1 | sed -n '4,16p'

echo
echo "=== 8. memory: its own lessons, separated from any other data"
./venv/bin/mh status 2>&1 | sed -n '/^memory/,/^recent/p' | head -14