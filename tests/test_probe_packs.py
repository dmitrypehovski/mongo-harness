"""The instrument audit must travel with the data, not stay behind in the film suite.

A probe that checks the sandbox against ``movies.released`` says nothing about a theatres
collection someone else loaded. A pack therefore declares its own probes, anchored in values that
exist in its data right now, and this pins down how those declarations are built — including the
ones that must be refused rather than quietly skipped.
"""

from __future__ import annotations

from datetime import datetime

import bson
import pytest

from mh import datasets, ruler, scaffold
from mh.ruler import Outcome, Probe


def _lookup(doc: dict, path: str):
    """Follow a dotted path the way MongoDB does, so a fake does not lie about the code."""
    current = doc
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


class _Missing:
    """A sentinel for a path that is not in the document."""


_MISSING = _Missing()


class FakeCollection:
    """Just enough of a collection to answer the one ``find_one`` a probe anchor makes."""

    def __init__(self, doc: dict | None) -> None:
        self.doc = doc

    def find_one(self, query: dict | None = None, projection: dict | None = None) -> dict | None:
        if self.doc is None:
            return None
        for field, want in (query or {}).items():
            if isinstance(want, dict) and "$exists" in want:
                if (field in self.doc or _lookup(self.doc, field) is not _MISSING) != bool(want["$exists"]):
                    return None
            elif _lookup(self.doc, field) != want:
                return None
        return self.doc


class FakeDatabase:
    """A database holding one collection per name given, or missing it entirely."""

    def __init__(self, **collections: dict | None) -> None:
        self.collections: dict[str, FakeCollection] = {
            name: FakeCollection(doc) for name, doc in collections.items()
        }

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self.collections:
            raise KeyError(name)
        return self.collections[name]


class FakeObjectId:
    """Stands in for bson.ObjectId, whose only relevant property here is its text."""

    def __init__(self, text: str) -> None:
        self.text = text

    def __str__(self) -> str:
        return self.text


def test_literal_probe_needs_no_data() -> None:
    """A probe with no anchor is usable as written."""
    probe, problem = ruler.probe_from_spec(
        {"name": "plain", "sugar": "db.a.count({})", "canonical": "db.a.countDocuments({})"},
        FakeDatabase(),
    )
    assert problem == ""
    assert probe is not None
    assert probe.texts(None) == ("db.a.count({})", "db.a.countDocuments({})")


def test_anchored_probe_reads_a_real_value() -> None:
    """The value the probe compares is taken from the database, not typed in once."""
    oid = FakeObjectId("507f1f77bcf86cd799439011")
    db = FakeDatabase(movies={"_id": oid})
    probe, problem = ruler.probe_from_spec(
        {
            "name": "object id",
            "anchor": {"collection": "movies", "field": "_id", "as": "objectid"},
            "sugar": 'db.movies.find({"_id": ObjectId("{{value}}")})',
            "canonical": 'db.movies.find({"_id": {"$oid": "{{value}}"}})',
        },
        db,
    )
    assert problem == ""
    assert probe is not None
    sugar, canonical = probe.texts(db)
    assert "ObjectId(\"507f1f77bcf86cd799439011\")" in sugar
    assert '{"$oid": "507f1f77bcf86cd799439011"}' in canonical
    assert "{{value}}" not in sugar and "{{value}}" not in canonical


def test_anchored_date_probe_renders_iso() -> None:
    """A date anchor is rendered in the spelling both forms of the query can carry."""
    db = FakeDatabase(orders={"placed": datetime(2024, 3, 7, 11, 30, 0)})
    probe, _ = ruler.probe_from_spec(
        {
            "name": "date",
            "anchor": {"collection": "orders", "field": "placed", "as": "date"},
            "sugar": 'db.orders.find({"placed": ISODate("{{value}}")})',
            "canonical": 'db.orders.find({"placed": {"$date": "{{value}}"}})',
        },
        db,
    )
    assert probe is not None
    sugar, _ = probe.texts(db)
    assert "2024-03-07T11:30:00Z" in sugar


@pytest.mark.parametrize(
    "spec",
    [
        {"sugar": "db.a.count({})", "canonical": "db.a.countDocuments({})"},
        {"name": "half", "sugar": "db.a.count({})"},
        {"name": "half", "canonical": "db.a.countDocuments({})"},
    ],
)
def test_probe_without_both_queries_is_refused(spec: dict) -> None:
    """Half a probe is not a probe."""
    probe, problem = ruler.probe_from_spec(spec, FakeDatabase())
    assert probe is None
    assert problem


def test_anchor_without_a_value_is_refused() -> None:
    """An anchor that finds nothing must say so instead of comparing two empty strings."""
    db = FakeDatabase(empty={})
    probe, problem = ruler.probe_from_spec(
        {
            "name": "no value",
            "anchor": {"collection": "empty", "field": "state", "as": "string"},
            "sugar": 'db.empty.find({"state": "{{value}}"})',
            "canonical": 'db.empty.find({"state": {"$eq": "{{value}}"}})',
        },
        db,
    )
    assert probe is None
    assert "no value" in problem.lower()


