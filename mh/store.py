"""All MongoDB access for mongo-harness.

Connections are created lazily on first use — nothing is opened at import time.
No ``print`` calls; use the ``logging`` module.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import OperationFailure, PyMongoError

from mh import config, embed

logger = logging.getLogger(__name__)


class LessonSource(Protocol):
    """What the local recall actually needs of a database: ``database["lessons"].find(query)``.

    Narrowing the parameter to this is what lets the scoping be tested without a server.
    """

    def __getitem__(self, name: str) -> Any: ...

_COLLECTIONS = ("runs", "steps", "lessons", "versions", "edits", "fetches")

# Lazily populated; never created at import time.
_client: Optional[MongoClient] = None


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def utc_now() -> datetime:
    """A timezone-aware UTC timestamp, for anything writing to the ledger from outside."""
    return _utc_now()


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


def dataset_identity() -> dict:
    """Which data, and which questions, the active harness is working on.

    ``key`` is the scope of the data — what recall and past results are filtered by. ``pack`` is the
    fingerprint of the exact question wording, kept for provenance only: it changes whenever an exam
    is regenerated, and memory should survive that.
    """
    from mh import tasks

    return {
        "key": tasks.pack_scope(),
        "pack": tasks.pack_key(),
        "questions": len(tasks.TASKS),
        "name": tasks.pack_name(),
        "collections": tasks.pack_collections(),
        "generated": tasks.is_generated(),
    }


def dataset_query(extra: dict | None = None) -> dict:
    """A query for runs belonging to the question set that is active right now.

    Two datasets otherwise write into one ledger indistinguishable from each other, and the
    later measurement silently becomes the record of the earlier one — which is exactly what
    happened the first time a second dataset was measured here: an exam over a different
    collection overwrote the film figures the project page was showing.
    """
    from mh import tasks

    query = dict(extra or {})
    query["dataset.key"] = tasks.pack_key()
    return query


def record_run(doc: dict) -> str:
    """Insert a run document; return inserted id as str.

    Every run is stamped with a fingerprint of the question set it measured, so a run can never
    be read as a measurement of some other exam.
    """
    payload = dict(doc)
    payload.setdefault("dataset", dataset_identity())
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

    Stamped with the question set it was learned on, like every run: a lesson about one dataset's
    fields is not advice for another's.

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
    payload.setdefault("dataset", dataset_identity())
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
    database: LessonSource,
    dataset_key: str | None = None,
) -> list[dict]:
    """In-process cosine ranking over ``lessons`` with an ``embedding`` field.

    ``dataset_key`` keeps the recall inside one question set. Without it a new dataset recalls
    memories of another one: the lesson "watch the year field" means nothing about theatres, and a
    harness whose memory is film-shaped is not usable on someone else's data.
    """
    query: dict = {"embedding": {"$exists": True, "$ne": []}}
    if dataset_key:
        query["dataset.key"] = dataset_key
    scored: list[tuple[float, dict]] = []
    mismatched = 0
    for doc in database["lessons"].find(query):
        emb = doc.get("embedding")
        if not isinstance(emb, list) or not emb:
            continue
        if len(emb) != len(query_vector):
            # a lesson embedded by another model cannot be compared, and cosine would silently
            # score it zero — a recall that looks empty rather than broken
            mismatched += 1
            continue
        score = _cosine(query_vector, [float(x) for x in emb])
        item = dict(doc)
        item["score"] = score
        scored.append((score, item))
    if mismatched:
        log.warning(
            "%d lesson(s) have embeddings of another width than the model in use (MH_EMBED_DIM=%d); "
            "they are not being recalled — re-embed them or point the harness back at the old model",
            mismatched,
            len(query_vector),
        )
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:k]]


def embedding_widths(db: Optional[Database] = None) -> dict:
    """How wide the stored embeddings are, against the width the code is configured for.

    Switching embedding models does not rewrite what is already stored, and a mismatch makes recall
    quietly empty instead of loudly wrong. This is what a caller checks before believing an empty
    result is an answer.
    """
    database = db if db is not None else get_db()
    widths: dict[int, int] = {}
    for doc in database["lessons"].find({"embedding": {"$exists": True}}):
        embedding = doc.get("embedding")
        if isinstance(embedding, list) and embedding:
            widths[len(embedding)] = widths.get(len(embedding), 0) + 1
    configured = embed.DIM
    return {
        "configured": configured,
        "stored": widths,
        "mismatched": sum(count for width, count in widths.items() if width != configured),
        "all_agree": all(width == configured for width in widths),
    }


def vector_search_stage(
    query_vector: list[float],
    k: int,
    index_name: str = "lessons_vec",
    dataset_key: str | None = None,
) -> dict:
    """The `$vectorSearch` stage, filter included.

    The filter has to be expressed inside the search stage rather than in a following ``$match``:
    a filter after the stage would rank lessons from another dataset and then throw them away,
    leaves fewer hits than the caller asked for. Filtering there also requires the field to be
    declared in the index, which ``vector_index_spec`` does.
    """
    stage: dict = {
        "index": index_name,
        "path": "embedding",
        "queryVector": query_vector,
        "numCandidates": max(k * 10, 50),
        "limit": k,
    }
    if dataset_key:
        stage["filter"] = {"dataset.key": dataset_key}
    return stage


def _try_atlas_vector_search(
    query_vector: list[float],
    k: int,
    database: Database,
    index_name: str = "lessons_vec",
    dataset_key: str | None = None,
) -> list[dict] | None:
    """Run `$vectorSearch` if available; return None on any failure."""
    stage = vector_search_stage(query_vector, k, index_name, dataset_key)
    pipeline = [
        {"$vectorSearch": stage},
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
    dataset_key: str | None = None,
) -> list[dict]:
    """Return up to ``k`` lessons sorted by similarity desc, each with a ``score`` key.

    Uses Atlas `$vectorSearch` when `MH_USE_VECTOR` is enabled and the deployment
    supports it; otherwise falls back to in-process cosine similarity. ``dataset_key`` restricts
    recall to one question set.
    """
    database = db if db is not None else get_db()
    qv = [float(x) for x in query_vector]

    if config.use_vector() and config.uri_kind() == "atlas":
        atlas_hits = _try_atlas_vector_search(qv, k, database, dataset_key=dataset_key)
        if atlas_hits is not None:
            return atlas_hits

    return _vector_search_local(qv, k, database, dataset_key=dataset_key)


def index_shape(definition: dict | None) -> dict[str, dict]:
    """The parts of an index definition that have to agree with this code.

    Width matters as much as which fields exist: an index built for a 768-number model refuses every
    vector a 384-number model produces, and the failure looks like an empty search rather than a
    misconfiguration.
    """
    shape: dict[str, dict] = {}
    for field in (definition or {}).get("fields", []):
        path = field.get("path")
        if not path:
            continue
        if field.get("type") == "vector":
            shape[path] = {
                "type": "vector",
                "numDimensions": field.get("numDimensions"),
                "similarity": field.get("similarity"),
            }
        else:
            shape[path] = {"type": field.get("type")}
    return shape


def index_differences(current: dict | None, wanted: dict | None) -> list[str]:
    """Every way the index Atlas holds differs from the one this code expects."""
    have, want = index_shape(current), index_shape(wanted)
    problems: list[str] = []
    for path in sorted(set(have) | set(want)):
        if path not in have:
            problems.append(f"{path}: missing from the index")
        elif path not in want:
            problems.append(f"{path}: in the index but not wanted")
        elif have[path] != want[path]:
            problems.append(f"{path}: index has {have[path]}, code wants {want[path]}")
    return problems


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
                    # taken from the embedding module, not typed in: an index built for another
                    # model's width silently refuses every vector this code produces
                    "numDimensions": embed.DIM,
                    "similarity": "cosine",
                },
                # declared so $vectorSearch may filter on it: a lesson learned on one question set
                # must not be ranked into another set's recall
                {"type": "filter", "path": "dataset.key"},
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
