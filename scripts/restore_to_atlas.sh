#!/usr/bin/env bash
# Load everything an Atlas deployment needs:
#   1. the sample_mflix dataset, restored with mongorestore from inside a container
#      (the archive is the official Atlas sample dump);
#   2. the harness database: collections, MQL indexes and the Atlas Vector Search
#      index used by the memory of past failures.
#
# Usage:
#   export MONGODB_URI='mongodb+srv://...'      # never echoed by this script
#   bash scripts/restore_to_atlas.sh
#
# Notes:
#   * the machine running this must be allowed in Atlas -> Network Access;
#   * the dataset needs a few hundred MB of traffic and a couple of minutes;
#   * restoring the same archive twice is safe: collections are replaced.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -z "${MONGODB_URI:-}" ]]; then
  echo "MONGODB_URI is not set. Export the Atlas connection string first." >&2
  exit 1
fi

if [[ "$MONGODB_URI" != mongodb+srv://* && "${ALLOW_LOCAL:-0}" != "1" ]]; then
  echo "MONGODB_URI does not look like an Atlas string (expected mongodb+srv://)." >&2
  echo "Set ALLOW_LOCAL=1 if you really mean a local server." >&2
  exit 1
fi

ARCHIVE="${MH_ARCHIVE:-data/sample_mflix.archive}"
CONTAINER="${MH_CONTAINER:-mh-mongo}"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "==> downloading the sample_mflix archive (around 124 MB)"
  mkdir -p "$(dirname "$ARCHIVE")"
  curl -fL --progress-bar -o "$ARCHIVE" \
    https://atlas-education.s3.amazonaws.com/sample_mflix.archive
else
  echo "==> reusing $ARCHIVE"
fi

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "==> starting a helper container"
  docker run -d --name "$CONTAINER" mongo:7 >/dev/null
  sleep 6
fi

echo "==> copying the archive into the helper container"
docker cp "$ARCHIVE" "$CONTAINER:/tmp/sample_mflix.archive"

# The URI travels through the environment, never through the command line, so it
# does not show up in a process listing.
echo "==> restoring sample_mflix into the target cluster"
docker exec -e MONGODB_URI="$MONGODB_URI" "$CONTAINER" \
  sh -lc 'mongorestore --quiet --uri "$MONGODB_URI" --archive=/tmp/sample_mflix.archive \
          --nsInclude="sample_mflix.*" --drop' 2>&1 | tail -3

echo "==> creating the harness database, its indexes and the vector search index"
.venv/bin/python scripts/init_atlas.py

echo "==> done. What is in the cluster now:"
.venv/bin/python - <<'PY'
import os
from mh import store, scorer

print(store.ok())
database = scorer.connect(os.environ["MONGODB_URI"]).get_database(os.environ.get("MH_MFLIX_DB", "sample_mflix"))
for name in sorted(database.list_collection_names()):
    print(f"  {name}: {database[name].estimated_document_count()} documents")
PY
