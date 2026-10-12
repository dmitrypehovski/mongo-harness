"""Lesson recall must stay inside the question set it was learned on.

A lesson learned on one dataset is not advice for another: "watch the year field" means nothing
about theatres. These tests pin down that the restriction is expressed where it actually works —
inside the ``$vectorSearch`` stage, and in the local cosine fallback — not in a ``$match`` that runs
after the ranking and quietly returns fewer hits than asked for.
"""

from __future__ import annotations

from typing import Iterator

import pytest

from mh import store, tasks


class FakeCollection:
    """Enough of a pymongo collection to answer ``find`` over plain dicts."""

    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs

    def find(self, query: dict):  # noqa: ANN201 - mirrors pymongo's shape
        return [doc for doc in self.docs if self._matches(doc, query)]

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        for key, want in query.items():
            if isinstance(want, dict):
                if "$exists" in want:
                    present = key in doc
                    if present != bool(want["$exists"]):
                        return False
                if "$ne" in want and doc.get(key) == want["$ne"]:
                    return False
            elif key == "dataset.key":
                if (doc.get("dataset") or {}).get("key") != want:
                    return False
            elif doc.get(key) != want:
                return False
        return True


class FakeDatabase:
    """A database whose only collection is ``lessons``."""

    def __init__(self, lessons: list[dict]) -> None:
        self.lessons = FakeCollection(lessons)

    def __getitem__(self, name: str) -> FakeCollection:
        assert name == "lessons"
        return self.lessons


def _lesson(key: str | None, text: str, embedding: list[float]) -> dict:
    doc = {"question": text, "embedding": embedding}
    if key is not None:
        doc["dataset"] = {"key": key, "questions": 3, "name": key}
    return doc


def test_vector_search_stage_filters_inside_the_stage() -> None:
    """The data scope is filtered during the search, not after it."""
    stage = store.vector_search_stage([1.0, 0.0], k=4, dataset_key="theaters")
    assert stage["filter"] == {"dataset.key": "theaters"}
    assert stage["limit"] == 4


def test_vector_search_stage_has_no_filter_without_a_dataset() -> None:
    """Calling it without a key searches everything, as before."""
    assert "filter" not in store.vector_search_stage([1.0, 0.0], k=4)


def test_index_declares_the_filter_field() -> None:
    """Atlas only allows filtering on fields the index knows about."""
    paths = [field.get("path") for field in store.vector_index_spec()["definition"]["fields"]]
    assert "dataset.key" in paths, paths


def test_index_still_searches_the_embedding() -> None:
    """The vector field comes first and keeps its shape."""
    first = store.vector_index_spec()["definition"]["fields"][0]
    assert first["type"] == "vector"
    assert first["path"] == "embedding"
    assert first["numDimensions"] == 384


def test_local_recall_skips_other_datasets() -> None:
    """A question from one set never recalls another set's memory."""
    db = FakeDatabase(
        [
            _lesson("sample_mflix", "film lesson", [1.0, 0.0]),
            _lesson("theaters", "theatre lesson", [1.0, 0.0]),
        ]
    )
    hits = store._vector_search_local([1.0, 0.0], k=5, database=db, dataset_key="theaters")
    assert [hit["question"] for hit in hits] == ["theatre lesson"]


def test_local_recall_without_a_key_still_sees_everything() -> None:
    """Unscoped recall is unchanged, so existing callers keep working."""
    db = FakeDatabase(
        [
            _lesson("sample_mflix", "film lesson", [1.0, 0.0]),
            _lesson("theaters", "theatre lesson", [1.0, 0.0]),
        ]
    )
    hits = store._vector_search_local([1.0, 0.0], k=5, database=db)
    assert len(hits) == 2


def test_local_recall_ignores_unstamped_lessons_when_scoped() -> None:
    """A lesson with no stamp cannot be proven to belong, so a scoped search does not use it."""
    db = FakeDatabase([_lesson(None, "from nowhere", [1.0, 0.0])])
    assert store._vector_search_local([1.0, 0.0], k=5, database=db, dataset_key="theaters") == []


