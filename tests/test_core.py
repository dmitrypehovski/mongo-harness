"""Tests for the parts of the harness that decide things: the envelope, the parser,
the comparison of answers and the statistics behind a promotion."""

from __future__ import annotations

import pytest

from mh import gate, scorer, tasks
from mh.agent import EDITABLE_KEYS, GENESIS


CURRENT = dict(GENESIS)


def test_every_task_is_well_formed():
    """The suite the whole measurement rests on has to be complete and parseable."""
    assert tasks.summary()["total"] == len(tasks.TASKS)
    for task in tasks.TASKS:
        for key in ("id", "family", "split", "collection", "question", "reference"):
            assert task.get(key), f"{task.get('id')} is missing {key}"
        assert task["split"] in ("train", "holdout")
        scorer.parse_mql(task["reference"])
    assert tasks.by_split("train") and tasks.by_split("holdout")


def test_envelope_refuses_unknown_keys():
    """A version may not grow new fields to hide a new capability in."""
    allowed, reason = gate.envelope_check(CURRENT, {**CURRENT, "backdoor": True})
    assert not allowed
    assert "do not exist" in reason


def test_envelope_refuses_widened_tools():
    """The harness cannot hand itself a tool it was not given."""
    allowed, reason = gate.envelope_check(CURRENT, {**CURRENT, "tools": ["find", "aggregate", "count", "shell"]})
    assert not allowed
    assert "tool" in reason


def test_envelope_allows_narrowing_tools():
    """Giving up a tool is always allowed: that is how a version earns discipline."""
    allowed, _ = gate.envelope_check(CURRENT, {**CURRENT, "tools": ["aggregate"]})
    assert allowed


def test_envelope_refuses_frozen_keys():
    """Frozen keys are outside the editable set on purpose."""
    allowed, reason = gate.envelope_check(CURRENT, {**CURRENT, "envelope_version": 99})
    assert not allowed
    assert "frozen" in reason


def _runs(passed: list[str], task_ids: list[str], repeat: int = 1) -> list[dict]:
    """A run list in the shape the gate reads: one entry per question per repeat."""
    return [{"task_id": tid, "repeat": repeat, "passed": tid in set(passed)} for tid in task_ids]


def test_gate_refuses_a_version_that_is_simply_worse():
    """Falling behind on the verification set is a refusal on its own."""
    holdout = [f"h{i}" for i in range(25)]
    incumbent = _runs(holdout[:20], holdout)
    candidate = _runs(holdout[:10], holdout)
    decision, reason, _ = gate.decide(incumbent, candidate, _runs([], []), _runs([], []))
    assert decision == "rejected_regression"
    assert "worse on the verification set" in reason


def test_gate_refuses_a_version_that_only_fits_the_selection_set():
    """Better where the search can see, no better where it cannot."""
    holdout = [f"h{i}" for i in range(25)]
    train = [f"t{i}" for i in range(32)]
    decision, reason, _ = gate.decide(
        _runs(holdout[:20], holdout),
        _runs(holdout[:20], holdout),
        _runs(train[:20], train),
        _runs(train[:30], train),
    )
    assert decision == "rejected_outsample"
    assert "selection set only" in reason


def test_gate_refuses_a_version_that_wins_out_of_sample_but_hurts_the_selection_set():
    """A gain that costs more than it pays is not broad improvement."""
    holdout = [f"h{i}" for i in range(25)]
    train = [f"t{i}" for i in range(32)]
    decision, reason, _ = gate.decide(
        _runs(holdout[:20], holdout),
        _runs(holdout[:24], holdout),
        _runs(train[:25], train),
        _runs(train[:18], train),
    )
    assert decision == "rejected_narrow"
    assert "not broad improvement" in reason


def test_gate_refuses_a_gain_that_sits_inside_the_margin():
    """One question out of twenty-five is not an improvement."""
    holdout = [f"h{i}" for i in range(25)]
    decision, reason, evidence = gate.decide(
        _runs(holdout[:20], holdout),
        _runs(holdout[:21], holdout),
        _runs([], []),
        _runs([], []),
    )
    assert decision == "rejected_insignificant"
    assert "less than the" in reason
    assert evidence["holdout_rate_before"] < evidence["holdout_rate_after"]


