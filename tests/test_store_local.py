"""Local store tests against docker MongoDB at mongodb://localhost:27017.

Uses scratch database ``harness_test`` and drops it at the end of the session.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

# Force local docker MongoDB and a scratch DB before importing mh.store.
os.environ["MONGODB_URI"] = "mongodb://localhost:27017"
os.environ["MH_DB"] = "harness_test"
os.environ["MH_USE_VECTOR"] = "0"

from mh import config  # noqa: E402
from mh import store  # noqa: E402


SCRATCH_DB = "harness_test"


def _reachable(uri: str = "mongodb://localhost:27017", timeout_ms: int = 800) -> bool:
    """Whether a MongoDB is listening, checked quickly and without raising."""
    from pymongo import MongoClient

    try:
        MongoClient(uri, serverSelectionTimeoutMS=timeout_ms).admin.command("ping")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def _scratch_db():
    """Ensure schema for the session; drop the scratch database afterwards.

    These tests exercise the store against a real server and need one on localhost:27017:
    ``docker run -d -p 27017:27017 mongo:7``, or the service container in
    ``.github/workflows/tests.yml``. Without one they skip with a reason instead of failing, so
    the rest of the suite still runs on a laptop with no database — and so a silent skip is
    visible in the summary rather than hidden.
    """
    if not _reachable():
        pytest.skip(
            "no MongoDB on mongodb://localhost:27017: start one with "
            "docker run -d -p 27017:27017 mongo:7 to run the store tests"
        )
    # Reset cached URI/settings in case other imports ran first.
    config.mongodb_uri.cache_clear()
    os.environ["MONGODB_URI"] = "mongodb://localhost:27017"
    os.environ["MH_DB"] = SCRATCH_DB
    os.environ["MH_USE_VECTOR"] = "0"
    config.mongodb_uri.cache_clear()

    # Drop any leftover client pointing at a previous DB name by resetting.
    store._client = None  # type: ignore[attr-defined]

    db = store.get_db()
    assert db.name == SCRATCH_DB
    store.ensure_schema(db)
    yield db
    store._get_client().drop_database(SCRATCH_DB)
    store._client = None  # type: ignore[attr-defined]


def test_ok():
    """ok() reports a healthy local server."""
    status = store.ok()
    assert status["ok"] is True
    assert status["uri_kind"] == "local"
    assert status["db"] == SCRATCH_DB
    assert status["server_version"]


def test_ensure_schema():
    """ensure_schema creates the expected collections and indexes."""
    result = store.ensure_schema()
    for name in ("runs", "steps", "lessons", "versions", "edits", "fetches"):
        assert name in result["collections"]
        assert name in result["indexes"]
        assert "version_id_1" in result["indexes"]["versions"] or name != "versions"


def test_record_and_get_version():
    """record_version / latest_version / get_version round-trip."""
    doc = {
        "version_id": 1,
        "config": {
            "system_prompt": "test",
            "rules": ["r1"],
            "cot": True,
            "sample_docs_n": 3,
            "include_indexes": True,
            "retrieve_k": 5,
            "tools": ["find", "aggregate", "count"],
        },
        "parent": None,
        "created_at": datetime.now(timezone.utc),
        "fingerprint": "fp-1",
        "promoted_by": "genesis",
    }
    inserted = store.record_version(doc)
    assert isinstance(inserted, str) and inserted

    latest = store.latest_version()
    assert latest is not None
    assert latest["version_id"] == 1
    assert latest["fingerprint"] == "fp-1"

    got = store.get_version(1)
    assert got is not None
    assert got["config"]["tools"] == ["find", "aggregate", "count"]


def test_record_run_steps_and_score():
    """record_run + record_step + run_score."""
    run_id = "run-test-1"
    store.record_run(
        {
            "run_id": run_id,
            "version_id": 1,
            "suite": "train",
            "started_at": datetime.now(timezone.utc),
            "finished_at": datetime.now(timezone.utc),
            "total": 2,
            "passed": 1,
            "rate": 0.5,
            "notes": "",
        }
    )
    store.record_step(
        {
            "run_id": run_id,
            "task_id": "t1",
            "question": "q1",
            "db": "harness_test",
            "collection": "movies",
            "generated_query": {"find": "movies"},
            "executed_ok": True,
            "result_digest": "a",
            "expected_digest": "a",
            "passed": True,
            "latency_ms": 1,
            "error": None,
        }
    )
    store.record_step(
        {
            "run_id": run_id,
            "task_id": "t2",
            "question": "q2",
            "db": "harness_test",
            "collection": "movies",
            "generated_query": {"find": "movies"},
            "executed_ok": True,
            "result_digest": "b",
            "expected_digest": "c",
            "passed": False,
            "latency_ms": 2,
            "error": None,
        }
    )
    score = store.run_score(run_id)
    assert score == {"passed": 1, "total": 2, "rate": 0.5}


def test_record_lesson_and_vector_search_ordering():
    """record_lesson stores float embeddings; vector_search ranks by cosine."""
    # Clear lessons so ordering is deterministic for this test.
    store.get_db()["lessons"].delete_many({})

    base = [1.0, 0.0, 0.0]
    near = [0.9, 0.1, 0.0]
    far = [0.0, 1.0, 0.0]

    store.record_lesson(
        {
            "task_id": "far",
            "question": "far q",
            "reason": "wrong_result",
            "failed_query": {},
            "expected": "e1",
            "got": "g1",
            "embedding": far,
        }
    )
    store.record_lesson(
        {
            "task_id": "near",
            "question": "near q",
            "reason": "invalid_query",
            "failed_query": {},
            "expected_digest": "e2",
            "got_digest": "g2",
            "embedding": near,
        }
    )
    store.record_lesson(
        {
            "task_id": "base",
            "question": "base q",
            "reason": "exception",
            "failed_query": {},
            "expected_digest": "e3",
            "got_digest": "g3",
            "embedding": base,
        }
    )

    stored = store.get_db()["lessons"].find_one({"task_id": "near"})
    assert stored is not None
    assert isinstance(stored["embedding"], list)
    assert all(isinstance(x, float) for x in stored["embedding"])

    hits = store.vector_search(base, k=3)
    assert len(hits) == 3
    assert all("score" in h for h in hits)
    # Descending similarity: base ~ 1.0, near high, far ~ 0.
    assert hits[0]["task_id"] == "base"
    assert hits[1]["task_id"] == "near"
    assert hits[2]["task_id"] == "far"
    assert hits[0]["score"] >= hits[1]["score"] >= hits[2]["score"]


def test_ensure_vector_index_not_atlas():
    """On local mongod, ensure_vector_index returns not_atlas without raising."""
    result = store.ensure_vector_index()
    assert result["created"] is False
    assert result["reason"] == "not_atlas"


def test_list_edits():
    """record_edit + list_edits returns newest-first entries."""
    store.get_db()["edits"].delete_many({})
    store.record_edit(
        {
            "version_from": 1,
            "version_to": 2,
            "proposal": {"cot": False},
            "rationale": "try without cot",
            "evidence": {
                "train_rate_before": 0.5,
                "train_rate_after": 0.6,
                "holdout_before": 0.4,
                "holdout_after": 0.45,
                "n_before": 10,
                "n_after": 10,
            },
            "decision": "promoted",
            "reason": "holdout improved",
            "created_at": datetime.now(timezone.utc),
            "rolled_back": False,
        }
    )
    store.record_edit(
        {
            "version_from": 2,
            "version_to": 3,
            "proposal": {"tools": ["find", "aggregate", "count", "schema"]},
            "rationale": "more tools",
            "evidence": {
                "train_rate_before": 0.6,
                "train_rate_after": 0.9,
                "holdout_before": 0.45,
                "holdout_after": 0.4,
                "n_before": 10,
                "n_after": 10,
            },
            "decision": "rejected_envelope",
            "reason": "tools expansion blocked",
            "rolled_back": False,
        }
    )
    edits = store.list_edits(limit=10)
    assert len(edits) >= 2
    assert edits[0]["decision"] in {
        "promoted",
        "rejected_outsample",
        "rejected_envelope",
        "rejected_insignificant",
    }


def test_vector_index_spec_shape():
    """vector_index_spec matches the Atlas contract, at the width of the model in use."""
    from mh import embed

    spec = store.vector_index_spec()
    assert spec["name"] == "lessons_vec"
    assert spec["type"] == "vectorSearch"
    field = spec["definition"]["fields"][0]
    assert field["type"] == "vector"
    assert field["path"] == "embedding"
    assert field["numDimensions"] == embed.DIM, "the index must be built for the model in use"
    assert field["similarity"] == "cosine"


def test_a_new_lesson_records_which_model_embedded_it():
    """A lesson is born verifiable: without the stamp it is indistinguishable from a stale one."""
    from mh import embed, reembed, tasks

    db = store.get_db()
    db["lessons"].delete_many({"task_id": "model-stamp"})
    try:
        store.record_lesson(
            {
                "task_id": "model-stamp",
                "question": "How many rows are there?",
                "embedding": [0.2] * embed.DIM,
                "expected_digest": "expected",
                "got_digest": "got",
            }
        )
        stored = db["lessons"].find_one({"task_id": "model-stamp"})
        assert stored["embedding_model"] == embed.MODEL_NAME

        plan = reembed.plan(db, dataset_key=tasks.pack_scope())
        assert not [sample for sample in plan.samples if sample["task_id"] == "model-stamp"]
    finally:
        db["lessons"].delete_many({"task_id": "model-stamp"})


def test_reembed_brings_a_lesson_back_into_recall():
    """A lesson written by another model is noticed, rewritten, and comparable again."""
    from mh import embed, reembed, tasks

    db = store.get_db()
    db["lessons"].delete_many({"task_id": "reembed-check"})
    try:
        store.record_lesson(
            {
                "task_id": "reembed-check",
                "question": "How many rows are there in total?",
                "embedding": [0.1] * (embed.DIM + 1),
                "expected_digest": "expected",
                "got_digest": "got",
            }
        )
        before = reembed.plan(db, dataset_key=tasks.pack_scope())
        assert before.mismatched >= 1, "a lesson of another width must be reported, not ignored"

        _, after, written = reembed.reembed(db, dataset_key=tasks.pack_scope(), batch=4)
        assert written >= 1
        assert after.mismatched < before.mismatched

        fixed = db["lessons"].find_one({"task_id": "reembed-check"})
        assert len(fixed["embedding"]) == embed.DIM
        assert fixed["embedding_model"] == embed.MODEL_NAME

        hits = store.vector_search([0.1] * embed.DIM, k=10, db=db, dataset_key=tasks.pack_scope())
        assert any(hit.get("task_id") == "reembed-check" for hit in hits), "recall must see it again"
    finally:
        db["lessons"].delete_many({"task_id": "reembed-check"})
