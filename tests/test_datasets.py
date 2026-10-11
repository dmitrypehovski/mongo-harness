"""Dataset packs: the format that lets this harness run on data that is not sample_mflix."""

from __future__ import annotations

import json

import pytest

from mh import datasets


def pack_dict(**overrides) -> dict:
    """A small, sound pack, with individual fields replaceable per test."""
    payload = {
        "name": "example",
        "database": "example_db",
        "description": "two questions about theatres",
        "tasks": [
            {
                "id": "t01",
                "family": "find",
                "split": "train",
                "collection": "theaters",
                "question": "How many theatres are in California?",
                "reference": 'db.theaters.countDocuments({"location.address.state": "CA"})',
            },
            {
                "id": "t02",
                "family": "aggregate",
                "split": "holdout",
                "collection": "theaters",
                "question": "How many theatres are in New York?",
                "reference": 'db.theaters.countDocuments({"location.address.state": "NY"})',
            },
        ],
    }
    payload.update(overrides)
    return payload


def write_pack(tmp_path, payload: dict):
    """Write a pack to a temporary file and hand back its path."""
    location = tmp_path / "pack.json"
    location.write_text(json.dumps(payload), encoding="utf-8")
    return location


def test_a_sound_pack_loads_and_summarises(tmp_path):
    pack = datasets.load(write_pack(tmp_path, pack_dict()))
    assert pack.name == "example"
    assert pack.database == "example_db"
    assert datasets.validate(pack) == []
    summary = pack.summary()
    assert summary["tasks"] == 2
    assert summary["splits"] == {"train": 1, "holdout": 1}
    assert summary["collections"] == ["theaters"]


def test_a_pack_without_a_verification_split_is_rejected(tmp_path):
    payload = pack_dict()
    for task in payload["tasks"]:
        task["split"] = "train"
    location = write_pack(tmp_path, payload)
    with pytest.raises(ValueError, match="holdout"):
        datasets.load(location)


def test_a_pack_with_a_duplicate_id_is_rejected(tmp_path):
    payload = pack_dict()
    payload["tasks"][1]["id"] = "t01"
    with pytest.raises(ValueError, match="duplicate id"):
        datasets.load(write_pack(tmp_path, payload))


def test_a_pack_whose_reference_is_not_a_query_is_rejected(tmp_path):
    payload = pack_dict()
    payload["tasks"][0]["reference"] = "SELECT * FROM theaters"
    with pytest.raises(ValueError, match="db.<collection>"):
        datasets.load(write_pack(tmp_path, payload))


def test_the_built_in_suite_satisfies_its_own_rules():
    """The rules a pack is held to are the rules the shipped suite already follows."""
    from mh import tasks

    pack = datasets.Pack(name="mflix", tasks=list(tasks.TASKS), database="sample_mflix")
    assert datasets.validate(pack) == []