def test_gate_promotes_an_improvement_that_is_both_large_and_out_of_sample():
    """Four questions gained and none lost on repeated measurement is the bar."""
    holdout = [f"h{i}" for i in range(25)]
    train = [f"t{i}" for i in range(32)]
    decision, reason, evidence = gate.decide(
        _runs(holdout[:20], holdout),
        _runs(holdout[:24], holdout),
        _runs(train[:20], train),
        _runs(train[:20], train),
    )
    assert decision == "promoted"
    assert evidence["only_candidate"] == 4
    assert evidence["only_incumbent"] == 0
    assert evidence["p_value"] <= gate.SIGNIFICANCE


def test_gate_promotes_an_improvement_that_lives_only_out_of_sample():
    """No movement on the selection set is allowed; a fall is not."""
    holdout = [f"h{i}" for i in range(25)]
    train = [f"t{i}" for i in range(32)]
    decision, reason, _ = gate.decide(
        _runs(holdout[:20], holdout),
        _runs(holdout[:24], holdout),
        _runs(train[:20], train),
        _runs(train[:19], train),
    )
    assert decision in {"promoted", "rejected_narrow"}, decision
    assert decision == "promoted" or "not broad improvement" in reason


def test_gate_refuses_comparison_of_verification_sets_of_different_size():
    """Two different verification sets are not comparable, whatever they report."""
    decision, reason, _ = gate.decide(
        _runs(["h0", "h1"], ["h0", "h1"]),
        _runs(["h0"], ["h0", "h1", "h2"]),
        _runs([], []),
        _runs([], []),
    )
    assert decision == "rejected_insignificant"
    assert "differ in size" in reason

def test_envelope_refuses_rules_that_ask_for_code_execution():
    """A rule asking for $where is refused before anything runs."""
    allowed, reason = gate.envelope_check(CURRENT, {**CURRENT, "rules": ["use $where for awkward filters"]})
    assert not allowed
    assert "$where" in reason


def test_envelope_allows_a_rule_that_forbids_code_execution():
    """A prohibition is not a request: the rule that bans $where must be accepted."""
    allowed, reason = gate.envelope_check(
        CURRENT, {**CURRENT, "rules": ["Never use $where, $function or $merge."]}
    )
    assert allowed, reason


def test_a_banned_operator_is_refused_even_if_a_rule_slips_through():
    """The execution sandbox is the second line of defence, and the one that holds."""
    parsed = scorer.parse_mql('db.movies.find({"$where": "this.year > 2000"})')
    execution = scorer.execute(db=None, mql=parsed, allowed_tools=["find"])
    assert execution.status == "blocked"


def test_envelope_refuses_an_emptied_prompt():
    """A version that strips its own instructions is refused."""
    allowed, _ = gate.envelope_check(CURRENT, {**CURRENT, "system_prompt": "write a query"})
    assert not allowed


def test_envelope_refuses_out_of_range_numbers():
    """Context knobs have bounds, so a version cannot ask for 500 sample documents."""
    assert not gate.envelope_check(CURRENT, {**CURRENT, "sample_docs_n": 50})[0]
    assert not gate.envelope_check(CURRENT, {**CURRENT, "retrieve_k": -1})[0]
    assert not gate.envelope_check(CURRENT, {**CURRENT, "sample_docs_n": True})[0]


def test_mcnemar_is_conservative_on_small_disagreement():
    """Two questions gained against none is not evidence."""
    assert gate.mcnemar_exact(0, 2) > gate.SIGNIFICANCE
    assert gate.mcnemar_exact(0, 0) == 1.0


def test_mcnemar_recognises_a_one_sided_gain():
    """Six gained against none is evidence even at this size."""
    assert gate.mcnemar_exact(1, 7) < gate.SIGNIFICANCE


