"""Changing the embedding model must be a recoverable operation, not a silent amnesia.

Lessons already stored keep the width they were written with, and recall across two widths is not a
comparison but a silence. These tests pin down that the harness notices, says so, rewrites what it
can, and reads the result back instead of trusting what it sent.
"""

from __future__ import annotations

from typing import Any

import pytest

from mh import embed, reembed


class FakeCollection:
    """A collection that answers ``find`` over plain dicts and records what was written to it."""

    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs
        self.updates: list[tuple[dict, dict]] = []

    def find(self, query: dict | None = None):  # noqa: ANN201 - mirrors pymongo's shape
        for doc in self.docs:
            if self._matches(doc, query or {}):
                yield doc

    def update_one(self, where: dict, update: dict) -> None:
        self.updates.append((where, update))
        for doc in self.docs:
            if doc.get("_id") == where.get("_id"):
                doc.update(update.get("$set") or {})

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        for key, want in query.items():
            if key == "dataset.key":
                if (doc.get("dataset") or {}).get("key") != want:
                    return False
            elif doc.get(key) != want:
                return False
        return True


class FakeDatabase:
    """A database holding lessons and nothing else."""

    def __init__(self, lessons: list[dict]) -> None:
        self.lessons = FakeCollection(lessons)

    def __getitem__(self, name: str) -> FakeCollection:
        assert name == "lessons", name
        return self.lessons


def _lesson(
    task_id: str,
    width: int,
    key: str = "scope-a",
    text: str = "How many rows?",
    model: str | None = embed.MODEL_NAME,
) -> dict:
    doc = {
        "_id": f"id-{task_id}",
        "task_id": task_id,
        "question": text,
        "embedding": [0.1] * width,
        "dataset": {"key": key, "name": "sample_mflix"},
    }
    if model is not None:
        doc["embedding_model"] = model
    return doc


def _fixed_vectors(texts: list[str]) -> list[list[float]]:
    """A stand-in for the model: right width, different numbers per text."""
    return [[float(len(text) % 7)] * embed.DIM for text in texts]


def test_plan_counts_what_can_and_cannot_be_compared() -> None:
    """A lesson embedded at another width is reported, not silently dropped from recall."""
    db = FakeDatabase([_lesson("a", embed.DIM), _lesson("b", 768), _lesson("c", 0)])
    result = reembed.plan(db)
    assert result.total == 3
    assert result.ok == 1
    assert result.mismatched == 1
    assert result.missing == 1
    assert result.needed == 2


def test_plan_reports_the_model_in_use() -> None:
    """The plan names the model and the width, so the report says what it compared against."""
    result = reembed.plan(FakeDatabase([]))
    assert result.model == embed.MODEL_NAME
    assert result.dim == embed.DIM
    assert result.needed == 0


def test_plan_keeps_examples_readable() -> None:
    """A plan with hundreds of stale lessons still prints a short list."""
    db = FakeDatabase([_lesson(f"t{index}", 768) for index in range(30)])
    result = reembed.plan(db, sample_limit=5)
    assert result.mismatched == 30
    assert len(result.samples) == 5
    assert result.samples[0]["reason"]


def test_plan_can_be_limited_to_one_scope() -> None:
    """Re-embedding one question set must not touch another's memory."""
    db = FakeDatabase([_lesson("a", 768, key="scope-a"), _lesson("b", 768, key="scope-b")])
    result = reembed.plan(db, dataset_key="scope-b")
    assert result.total == 1
    assert result.mismatched == 1


def test_apply_writes_the_vector_and_names_the_model() -> None:
    """A rewritten lesson records which model produced the vector it now holds."""
    db = FakeDatabase([_lesson("a", 768)])
    lessons = list(db["lessons"].find({}))
    written = reembed.apply(db, lessons, embed_fn=_fixed_vectors)
    assert written == 1
    stored = db.lessons.docs[0]
    assert len(stored["embedding"]) == embed.DIM
    assert stored["embedding_model"] == embed.MODEL_NAME
    assert stored["reembedded_at"] is not None