def test_anchor_on_a_missing_collection_is_refused() -> None:
    """A collection that is not there cannot anchor anything."""
    probe, problem = ruler.probe_from_spec(
        {
            "name": "missing",
            "anchor": {"collection": "nowhere", "field": "x", "as": "string"},
            "sugar": "db.nowhere.find({})",
            "canonical": "db.nowhere.find({})",
        },
        FakeDatabase(),
    )
    assert probe is None
    assert "nowhere" in problem


def test_anchor_must_name_its_field() -> None:
    """An anchor with nowhere to look is refused with a reason."""
    probe, problem = ruler.probe_from_spec(
        {"name": "vague", "anchor": {"collection": "movies"}, "sugar": "a", "canonical": "b"},
        FakeDatabase(movies={}),
    )
    assert probe is None
    assert "anchor" in problem.lower()


def test_unfilled_placeholder_is_refused() -> None:
    """A template that would ship with a hole in it is refused."""
    db = FakeDatabase(movies={"state": "MN"})
    probe, problem = ruler.probe_from_spec(
        {
            "name": "hole",
            "anchor": {"collection": "movies", "field": "state", "as": "string"},
            "sugar": 'db.movies.find({"state": "{{value}}"})',
            "canonical": 'db.movies.find({"state": "{{filled}}"})',
        },
        db,
    )
    assert probe is None
    assert "empty" in problem


def test_probes_from_spec_separates_the_usable_from_the_rest() -> None:
    """A pack with one good and one broken probe yields one probe and one reason."""
    db = FakeDatabase(orders={"state": "MN"})
    probes, problems = ruler.probes_from_spec(
        [
            {
                "name": "good",
                "anchor": {"collection": "orders", "field": "state", "as": "string"},
                "sugar": 'db.orders.find({"state": "{{value}}"})',
                "canonical": 'db.orders.find({"state": {"$eq": "{{value}}"}})',
            },
            {"name": "broken", "sugar": "where is the canonical one"},
        ],
        db,
    )
    assert [probe.name for probe in probes] == ["good"]
    assert len(problems) == 1


def test_pack_validation_refuses_a_malformed_probe() -> None:
    """A pack that cannot be audited properly must not pass validation silently."""
    pack = datasets.Pack(
        name="x",
        database="x",
        tasks=[
            {"id": "a", "question": "q", "reference": "db.c.countDocuments({})", "split": "train", "collection": "c"},
            {"id": "b", "question": "q", "reference": "db.c.countDocuments({})", "split": "holdout", "collection": "c"},
        ],
        audit_probes=[{"name": "half", "sugar": "db.c.countDocuments({})"}],
    )
    problems = datasets.validate(pack)
    assert any("canonical" in problem for problem in problems)


def test_scaffold_writes_probes_for_its_own_data() -> None:
    """The exam generator declares an audit for the collections it just asked about."""
    db = FakeDatabase(
        theaters={
            "_id": bson.ObjectId("65f1c2d3e4b0a1a2b3c4d5e6"),
            "theaterId": 1000,
            "location": {"address": {"state": "MN"}},
            "name": "St. Anthony Main",
        }
    )
    specs = scaffold.audit_probes_for(db, ["theaters"])
    names = [spec["name"] for spec in specs]
    assert any("object id" in name for name in names), names
    assert any("equality" in name for name in names), names

    probes, problems = ruler.probes_from_spec(specs, db)
    assert problems == []
    assert len(probes) == len(specs)
    for probe in probes:
        sugar, canonical = probe.texts(db)
        assert "{{value}}" not in sugar and "{{value}}" not in canonical
        assert sugar != canonical


def test_scaffold_skips_collections_it_cannot_read() -> None:
    """A collection that cannot be sampled is skipped, and the rest still get probes."""
    db = FakeDatabase(theaters={"name": "Somewhere"})
    specs = scaffold.audit_probes_for(db, ["absent", "theaters"])
    assert all("absent" not in spec["name"] for spec in specs)
    assert any("theaters" in spec["name"] for spec in specs)


def test_report_says_when_only_refusals_were_checked() -> None:
    """An audit with no equivalence probes must not read as a full clean bill of health."""
    policy = [Outcome(Probe(name="write refused", kind="policy", note=""), "refused", "ok")]
    text = ruler.report(policy)
    assert "no equivalence probes" in text


def test_policy_probes_are_always_run() -> None:
    """Dataset-independent checks cannot be switched off by a pack that declares nothing."""
    _, text = ruler.run(FakeDatabase(), probes=[])
    assert "write" in text.lower()