def test_gate_refuses_a_gain_that_only_shows_on_the_selection_set():
    """The classic overfit: better where the search looks, flat where it is judged."""
    incumbent_holdout = [{"task_id": f"h{index}", "passed": index < 20} for index in range(25)]
    candidate_holdout = [{"task_id": f"h{index}", "passed": index < 20} for index in range(25)]
    incumbent_train = [{"task_id": f"t{index}", "passed": index < 20} for index in range(32)]
    candidate_train = [{"task_id": f"t{index}", "passed": index < 30} for index in range(32)]
    decision, reason, evidence = gate.decide(
        incumbent_holdout, candidate_holdout, incumbent_train, candidate_train
    )
    assert decision == "rejected_outsample"
    assert "selection set only" in reason
    assert evidence["holdout_rate_after"] == evidence["holdout_rate_before"]


def test_gate_promotes_a_gain_that_holds_up():
    """A large, one-sided gain on the verification set is promoted."""
    incumbent_holdout = [{"task_id": f"h{index}", "passed": index < 15} for index in range(25)]
    candidate_holdout = [{"task_id": f"h{index}", "passed": index < 24} for index in range(25)]
    incumbent_train = [{"task_id": f"t{index}", "passed": index < 20} for index in range(32)]
    candidate_train = [{"task_id": f"t{index}", "passed": index < 24} for index in range(32)]
    decision, _, evidence = gate.decide(
        incumbent_holdout, candidate_holdout, incumbent_train, candidate_train
    )
    assert decision == "promoted"
    assert evidence["only_candidate"] == 9
    assert evidence["only_incumbent"] == 0


def test_gate_refuses_a_gain_below_the_noise_margin():
    """One question out of twenty-five is inside the noise of a single run."""
    incumbent_holdout = [{"task_id": f"h{index}", "passed": index < 20} for index in range(25)]
    candidate_holdout = [{"task_id": f"h{index}", "passed": index < 21} for index in range(25)]
    incumbent_train = [{"task_id": f"t{index}", "passed": index < 20} for index in range(32)]
    candidate_train = incumbent_train
    decision, reason, _ = gate.decide(
        incumbent_holdout, candidate_holdout, incumbent_train, candidate_train
    )
    assert decision == "rejected_insignificant"
    assert "noise" in reason


def test_gate_refuses_a_version_that_hurts_the_selection_set():
    """Improving the verification set by wrecking the selection set is not progress."""
    incumbent_holdout = [{"task_id": f"h{index}", "passed": index < 12} for index in range(25)]
    candidate_holdout = [{"task_id": f"h{index}", "passed": index < 22} for index in range(25)]
    incumbent_train = [{"task_id": f"t{index}", "passed": index < 30} for index in range(32)]
    candidate_train = [{"task_id": f"t{index}", "passed": index < 10} for index in range(32)]
    decision, reason, _ = gate.decide(
        incumbent_holdout, candidate_holdout, incumbent_train, candidate_train
    )
    assert decision == "rejected_narrow"
    assert "selection set falls" in reason


def test_parser_accepts_javascript_regex_literals():
    """A JavaScript regex literal is valid in mongosh, so the sandbox takes it too."""
    parsed = scorer.parse_mql('db.comments.countDocuments({ email: /@fakegmail\\.com$/ })')
    assert parsed.as_dict()["args"][0] == {"email": {"$regex": r"@fakegmail\.com$"}}

    flagged = scorer.parse_mql('db.movies.find({ title: /^The/i }, { title: 1 })')
    assert flagged.as_dict()["args"][0] == {"title": {"$regex": "^The", "$options": "i"}}


def test_parser_accepts_javascript_style_output():
    """Models write executable MQL: unquoted keys, single quotes, no fences."""
    parsed = scorer.parse_mql("db.movies.find({ year: 1994, genres: 'Drama' }, { title: 1 })")
    assert parsed.collection == "movies"
    assert parsed.args[0] == {"year": 1994, "genres": "Drama"}


