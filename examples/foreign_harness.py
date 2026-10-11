"""A foreign harness judged by this gate, in sixty lines and no dependencies.

This is an interface demonstration, not a measurement: the "agent" here is a stand-in
that enables features, and the numbers it produces describe nothing in the real world.
What it does prove is the thing that matters for reuse: another harness, with its own
idea of what a configuration is, its own cases and its own notion of passing, can hand a
proposed self-edit to `mh.adapter.Gate` and get back a verdict with a reason.

No MongoDB, no model, no network, nothing from this repository's own agent: only the
gate. Run it with:

    python examples/foreign_harness.py

Four proposals, and the four things the gate is for:

    fixes more cases on the verification split than noise can explain   -> promoted
    improves the split it was tuned on, and nothing else               -> rejected
    makes the verification split worse                                 -> rejected, worse
    grants itself a permission it did not have                         -> refused before
                                                                          measuring
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mh.adapter import Gate  # noqa: E402

# --------------------------------------------------------------- the foreign harness

FEATURES = ["ranges", "arrays", "regex", "dates", "joins"]


def _cases(prefix: str, count: int, needs: list[list[str]]) -> list[dict]:
    """Cases with the features they need to pass."""
    return [
        {"id": f"{prefix}{index:02d}", "needs": needs[index % len(needs)]}
        for index in range(1, count + 1)
    ]


SELECTION_CASES = _cases("s", 32, [["ranges"], ["arrays"], ["regex"], ["dates"], ["joins"]])
VERIFICATION_CASES = _cases(
    "v", 25, [["ranges"], ["arrays"], ["regex"], ["dates"], ["ranges", "arrays"]]
)


class FeatureAgent:
    """A harness whose agent answers a case only if every feature it needs is enabled."""

    name = "feature-agent (stand-in)"

    def __init__(self) -> None:
        self.envelope = {"tools": ["lookup"], "max_features": 5}

    def measure(self, config: dict, split: str) -> list[dict]:
        """Answer every case with the given configuration and report what passed."""
        enabled = {name for name, on in (config.get("features") or {}).items() if on}
        broken = config.get("break_all", False)
        cases = VERIFICATION_CASES if split == "verification" else SELECTION_CASES
        results = []
        for case in cases:
            passed = (not broken) and set(case["needs"]).issubset(enabled)
            results.append({"task_id": case["id"], "passed": bool(passed)})
        return results

    def propose(self, incumbent: dict) -> dict:
        """The harness would like to enable regex lookup, which nothing else can do."""
        features = dict(incumbent.get("features") or {})
        features["regex"] = True
        return {**incumbent, "features": features}


# ---------------------------------------------------------------------------- running

def with_tools(tools: list[str]) -> dict:
    """A version-shaped configuration, for demonstrating the permission check."""
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


def baseline() -> dict:
    """The starting version: one feature enabled."""
    return {"features": {"ranges": True}, "break_all": False}


def enabled(*names: str) -> dict:
    """A configuration with exactly these features on."""
    return {"features": {name: name in names for name in FEATURES}, "break_all": False}


def main() -> None:
    print(f"harness under judgement: {FeatureAgent.name}")
    print(f"  selection cases {len(SELECTION_CASES)}, verification cases {len(VERIFICATION_CASES)}")
    print("  the gate is from this repository; nothing else here is")
    print("  the gate asks for: +8% on the verification split before it believes a gain,")
    print("  no loss worse than 6% on the selection split, McNemar p <= 0.15\n")

    agent = FeatureAgent()
    gate = Gate(agent, repeats=1, allowed_tools=agent.envelope["tools"])

    trials = [
        (
            "enable dates: five verification cases start passing that never did before",
            baseline(),
            enabled("ranges", "dates"),
            None,
        ),
        (
            "enable joins: the selection split likes it, the verification split never uses it",
            baseline(),
            enabled("ranges", "joins"),
            None,
        ),
        (
            "try a rewrite that breaks everything it used to get right",
            enabled("ranges", "arrays", "regex", "dates", "joins"),
            {**enabled("ranges", "arrays", "regex", "dates", "joins"), "break_all": True},
            None,
        ),
        (
            "ask for a shell tool its envelope does not allow",
            None,
            None,
            {"tools": ["lookup", "shell"]},
        ),
    ]

    for label, incumbent, candidate, envelope in trials:
        print(f"— {label}")
        if envelope is not None:
            verdict = gate.review(
                baseline(),
                candidate=baseline(),
                current_envelope=with_tools(["lookup"]),
                proposed_envelope=with_tools(["lookup", "shell"]),
            )
        else:
            verdict = gate.review(incumbent, candidate)
        evidence = verdict.evidence or {}
        print(f"    decision: {verdict.decision}")
        print(f"    reason:   {verdict.reason}")
        if evidence:
            print(
                "    evidence: selection "
                f"{evidence['train_rate_before']:.1%} -> {evidence['train_rate_after']:.1%}, "
                "verification "
                f"{evidence['holdout_rate_before']:.1%} -> {evidence['holdout_rate_after']:.1%}, "
                f"gained {evidence['only_candidate']} against {evidence['only_incumbent']} lost, "
                f"p={evidence['p_value']}"
            )
        if verdict.accepted:
            print(f"    the harness may keep it: {json.dumps(verdict.config)}")
        print()

    # And the same gate, asked to decide for itself what to propose.
    verdict = gate.review(baseline())
    print(f"left to itself, the harness proposes: {verdict.reason}")
    print(f"    decision: {verdict.decision}")


if __name__ == "__main__":
    main()
