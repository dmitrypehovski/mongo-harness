#!/usr/bin/env python3
"""Load sample_mflix collections into the target database.

Idempotent: drops and reloads the five mflix collections, or skips restore
when counts already look populated and ``--force`` is not set.

Preferred path: ``mongorestore`` with the official Atlas education archive.
Fallback: download public JSON dumps and ``insert_many`` in batches of 1000.
Never embeds credentials; never prints the URI.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mh import config  # noqa: E402
from mh import store  # noqa: E402

MFLIX_COLLECTIONS = ("movies", "comments", "theaters", "users", "sessions")
ARCHIVE_URL = "https://atlas-education.s3.amazonaws.com/sample_mflix.archive"

# Public JSON mirrors used when mongorestore / archive path is unavailable.
JSON_FALLBACK_BASE = (
    "https://raw.githubusercontent.com/neelabalan/mongodb-sample-dataset/main/sample_mflix"
)
BATCH_SIZE = 1000


def _count_summary(database) -> dict[str, int]:
    """Return document counts for mflix collections."""
    return {name: database[name].estimated_document_count() for name in MFLIX_COLLECTIONS}


def _already_loaded(database) -> bool:
    """True if movies (and at least one other) collection has documents."""
    counts = _count_summary(database)
    return counts.get("movies", 0) > 0 and sum(counts.values()) > 0


def _mongorestore_available() -> bool:
    """Return True if the mongorestore binary is on PATH."""
    return shutil.which("mongorestore") is not None


def _restore_archive(uri: str, db_name: str, archive_path: Path) -> None:
    """Restore sample_mflix archive into ``db_name`` via mongorestore."""
    cmd = [
        "mongorestore",
        f"--uri={uri}",
        f"--nsFrom=sample_mflix.*",
        f"--nsTo={db_name}.*",
        f"--archive={archive_path}",
        "--drop",
    ]
    print("Running mongorestore from archive…")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Redact URI if it leaked into stderr
        err = (proc.stderr or proc.stdout or "").replace(uri, "<MONGODB_URI>")
        raise RuntimeError(f"mongorestore failed (exit {proc.returncode}): {err[:500]}")


def _download(url: str, dest: Path) -> None:
    """Download ``url`` to ``dest`` with a simple progress note."""
    print(f"Downloading {url} …")
    with urllib.request.urlopen(url, timeout=120) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


def _iter_json_docs(path: Path) -> Iterable[dict[str, Any]]:
    """Yield documents from a JSON array file or NDJSON."""
    text = path.read_text(encoding="utf-8")
    text_stripped = text.lstrip()
    if text_stripped.startswith("["):
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError(f"expected JSON array in {path}")
        for item in data:
            if isinstance(item, dict):
                yield item
        return
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if isinstance(obj, dict):
            yield obj


def _insert_batches(collection, docs: Iterable[dict[str, Any]]) -> int:
    """Insert documents in batches of BATCH_SIZE; return total inserted."""
    batch: list[dict[str, Any]] = []
    total = 0
    for doc in docs:
        batch.append(doc)
        if len(batch) >= BATCH_SIZE:
            collection.insert_many(batch, ordered=False)
            total += len(batch)
            print(f"  … {collection.name}: {total}")
            batch = []
    if batch:
        collection.insert_many(batch, ordered=False)
        total += len(batch)
    return total


def _load_json_fallback(database) -> dict[str, int]:
    """Download JSON collections and insert_many in batches."""
    loaded: dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="mh_mflix_") as tmp:
        tmp_path = Path(tmp)
        for name in MFLIX_COLLECTIONS:
            url = f"{JSON_FALLBACK_BASE}/{name}.json"
            dest = tmp_path / f"{name}.json"
            try:
                _download(url, dest)
            except Exception as exc:  # noqa: BLE001
                print(f"WARN: skip {name}: download failed: {exc}")
                loaded[name] = 0
                continue
            database[name].drop()
            count = _insert_batches(database[name], _iter_json_docs(dest))
            loaded[name] = count
            print(f"loaded {name}: {count}")
    return loaded


def load_mflix(*, force: bool = False) -> dict[str, int]:
    """Load sample_mflix into the configured database; return per-collection counts."""
    uri = config.mongodb_uri()
    db_name = config.db_name()
    database = store.get_db()

    if not force and _already_loaded(database):
        counts = _count_summary(database)
        print("sample_mflix already present (use --force to reload). Counts:")
        for name, n in counts.items():
            print(f"  {name}: {n}")
        return counts

    kind = config.uri_kind(uri)
    if _mongorestore_available():
        with tempfile.TemporaryDirectory(prefix="mh_mflix_arch_") as tmp:
            archive = Path(tmp) / "sample_mflix.archive"
            try:
                _download(ARCHIVE_URL, archive)
                _restore_archive(uri, db_name, archive)
                counts = _count_summary(database)
                print("mongorestore complete. Counts:")
                for name, n in counts.items():
                    print(f"  {name}: {n}")
                return counts
            except Exception as exc:  # noqa: BLE001
                print(f"WARN: archive/mongorestore path failed ({exc}); trying JSON fallback")
    else:
        print("mongorestore not on PATH; using JSON fallback")
        if kind == "atlas":
            print("(Atlas URI detected; archive restore preferred when mongorestore is installed)")

    counts = _load_json_fallback(database)
    print("JSON load complete. Counts:")
    for name, n in counts.items():
        print(f"  {name}: {n}")
    return counts


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Load sample_mflix into MH_DB")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Drop and reload even if collections already have documents",
    )
    args = parser.parse_args()
    try:
        load_mflix(force=args.force)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