def test_apply_skips_a_lesson_with_no_text() -> None:
    """Nothing is written for a document with nothing to embed."""
    db = FakeDatabase([_lesson("a", 0, text="")])
    lessons = list(db["lessons"].find({}))
    assert reembed.apply(db, lessons, embed_fn=_fixed_vectors) == 0
    assert db.lessons.updates == []


def test_apply_refuses_a_vector_of_the_wrong_width() -> None:
    """A model returning the wrong number of numbers is refused rather than stored."""
    db = FakeDatabase([_lesson("a", 768)])
    lessons = list(db["lessons"].find({}))
    written = reembed.apply(db, lessons, embed_fn=lambda texts: [[0.0] * 5 for _ in texts])
    assert written == 0
    assert db.lessons.updates == []


def test_apply_on_nothing_is_not_an_error() -> None:
    """An empty plan is a normal outcome, not a failure."""
    assert reembed.apply(FakeDatabase([]), []) == 0


def test_reembed_rewrites_and_then_reads_the_result_back() -> None:
    """The plan returned after the work comes out of the database, not out of the argument list."""
    db = FakeDatabase([_lesson("a", 768), _lesson("b", embed.DIM)])
    before, after, written = reembed.reembed(db, batch=1)
    assert before.needed == 1
    assert written == 1
    assert after.needed == 0
    assert after.ok == 2


def test_reembed_dry_run_writes_nothing() -> None:
    """Looking before rewriting is the default for anyone cautious, and it says what it would do."""
    db = FakeDatabase([_lesson("a", 768)])
    before, after, written = reembed.reembed(db, dry_run=True)
    assert before.needed == 1
    assert written == 0
    assert after.needed == 1
    assert db.lessons.updates == []


def test_reembed_when_everything_is_fine_says_so() -> None:
    """Nothing to do is reported as nothing to do, with no writes at all."""
    db = FakeDatabase([_lesson("a", embed.DIM)])
    before, after, written = reembed.reembed(db)
    assert (before.needed, written, after.needed) == (0, 0, 0)
    assert db.lessons.updates == []


@pytest.mark.parametrize("width", [embed.DIM - 1, embed.DIM + 1, embed.DIM * 2])
def test_any_other_width_is_noticed(width: int) -> None:
    """The check is against the configured width, whatever that width happens to be."""
    result = reembed.plan(FakeDatabase([_lesson("a", width)]))
    assert result.needed == 1


def test_the_same_width_from_another_model_is_not_fine() -> None:
    """Two models of the same width live in different spaces, and comparing across them is nonsense.

    This is the case a width check alone would miss entirely: recall would return confident results
    computed in a vector space the vectors were never in.
    """
    db = FakeDatabase([_lesson("a", embed.DIM, model="BAAI/bge-base-en-v1.5")])
    result = reembed.plan(db)
    assert result.mismatched == 0
    assert result.unstamped == 1
    assert result.ok == 0
    assert "BAAI/bge-base-en-v1.5" in result.samples[0]["reason"]


def test_a_lesson_with_no_recorded_model_is_not_trusted() -> None:
    """An unrecorded vector cannot be proven comparable, so it is rewritten rather than assumed."""
    result = reembed.plan(FakeDatabase([_lesson("a", embed.DIM, model=None)]))
    assert result.unstamped == 1
    assert "no model recorded" in result.samples[0]["reason"]


def test_reembed_rewrites_both_kinds_of_stale_lesson() -> None:
    """A wrong width and an unrecorded model are both brought back into a comparable state."""
    db = FakeDatabase(
        [
            _lesson("width", 768),
            _lesson("model", embed.DIM, model="some/other-model"),
            _lesson("fine", embed.DIM),
        ]
    )
    before, after, written = reembed.reembed(db)
    assert before.needed == 2
    assert written == 2
    assert after.needed == 0
    assert all(doc.get("embedding_model") == embed.MODEL_NAME for doc in db.lessons.docs)