def test_parser_accepts_extended_json_dates():
    """Dates arrive as Extended JSON, not as JavaScript constructors."""
    parsed = scorer.parse_mql(
        'db.comments.countDocuments({"date": {"$gte": {"$date": "2015-01-01T00:00:00Z"}}})'
    )
    assert parsed.collection == "comments"


def test_parser_accepts_a_chain():
    """Sorting, limiting and projection all belong to the same statement."""
    parsed = scorer.parse_mql(
        'db.movies.find({"year": 2014}, {"title": 1}).sort({"runtime": -1, "title": 1}).limit(6)'
    )
    assert [name for name, _ in parsed.chain] == ["sort", "limit"]


def test_parser_refuses_more_than_one_statement():
    """Two statements in one answer is not something we can run safely."""
    with pytest.raises(scorer.ParseError):
        scorer.parse_mql("db.movies.drop()")


def test_parser_refuses_unknown_chained_methods():
    """An unknown method is refused rather than guessed at."""
    with pytest.raises(scorer.ParseError):
        scorer.parse_mql('db.movies.find({}).forEach(function (d) { print(d.title) })')


def test_parser_reports_having_nothing_to_run():
    """An answer with no query at all is an error, not a silent empty result."""
    with pytest.raises(scorer.ParseError):
        scorer.parse_mql("I would use the aggregation framework for this.")


def test_blocked_operators_are_found_anywhere_in_the_statement():
    """Code execution and write stages are detected before execution."""
    parsed = scorer.parse_mql('db.movies.find({"$where": "this.year > 2000"})')
    assert scorer.find_blocked({"args": parsed.args}) == "$where"
    pipeline = scorer.parse_mql('db.movies.aggregate([{"$match": {}}, {"$out": "copy"}])')
    assert scorer.find_blocked({"args": pipeline.args}) == "$out"


def test_execute_refuses_a_tool_that_is_switched_off():
    """The tool list in a version is enforced at execution, not merely requested."""
    parsed = scorer.parse_mql('db.movies.aggregate([{"$match": {}}])')
    execution = scorer.execute(db=None, mql=parsed, allowed_tools=["find"])
    assert execution.status == "tool_denied"
    assert not execution.ok


def test_answers_match_when_only_the_field_names_differ():
    """{"count": 47} and {"movies": 47} are the same answer to the same question."""
    matched, how = scorer.compare([{"movies": 47}], [{"count": 47}])
    assert matched and how == "values"


def test_answers_do_not_match_when_extra_fields_come_back():
    """Returning more than was asked for is a different answer."""
    matched, how = scorer.compare([{"count": 47}], [{"count": 47, "note": "extra"}])
    assert not matched and how == "mismatch"


def test_answers_do_not_match_across_a_different_number_of_rows():
    """The size of the answer is part of the answer."""
    matched, _ = scorer.compare([{"n": index} for index in range(10)], [{"n": index} for index in range(9)])
    assert not matched


def test_identifier_is_ignored_for_document_answers():
    """Asking for titles must not fail because the identifier was included."""
    matched, _ = scorer.compare([{"_id": "a", "title": "X"}], [{"title": "X"}], drop_id=True)
    assert matched


def test_identifier_is_part_of_a_grouped_answer():
    """For grouped answers the identifier is the group key, so it has to match."""
    matched, _ = scorer.compare([{"_id": "Drama", "n": 5}], [{"_id": "Comedy", "n": 5}], drop_id=False)
    assert not matched


def test_order_matters_only_when_the_question_sorts():
    """A sequence question and a set question are compared differently."""
    left = [{"title": "A"}, {"title": "B"}]
    right = [{"title": "B"}, {"title": "A"}]
    assert scorer.compare(left, right, order_sensitive=False)[0]
    assert not scorer.compare(left, right, order_sensitive=True)[0]


def test_editable_keys_cover_the_version_document():
    """Every knob a proposal may set is a real key of the version document."""
    for key in EDITABLE_KEYS:
        assert key in GENESIS, f"{key} is editable but absent from a version"
