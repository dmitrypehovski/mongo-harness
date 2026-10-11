#!/usr/bin/env bash
# Load the sample_mflix dataset into a local MongoDB (docker container), plus the
# two indexes the questions rely on. Same data the Atlas path restores, so the
# harness behaves the same in both places.
#
# Usage:  bash scripts/load_mflix_local.sh
#
#   CONTAINER   container name (default mh-mongo, started if missing)
#   PORT        host port to publish (default 27017)
#   ARCHIVE     where the archive is kept (default data/sample_mflix.archive)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CONTAINER="${CONTAINER:-mh-mongo}"
PORT="${PORT:-27017}"
ARCHIVE="${ARCHIVE:-data/sample_mflix.archive}"
DB="${MH_MFLIX_DB:-sample_mflix}"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "==> downloading the sample_mflix archive (about 124 MB)"
  mkdir -p "$(dirname "$ARCHIVE")"
  curl -fL --progress-bar -o "$ARCHIVE" \
    https://atlas-education.s3.amazonaws.com/sample_mflix.archive
else
  echo "==> reusing $ARCHIVE"
fi

if docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "==> $CONTAINER already exists"
else
  echo "==> starting $CONTAINER on port $PORT"
  docker run -d --name "$CONTAINER" -p "$PORT:27017" mongo:7 >/dev/null
  sleep 6
fi

echo "==> restoring into the container"
docker cp "$ARCHIVE" "$CONTAINER:/tmp/sample_mflix.archive"
docker exec "$CONTAINER" mongorestore --quiet --archive=/tmp/sample_mflix.archive \
  --nsInclude="${DB}.*" --drop

# comments.movie_id is what the $lookup questions join on; movies.year carries most
# of the filters. Without these the join questions take minutes instead of seconds.
echo "==> creating the indexes the questions rely on"
docker exec "$CONTAINER" mongosh --quiet "$DB" --eval '
  db.comments.createIndex({ movie_id: 1 }, { name: "movie_id_1" });
  db.movies.createIndex({ year: 1 }, { name: "year_1" });
'

echo "==> what is loaded now"
docker exec "$CONTAINER" mongosh --quiet "$DB" --eval '
  db.getCollectionNames().sort().forEach((name) => print("  " + name + ": " + db[name].countDocuments()));
'
