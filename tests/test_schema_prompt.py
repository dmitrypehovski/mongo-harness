"""The agent must be told about the data it has, not about the films this repository ships.

Pointed at an unfamiliar database with the film description, the agent answered "there is no orders
collection here" and once invented a query over movies. These tests hold both halves of the fix:
a description read out of the data, and the shipped description kept byte for byte so the numbers
already measured with it stay comparable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import bson
import pytest

from mh import agent, schema, tasks


class FakeCursor:
    """The one method ``schema`` uses on a cursor."""

    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents

    def limit(self, count: int) -> list[dict]:
        return self.documents[:count]


class FakeCollection:
    """A collection that hands back the documents it was given."""

    def __init__(self, documents: list[dict] | None, broken: bool = False) -> None:
        self.documents = documents or []
        self.broken = broken

    def find(self, query: dict | None = None) -> FakeCursor:
        if self.broken:
            raise RuntimeError("cannot read this collection")
        return FakeCursor(self.documents)


class FakeDatabase:
    """A database holding named collections."""

    def __init__(self, **collections: Any) -> None:
        self.collections: dict[str, FakeCollection] = collections

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self.collections:
            raise KeyError(name)
        return self.collections[name]

    def list_collection_names(self) -> list[str]:
        return sorted(self.collections)


FILM_WORDS = ("sample_mflix", "movies", "comments", "theaters")


def test_shipped_questions_keep_the_shipped_description() -> None:
    """Byte for byte, so the rates already in the record stay comparable with the same apparatus."""
    tasks.reset_pack()
    assert agent.schema_text(FakeDatabase()) == agent.SCHEMA_TEXT


def test_a_pack_gets_a_description_of_its_own_data() -> None:
    """The prompt describes the collections the pack asks about, not the films."""
    db = FakeDatabase(
        orders=FakeCollection(
            [
                {
                    "_id": bson.ObjectId("507f1f77bcf86cd799439011"),
                    "item": "Flat white",
                    "qty": 2,
                    "placed": datetime(2024, 5, 1, 7, 30, 0),
                }
            ]
        )
    )
    tasks.use_pack(
        [
            {
                "id": "g01",
                "collection": "orders",
                "split": "train",
                "question": "How many orders?",
                "reference": "db.orders.countDocuments({})",
            }
        ],
        database="cafe",
        name="cafe",
    )
    text = agent.schema_text(db)
    assert "cafe" in text
    assert "collection orders" in text
    assert "item" in text
    assert "placed" in text
    for word in FILM_WORDS:
        assert word not in text, f"the film word {word!r} is still in the prompt"


def test_without_a_database_it_still_names_the_collections() -> None:
    """The description degrades to something true rather than to the film schema."""
    tasks.use_pack(
        [
            {
                "id": "g01",
                "collection": "orders",
                "split": "train",
                "question": "How many orders?",
                "reference": "db.orders.countDocuments({})",
            }
        ],
        database="cafe",
        name="cafe",
    )
    text = agent.schema_text(None)
    assert "cafe" in text and "orders" in text
    assert "movies" not in text


def test_a_broken_database_falls_back_instead_of_raising() -> None:
    """A description that cannot be built must not stop the measurement."""
    tasks.use_pack(
        [
            {
                "id": "g01",
                "collection": "orders",
                "split": "train",
                "question": "How many orders?",
                "reference": "db.orders.countDocuments({})",
            }
        ],
        database="cafe",
        name="cafe",
    )
    text = agent.schema_text(FakeDatabase(orders=FakeCollection([], broken=True)))
    assert "cafe" in text


@pytest.fixture(autouse=True)
def _restore_pack() -> Any:
    """Every test starts from the shipped suite, whatever the previous one did."""
    tasks.reset_pack()
    yield
    tasks.reset_pack()


def test_describe_names_fields_types_and_nesting() -> None:
    """A nested field is described by its path, because that is how it is queried."""
    db = FakeDatabase(
        orders=FakeCollection(
            [
                {"_id": bson.ObjectId("507f1f77bcf86cd799439011"), "location": {"city": "Berlin"}},
                {"_id": bson.ObjectId("507f1f77bcf86cd799439012"), "location": {"city": "Berlin"}},
            ]
        )
    )
    text = schema.describe(db, "cafe", ["orders"])
    assert "Database: cafe" in text
    assert "location.city" in text
    assert "string" in text


def test_describe_reports_absent_fields() -> None:
    """A field that is sometimes missing is called out: assuming it is always there is a bug."""
    db = FakeDatabase(
        orders=FakeCollection([{"item": "Flat white", "note": "no foam"}, {"item": "Filter"}])
    )
    text = schema.describe(db, "cafe", ["orders"])
    assert "absent in 1 of 2" in text


def test_describe_reports_numeric_ranges() -> None:
    """Ranges tell a model what a plausible filter is."""
    db = FakeDatabase(orders=FakeCollection([{"qty": 1}, {"qty": 3}]))
    text = schema.describe(db, "cafe", ["orders"])
    assert "ranges 1..3" in text


def test_describe_an_empty_collection_says_so() -> None:
    """An empty collection is described as empty, not as a schema with no fields."""
    text = schema.describe(FakeDatabase(orders=FakeCollection([])), "cafe", ["orders"])
    assert "empty" in text


def test_describe_reports_a_collection_it_cannot_read() -> None:
    """An unreadable collection is named, and the rest of the description still gets built."""
    db = FakeDatabase(orders=FakeCollection([], broken=True), menu=FakeCollection([{"name": "Filter"}]))
    text = schema.describe(db, "cafe", ["orders", "menu"])
    assert "could not be read" in text
    assert "collection menu" in text


def test_describe_lists_collections_when_none_are_named() -> None:
    """With nothing named, the description falls back to what the database holds."""
    db = FakeDatabase(menu=FakeCollection([{"name": "Filter"}]))
    text = schema.describe(db, "cafe", [])
    assert "menu" in text