@pytest.fixture(autouse=True)
def _restore_pack() -> Iterator[None]:
    """Whatever a test does to the active question set, the next one starts from the shipped suite."""
    yield
    tasks.reset_pack()


def test_identity_describes_the_data_and_the_questions() -> None:
    """The stamp names what the questions are about, and which wording produced them."""
    identity = store.dataset_identity()
    assert identity["key"] == tasks.pack_scope()
    assert identity["pack"] == tasks.pack_key()
    assert identity["questions"] == len(tasks.TASKS)
    assert identity["collections"] == tasks.pack_collections()
    assert identity["generated"] is False


def test_scope_survives_regenerating_the_exam() -> None:
    """Rewording a question set over the same data must not orphan its memory."""
    first = [
        {
            "id": "x01",
            "collection": "theaters",
            "split": "train",
            "question": "How many theaters?",
            "reference": 'db.theaters.countDocuments({})',
        }
    ]
    regenerated = [dict(first[0], id="x09", question="Count the theater records.", reference='db.theaters.countDocuments({})')]

    tasks.use_pack(first, database="sample_mflix", name="theaters")
    scope, fingerprint = tasks.pack_scope(), tasks.pack_key()
    tasks.use_pack(regenerated, database="sample_mflix", name="theaters")
    assert tasks.pack_scope() == scope, "the data did not change, so the scope must not"
    assert tasks.pack_key() != fingerprint, "the wording did change, so the fingerprint must"


def test_scope_separates_different_data() -> None:
    """The same questions pointed at other collections are a different scope."""
    on_theaters = [
        {
            "id": "y01",
            "collection": "theaters",
            "split": "train",
            "question": "How many theaters?",
            "reference": 'db.theaters.countDocuments({})',
        }
    ]
    on_movies = [dict(on_theaters[0], id="y02", collection="movies")]
    tasks.use_pack(on_theaters, database="sample_mflix", name="a")
    theaters_scope = tasks.pack_scope()
    tasks.use_pack(on_movies, database="sample_mflix", name="b")
    assert tasks.pack_scope() != theaters_scope


def test_scope_separates_different_databases() -> None:
    """The same collection name in two databases is two different scopes."""
    task = {
        "id": "z01",
        "collection": "orders",
        "split": "train",
        "question": "How many orders?",
        "reference": 'db.orders.countDocuments({})',
    }
    tasks.use_pack([task], database="shop", name="shop")
    shop = tasks.pack_scope()
    tasks.use_pack([task], database="warehouse", name="warehouse")
    assert tasks.pack_scope() != shop


def test_identity_marks_generated_questions() -> None:
    """A pack's questions are recorded as generated, the shipped suite is not."""
    tasks.use_pack(
        [
            {
                "id": "w01",
                "collection": "theaters",
                "split": "train",
                "question": "How many theaters?",
                "reference": 'db.theaters.countDocuments({})',
            }
        ],
        database="sample_mflix",
        name="theaters",
    )
    identity = store.dataset_identity()
    assert identity["generated"] is True
    assert identity["name"] == "theaters"
    assert identity["collections"] == ["theaters"]


def test_recall_ranks_by_similarity_before_cutting() -> None:
    """The filter must not disturb the ordering it is filtering."""
    db = FakeDatabase(
        [
            _lesson("theaters", "near", [1.0, 0.0]),
            _lesson("theaters", "far", [0.0, 1.0]),
        ]
    )
    hits = store._vector_search_local([1.0, 0.0], k=1, database=db, dataset_key="theaters")
    assert [hit["question"] for hit in hits] == ["near"]
    assert hits[0]["score"] > 0.9


@pytest.mark.parametrize("key", ["sample_mflix", "theaters", "generated:7"])
def test_every_provenance_is_accepted(key: str) -> None:
    """Film, generated and custom packs all stamp themselves the same way."""
    db = FakeDatabase([_lesson(key, "only one", [1.0, 0.0])])
    assert len(store._vector_search_local([1.0, 0.0], k=3, database=db, dataset_key=key)) == 1
