"""An index that does not match the code must be reported, not discovered as an empty search.

The width is the case worth pinning down: an index built for one model refuses every vector another
model produces, and the symptom is a search that returns nothing rather than an error. The filter
field is the other: filtering on a field the index does not know is refused outright.
"""

from __future__ import annotations

from mh import embed, store


def _definition(**overrides) -> dict:
    """The index definition this code produces, with pieces altered for a test."""
    definition = store.vector_index_spec()["definition"]
    definition = {"fields": [dict(field) for field in definition["fields"]]}
    for path, change in overrides.items():
        for field in definition["fields"]:
            if field.get("path") == path:
                field.update(change)
    return definition


def test_the_codes_own_spec_matches_itself() -> None:
    """Self-consistency, so the comparison cannot be called broken by a false positive."""
    assert store.index_differences(_definition(), _definition()) == []


def test_a_width_difference_is_reported() -> None:
    """The exact failure a switch of embedding model produces."""
    current = _definition(embedding={"numDimensions": embed.DIM * 2})
    problems = store.index_differences(current, _definition())
    assert problems
    assert any("numDimensions" in problem for problem in problems)


def test_a_missing_filter_field_is_reported() -> None:
    """An index that does not know dataset.key refuses a filtered search."""
    current = {"fields": [field for field in _definition()["fields"] if field["path"] != "dataset.key"]}
    problems = store.index_differences(current, _definition())
    assert any("dataset.key" in problem and "missing" in problem for problem in problems)


def test_an_unwanted_extra_field_is_reported() -> None:
    """A field the code no longer uses is still a difference, and it is named."""
    current = _definition()
    current["fields"].append({"type": "filter", "path": "leftover.field"})
    problems = store.index_differences(current, _definition())
    assert any("leftover.field" in problem for problem in problems)


def test_a_similarity_change_is_reported() -> None:
    """Cosine and euclidean rank differently, so a change of metric is a difference."""
    problems = store.index_differences(
        _definition(embedding={"similarity": "euclidean"}), _definition()
    )
    assert any("similarity" in problem for problem in problems)


def test_an_empty_definition_is_reported_rather_than_crashing() -> None:
    """A missing definition is a difference, not an exception."""
    problems = store.index_differences(None, _definition())
    assert any("embedding" in problem for problem in problems)
    assert store.index_differences(None, None) == []
