"""Use this gate in someone else's harness.

The gate in `mh.gate` decides whether a proposed change to an agent makes it better.
Nothing in it knows about MongoDB, sample_mflix, or the agent in this repository. This
module is the small amount of glue that lets a different harness hand its own work to
that decision, and get back a verdict it can act on.

A harness has to answer two questions, and nothing else:

    measure(config, split) -> list[dict]     # one entry per case: {"task_id", "passed"}
    propose(incumbent)     -> dict | None    # the configuration it wants to try instead

Everything else is the gate's job: it measures both configurations on the same cases,
decides, and explains itself in a sentence that can be shown to a person or written to a
log. If the harness has a notion of what its agent is allowed to do, it can also answer
`envelope()`, and a proposal that widens its own permissions is refused before any
measurement is spent on it.

    from mh.adapter import Gate

    verdict = Gate(my_harness).review(incumbent_config, candidate_config)
    if verdict.accepted:
        deploy(verdict.config)
    else:
        log.warning("refused: %s", verdict.reason)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable

from mh import gate as gate_rules


@runtime_checkable
class Harness(Protocol):
    """What a harness must provide to be judged by this gate."""

    name: str

    def measure(self, config: dict, split: str) -> list[dict]:
        """Run one configuration over one split, one entry per case."""

    def propose(self, incumbent: dict) -> dict | None:
        """The change this harness wants to make to itself, or None."""


@dataclass
class Verdict:
    """A decision about one proposed change, with the arithmetic behind it."""

    decision: str
    reason: str
    evidence: dict
    config: dict | None = None
    accepted: bool = False
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        """A shape that is safe to write to a log or a database."""
        return {
            "decision": self.decision,
            "reason": self.reason,
            "evidence": self.evidence,
            "accepted": self.accepted,
            **self.extra,
        }


class Gate:
    """Judge another harness's proposed self-edits.

    ``selection`` is the split the harness optimises against; ``verification`` is the one
    it must generalise to. Measuring both is the whole point: a change that only moves the
    selection split is the failure this gate exists to catch.

    ``allowed_tools`` is the harness's own permission list. It defaults to the MongoDB
    tools this repository's agent uses; a harness with different capabilities names its
    own, so the permission check is about its envelope rather than about ours.

    ``on_review`` is called with every verdict, so a harness can record refusals where it
    keeps its own history rather than having to read this repository's ledger.
    """

    def __init__(
        self,
        harness: Harness,
        selection: str = "selection",
        verification: str = "verification",
        repeats: int = 1,
        allowed_tools: tuple[str, ...] | None = None,
        on_review: Callable[[Verdict], None] | None = None,
    ) -> None:
        self.harness = harness
        self.selection = selection
        self.verification = verification
        self.repeats = max(1, repeats)
        self.on_review = on_review
        self.allowed_tools = allowed_tools

    # ------------------------------------------------------------------ measuring

    def _measure(self, config: dict, split: str) -> list[dict]:
        """Measure one configuration, repeating the verification split if asked.

        Repeats exist because one run of a small verification set cannot tell a real
        improvement from a lucky one. The results are kept flat: the gate counts how many
        times each case appears and requires more than one before trusting a small gain.
        """
        gathered: list[dict] = []
        for repeat in range(self.repeats if split == self.verification else 1):
            results = self.harness.measure(config, split)
            for result in results:
                gathered.append({**result, "repeat": repeat + 1})
        return gathered

    # ------------------------------------------------------------------- deciding

    def review(
        self,
        incumbent: dict,
        candidate: dict | None = None,
        current_envelope: dict | None = None,
        proposed_envelope: dict | None = None,
    ) -> Verdict:
        """Decide whether ``candidate`` replaces ``incumbent``.

        If ``candidate`` is omitted the harness is asked for one. When both envelope
        arguments are given, the permission check runs first: a proposal that grants
        itself a capability is refused before it costs a single measurement.
        """
        if current_envelope is not None and proposed_envelope is not None:
            allowed, why = gate_rules.envelope_check(
                current_envelope, proposed_envelope, allowed_tools=self.allowed_tools
            )
            if not allowed:
                verdict = Verdict(
                    decision="rejected_envelope",
                    reason=why,
                    evidence={},
                    extra={"harness": self.harness.name},
                )
                self._report(verdict)
                return verdict

        if candidate is None:
            candidate = self.harness.propose(incumbent)
            if candidate is None:
                verdict = Verdict(
                    decision="no_proposal",
                    reason="the harness proposed no change to itself",
                    evidence={},
                    extra={"harness": self.harness.name},
                )
                self._report(verdict)
                return verdict

        incumbent_verification = self._measure(incumbent, self.verification)
        candidate_verification = self._measure(candidate, self.verification)
        incumbent_selection = self._measure(incumbent, self.selection)
        candidate_selection = self._measure(candidate, self.selection)

        decision, reason, evidence = gate_rules.decide(
            incumbent_verification, candidate_verification, incumbent_selection, candidate_selection
        )
        accepted = decision == "promoted"
        verdict = Verdict(
            decision=decision,
            reason=reason,
            evidence=evidence,
            config=candidate if accepted else None,
            accepted=accepted,
            extra={"harness": self.harness.name, "repeats": self.repeats},
        )
        self._report(verdict)
        return verdict

    def _report(self, verdict: Verdict) -> None:
        """Hand the verdict to the harness's own recorder, if it has one."""
        if self.on_review is not None:
            self.on_review(verdict)
