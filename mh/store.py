"""All MongoDB access for mongo-harness.

Connections are created lazily on first use — nothing is opened at import time.
No ``print`` calls; use the ``logging`` module.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import OperationFailure, PyMongoError

from mh import config

logger = logging.getLogger(__name__)

_COLLECTIONS = ("runs", "steps", "lessons", "versions", "edits", "fetches")

# Lazily populated; never created at import time.
_client: Optional[MongoClient] = None


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _get_client() -> MongoClient:
    """Return a process-wide MongoClient, creating it on first call."""
    global _client
    if _client is None:
        uri = config.mongodb_uri()
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        logger.debug("MongoClient created (uri_kind=%s)", config.uri_kind(uri))
    return _client


def get_db() -> Database:
    """Return the configured harness database (lazy connect)."""
    return _get_client()[config.db_name()]


def ensure_schema(db: Optional[Database] = None) -> dict:
    """Create harness collections and MQL indexes; return what exists.

    Returns a dict with keys ``collections`` (list of names present) and
    ``indexes`` (mapping collection -> list of index names).
    """
    database = db if db is not None else get_db()
    existing = set(database.list_collection_names())
    for name in _COLLECTIONS:
        if name not in existing:
            database.create_collection(name)
            logger.info("created collection %s", name)

    index_specs: dict[str, list[tuple[list[tuple[str, int]], dict[str, Any]]]] = {
        "runs": [
            ([("run_id", ASCENDING)], {"name": "run_id_1", "unique": True}),
            ([("version_id", ASCENDING)], {"name": "version_id_1"}),
            ([("started_at", ASCENDING)], {"name": "started_at_1"}),
        ],
        "steps": [
            ([("run_id", ASCENDING)], {"name": "run_id_1"}),
            ([("task_id", ASCENDING)], {"name": "task_id_1"}),
        ],
        "lessons": [
            ([("task_id", ASCENDING)], {"name": "task_id_1"}),
            ([("created_at", ASCENDING)], {"name": "created_at_1"}),
        ],
        "versions": [
            ([("version_id", ASCENDING)], {"name": "version_id_1", "unique": True}),
            ([("created_at", ASCENDING)], {"name": "created_at_1"}),
        ],
        "edits": [
            ([("version_to", ASCENDING)], {"name": "version_to_1"}),
            ([("created_at", ASCENDING)], {"name": "created_at_1"}),
        ],
        "fetches": [
            ([("ts", ASCENDING)], {"name": "ts_1"}),
            ([("sha256", ASCENDING)], {"name": "sha256_1"}),
        ],
    }

    indexes_out: dict[str, list[str]] = {}
    for coll_name, specs in index_specs.items():
        coll = database[coll_name]
        for keys, kwargs in specs:
            try:
                coll.create_index(keys, **kwargs)
            except OperationFailure as exc:
                logger.warning("index %s on %s: %s", kwargs.get("name"), coll_name, exc)
        indexes_out[coll_name] = [idx["name"] for idx in coll.list_indexes()]

    collections = sorted(database.list_collection_names())
    return {"collections": collections, "indexes": indexes_out}


def ok() -> dict:
    """Ping the server and return connectivity status.

    Returns ``{"ok": bool, "uri_kind": "atlas"|"local", "db": str, "server_version": str}``.
    """
    uri = config.mongodb_uri()
    kind = config.uri_kind(uri)
    db_name = config.db_name()
    try:
        client = _get_client()
        info = client.server_info()
        version = str(info.get("version", "unknown"))
        client.admin.command("ping")
        return {"ok": True, "uri_kind": kind, "db": db_name, "server_version": version}
    except PyMongoError as exc:
        logger.error("ok() failed: %s", exc)
        return {"ok": False, "uri_kind": kind, "db": db_name, "server_version": ""}


def _insert_one(collection_name: str, doc: dict, db: Optional[Database] = None) -> str:
    """Insert ``doc`` into ``collection_name`` and return the inserted id as str."""
    database = db if db is not None else get_db()
    result = database[collection_name].insert_one(doc)
    return str(result.inserted_id)


def record_run(doc: dict) -> str:
    """Insert a run document; return inserted id as str."""
    payload = dict(doc)
    if "started_at" not in payload:
        payload["started_at"] = _utc_now()
    return _insert_one("runs", payload)


def record_step(doc: dict) -> str:
    """Insert a step document; return inserted id as str."""
    return _insert_one("steps", dict(doc))


def record_version(doc: dict) -> str:
    """Insert a version document; return inserted id as str.

    Expected keys: ``version_id`` (int), ``config`` (dict), ``parent`` (int|None),
    ``created_at``, ``fingerprint`` (str). Optional: ``promoted_by``.
    """
    payload = dict(doc)
    if "created_at" not in payload:
        payload["created_at"] = _utc_now()
    if "promoted_by" not in payload:
        payload["promoted_by"] = "manual"
    return _insert_one("versions", payload)


def record_edit(doc: dict) -> str:
    """Insert an edit journal document; return inserted id as str."""
    payload = dict(doc)
    if "created_at" not in payload:
        payload["created_at"] = _utc_now()
    if "rolled_back" not in payload:
        payload["rolled_back"] = False
    return _insert_one("edits", payload)


def record_lesson(doc: dict) -> str:
    """Insert a lesson document with embedding; return inserted id as str.

    Accepts either ``expected``/``got`` or ``expected_digest``/``got_digest``.
    ``embedding`` must be a plain list of floats (stored as-is).
    """
    payload = dict(doc)
    if "expected_digest" not in payload and "expected" in payload:
        payload["expected_digest"] = payload.pop("expected")
    elif "expected" in payload:
        payload.pop("expected", None)
    if "got_digest" not in payload and "got" in payload:
        payload["got_digest"] = payload.pop("got")
    elif "got" in payload:
        payload.pop("got", None)
    emb = payload.get("embedding")
    if emb is not None:
        payload["embedding"] = [float(x) for x in emb]
    if "created_at" not in payload:
        payload["created_at"] = _utc_now()
    return _insert_one("lessons", payload)


def latest_version() -> dict | None:
    """Return the version document with the highest ``version_id``, or None."""
    doc = get_db()["versions"].find_one(sort=[("version_id", -1)])
    return doc


def get_version(version_id: int) -> dict | None:
    """Return the version document for ``version_id``, or None."""
    return get_db()["versions"].find_one({"version_id": version_id})


def list_edits(limit: int = 50) -> list[dict]:
    """Return recent edit documents, newest first, up to ``limit``."""
    cursor = get_db()["edits"].find().sort("created_at", -1).limit(limit)
    return list(cursor)


def run_score(run_id: str) -> dict:
    """Compute pass rate for ``run_id`` from the ``runs`` doc or its steps.

    Returns ``{"passed": int, "total": int, "rate": float}``.
    """
    database = get_db()
    run = database["runs"].find_one({"run_id": run_id})
    if run is not None and "passed" in run and "total" in run:
        total = int(run["total"])
        passed = int(run["passed"])
        rate = float(run["rate"]) if "rate" in run else (passed / total if total else 0.0)
        return {"passed": passed, "total": total, "rate": rate}

    steps = list(database["steps"].find({"run_id": run_id}))
    total = len(steps)
    passed = sum(1 for s in steps if s.get("passed"))
    rate = (passed / total) if total else 0.0
    return {"passed": passed, "total": total, "rate": rate}


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        fx = float(x)
        fy = float(y)
        dot += fx * fy
        na += fx * fx
        nb += fy * fy
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _vector_search_local(
    query_vector: list[float],
    k: int,
    database: Database,
) -> list[dict]:
    """In-process cosine ranking over ``lessons`` with an ``embedding`` field."""
    scored: list[tuple[float, dict]] = []
    for doc in database["lessons"].find({"embedding": {"$exists": True, "$ne": []}}):
        emb = doc.get("embedding")
        if not isinstance(emb, list) or not emb:
            continue
        score = _cosine(query_vector, [float(x) for x in emb])
        item = dict(doc)
        item["score"] = score
        scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:k]]


def _try_atlas_vector_search(
    query_vector: list[float],
    k: int,
    database: Database,
    index_name: str = "lessons_vec",
) -> list[dict] | None:
    """Run `$vectorSearch` if available; return None on any failure."""
    pipeline = [
        {
            "$vectorSearch": {
                "index": index_name,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": max(k * 10, 50),
                "limit": k,
            }
        },
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
    ]
    try:
        return list(database["lessons"].aggregate(pipeline))
    except PyMongoError as exc:
        logger.info("Atlas $vectorSearch unavailable, falling back: %s", exc)
        return None


def vector_search(
    query_vector: list[float],
    k: int = 5,
    db: Optional[Database] = None,
) -> list[dict]:
    """Return up to ``k`` lessons sorted by similarity desc, each with a ``score`` key.

    Uses Atlas `$vectorSearch` when `MH_USE_VECTOR` is enabled and the deployment
    supports it; otherwise falls back to in-process cosine similarity.
    """
    database = db if db is not None else get_db()
    qv = [float(x) for x in query_vector]

    if config.use_vector() and config.uri_kind() == "atlas":
        atlas_hits = _try_atlas_vector_search(qv, k, database)
        if atlas_hits is not None:
            return atlas_hits

    return _vector_search_local(qv, k, database)


def vector_index_spec(name: str = "lessons_vec") -> dict:
    """Return the Atlas Vector Search index definition for ``lessons.embedding``."""
    return {
        "name": name,
        "type": "vectorSearch",
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": 384,
                    "similarity": "cosine",
                }
            ]
        },
    }


def ensure_vector_index(db: Optional[Database] = None) -> dict:
    """Create the Atlas Vector Search index if the deployment is Atlas.

    On plain mongod, return ``{"created": False, "reason": "not_atlas"}`` and
    never raise.
    """
    database = db if db is not None else get_db()
    if config.uri_kind() != "atlas":
        return {"created": False, "reason": "not_atlas"}

    spec = vector_index_spec()
    try:
        from pymongo.operations import SearchIndexModel

        model = SearchIndexModel(
            definition=spec["definition"],
            name=spec["name"],
            type=spec["type"],
        )
        index_name = database["lessons"].create_search_index(model=model)
        logger.info("created vector search index %s", index_name)
        return {"created": True, "name": index_name}
    except Exception as exc:  # noqa: BLE001 — must never raise to callers on API refusal
        logger.warning("ensure_vector_index failed: %s", exc)
        return {"created": False, "reason": str(exc), "spec": spec}
