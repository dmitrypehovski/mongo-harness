"""Tests for the ruler audit.

Two layers. The first needs no database and guards the detector itself: the fault
injection must really break the parser, otherwise a green audit proves nothing. The
second runs the audit against a loaded ``sample_mflix`` and skips when there is no
database to audit.
"""

from __future__ import annotations

import pytest

from mh import ruler, scorer

SUGAR_REGEX = 'db.movies.find({"title": /the/i}, {"title": 1}).limit(1)'
SUGAR_OID = 'db.comments.find({"movie_id": ObjectId("573a1390f29313caabcd4323")}).limit(1)'


# --- the detector, with no database -----------------------------------------


def test_the_regex_rewrite_can_be_switched_off_and_back():
    """The injection must change behaviour, or the audit could never fail."""
    original = scorer._regex_literals
    try:
        ruler.inject_fault("regex")
        with pytest.raises(scorer.ParseError):
            scorer.parse_mql(SUGAR_REGEX)
    finally:
        scorer._regex_literals = original
    assert scorer.parse_mql(SUGAR_REGEX).method == "find"


def test_the_identifier_rewrite_can_be_switched_off_and_back():
    original = scorer._JS_CALLS
    try:
        ruler.inject_fault("oid")
        with pytest.raises(scorer.ParseError):
            scorer.parse_mql(SUGAR_OID)
    finally:
        scorer._JS_CALLS = original
    assert scorer.parse_mql(SUGAR_OID).method == "find"


def test_an_unknown_fault_is_refused():
    with pytest.raises(ValueError):
        ruler.inject_fault("a-fault-that-does-not-exist")


def test_both_spellings_of_every_static_probe_parse():
    """The sugar form must never be refused where the strict form is accepted."""
    static = [p for p in ruler.EQUIVALENCE_PROBES if p.build is None]
    assert static
    for probe in static:
        assert scorer.parse_mql(probe.sugar) is not None
        assert scorer.parse_mql(probe.canonical) is not None


def test_every_policy_probe_is_caught_without_touching_the_database():
    """A policy probe is either unparseable or carries a blocked operator."""
    assert ruler.POLICY_PROBES
    for probe in ruler.POLICY_PROBES:
        try:
            mql = scorer.parse_mql(probe.sugar)
        except scorer.ParseError:
            continue
        found = scorer.find_blocked({"args": mql.args, "chain": [value for _, value in mql.chain]})
        assert found, f"{probe.name} was neither refused nor blocked"


def test_the_report_names_the_defect_it_found():
    broken = ruler.Outcome(
        probe=ruler.EQUIVALENCE_PROBES[0], verdict="diverges", detail="two spellings disagree"
    )
    honest = ruler.Outcome(probe=ruler.POLICY_PROBES[0], verdict="refused", detail="blocked")
    text = ruler.report([broken, honest])
    assert "The instrument is lying" in text
    assert "two spellings disagree" in text
    assert '"defects": 1' in text


def test_the_report_is_quiet_when_everything_agrees():
    clean = [ruler.Outcome(probe=p, verdict="agrees", detail="identical") for p in ruler.EQUIVALENCE_PROBES]
    text = ruler.report(clean)
    assert "The instrument agrees with the database" in text
    assert ruler.defects(clean) == []


# --- the audit against a real dataset ---------------------------------------


@pytest.fixture(scope="module")
def sample_db():
    """A live sample_mflix, or a skip: this layer is about the data, not the code."""
    try:
        db = ruler.connection()
        db.client.admin.command("ping")
    except Exception as exc:  # no server, no credentials, no network
        pytest.skip(f"no MongoDB reachable: {exc}")
    if db.movies.estimated_document_count() == 0:
        pytest.skip("sample_mflix is not loaded")
    return db


def test_the_audit_passes_on_the_current_parser(sample_db):
    outcomes = ruler.audit(sample_db)
    assert ruler.defects(outcomes) == []
    assert len(outcomes) == len(ruler.EQUIVALENCE_PROBES) + len(ruler.POLICY_PROBES)


def test_the_audit_catches_the_defect_that_cost_us_the_most(sample_db):
    """Disabled regex rewriting is the bug that made 38 answers look like failures."""
    original = scorer._regex_literals
    try:
        ruler.inject_fault("regex")
        outcomes = ruler.audit(sample_db)
    finally:
        scorer._regex_literals = original
    caught = [o for o in ruler.defects(outcomes) if "regex" in o.probe.name]
    assert len(caught) >= 3, f"the audit missed the historical defect: {caught}"
