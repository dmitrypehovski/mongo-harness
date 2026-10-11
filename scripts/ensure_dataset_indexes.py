"""Create the dataset indexes the questions rely on.

The Atlas sample dump arrives with only the default indexes, and eight of the
questions join `movies` with `comments` on `comments.movie_id`. Without that index
the join scans the whole collection and hits the server-side time limit, so the
reference answers cannot even be computed. Local loads and Atlas loads both need
this step, and it is safe to run twice.

Usage:  MONGODB_URI='...' .venv/bin/python scripts/ensure_dataset_indexes.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pymongo import ASCENDING, MongoClient

URI_FILE = Path(os.environ.get("MH_URI_FILE", "/root/.secrets/atlas_uri"))


def connection_string() -> str:
    uri = os.environ.get("MONGODB_URI", "").strip()
    if uri:
        return uri
    if URI_FILE.exists():
        return URI_FILE.read_text().strip()
    sys.exit("no MONGODB_URI and no connection file to read it from")


#: (collection, keys, name) — the join key, and the filter every year question uses.
WANTED = [
    ("comments", [("movie_id", ASCENDING)], "movie_id_1"),
    ("movies", [("year", ASCENDING)], "year_1"),
]


def main() -> None:
    database_name = os.environ.get("MH_MFLIX_DB", "sample_mflix")
    client = MongoClient(connection_string(), serverSelectionTimeoutMS=20000)
    database = client[database_name]
    print(f"database: {database_name}")
    for collection_name, keys, name in WANTED:
        collection = database[collection_name]
        existing = {index["name"] for index in collection.list_indexes()}
        if name in existing:
            print(f"  {collection_name}.{name}: already there")
            continue
        collection.create_index(keys, name=name, background=True)
        print(f"  {collection_name}.{name}: created")
    print("indexes now:")
    for collection_name, _, _ in WANTED:
        names = sorted(index["name"] for index in database[collection_name].list_indexes())
        print(f"  {collection_name}: {', '.join(names)}")


if __name__ == "__main__":
    main()
