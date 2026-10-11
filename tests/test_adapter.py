"""The adapter: another harness's proposal, judged by this gate."""

from __future__ import annotations

from mh.adapter import Gate


def version_with(tools: list[str]) -> dict:
    """A version-shaped configuration, so the permission check has something to read."""
    return {
        "envelope_version": 1,
        "system_prompt": "Answer the question with one query. Reply with the query only.",
        "rules": [],
        "cot": False,
        "sample_docs_n": 0,
        "include_indexes": False,
        "retrieve_k": 0,
        "replay_train_answers": False,
        "tools": tools,
    }


class StubHarness:
    """A harness with twenty verification cases and twenty selection cases.

    ``verification_fixed`` cases only pass once ``date_support`` is on; ``selection_only``
    cases only matter on the selection split. That is enough to exercise the four
    outcomes the gate produces without a model, a database or a network call.
    """

    name = "stub"

    def __init__(self, verification_fixed: int = 5, verification_broken: int = 0) -> None:
        self.verification_fixed = verification_fixed
        self.verification_broken = verification_broken
        self.reviews = []
        self.proposals = 0

    def measure(self, config: dict, split: str) -> list[dict]:
        date_support = bool(config.get("date_support"))
        broken = bool(config.get("broken"))
        results = []
        for index in range(20):
            if split == "verification":
                if index < self.verification_fixed:
                    passed = date_support and not broken
                else:
                    passed = not broken
            else:
                # the selection split likes the change a great deal; whether that means
                # anything is exactly what the verification split is for
                passed = index >= (4 if date_support else 12)
            results.append({"task_id": f"{split[0]}{index:02d}", "passed": bool(passed)})
        return results

    def propose(self, incumbent: dict) -> dict:
        self.proposals += 1
        return {**incumbent, "date_support": True}


def gate_for(harness: StubHarness, **kwargs) -> Gate:
    gate = Gate(harness, repeats=1, **kwargs)
    gate.on_review = harness.reviews.append
    return gate


def test_a_change_that_fixes_verification_cases_is_promoted():
    harness = StubHarness()
    verdict = gate_for(harness).review({}, {"date_support": True})
    assert verdict.decision == "promoted"
    assert verdict.accepted is True
    assert verdict.config == {"date_support": True}
    assert verdict.evidence["only_candidate"] == 5
    assert verdict.evidence["only_incumbent"] == 0


def test_a_change_that_only_moves_the_selection_split_is_refused():
    harness = StubHarness(verification_fixed=0)
    verdict = gate_for(harness).review({}, {"date_support": True})
    assert verdict.decision == "rejected_outsample"
    assert verdict.accepted is False
    assert verdict.config is None


def test_a_change_that_makes_verification_worse_is_refused():
    harness = StubHarness()
    verdict = gate_for(harness).review({}, {"date_support": True, "broken": True})
    assert verdict.decision == "rejected_regression"
    assert verdict.evidence["holdout_rate_after"] < verdict.evidence["holdout_rate_before"]


def test_a_proposal_that_widens_its_own_permissions_is_refused_without_measuring():
    harness = StubHarness()
    gate = gate_for(harness, allowed_tools=("lookup",))

    def explode(config: dict, split: str) -> list[dict]:
        raise AssertionError("the gate measured a proposal it should have refused outright")

    harness.measure = explode  # type: ignore[assignment]
    verdict = gate.review(
        {},
        candidate={},
        current_envelope=version_with(["lookup"]),
        proposed_envelope=version_with(["lookup", "shell"]),
    )
    assert verdict.decision == "rejected_envelope"
    assert "shell" in verdict.reason


def test_every_verdict_is_reported_to_the_harness():
    harness = StubHarness()
    gate = gate_for(harness)
    gate.review({}, {"date_support": True})
    gate.review({}, {"date_support": True, "broken": True})
    assert [review.decision for review in harness.reviews] == ["promoted", "rejected_regression"]


def test_the_harness_can_be_left_to_propose_on_its_own():
    harness = StubHarness()
    verdict = gate_for(harness).review({})
    assert harness.proposals == 1
    assert verdict.decision == "promoted"
