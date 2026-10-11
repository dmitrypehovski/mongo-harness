"""The gate: the only thing in the system allowed to accept a new harness version.

The gate does two jobs.

1. **Envelope.** It checks the shape of a proposed version before anything is run:
   no unknown keys, no touching frozen keys, no widening of the tool set, no rule
   that asks for code execution or a write. This is a refusal path in the code, not
   a sentence in a prompt: a version that tries it never reaches the database.
2. **Evidence.** It compares the candidate with the current version on the
   verification set and refuses improvements that do not survive it: a candidate
   that only gets better on the selection set is overfitting, and a candidate whose
   gain is small enough to be noise is refused as such.
"""

from __future__ import annotations

import logging
import math

from mh.agent import EDITABLE_KEYS, FROZEN_KEYS

log = logging.getLogger(__name__)

ALLOWED_TOOLS = ("find", "aggregate", "count")
FORBIDDEN_IN_RULES = ("$where", "$function", "$accumulator", "$out", "$merge")
MAX_RULES = 25
RULE_CHARS = 400

#: How much better the candidate must be on the verification set, as a share of
#: questions, for the improvement to count. One question out of twenty-five is
#: inside the noise of a single run, so a bare improvement is not enough.
HOLD_MARGIN = 0.08

#: How far the candidate may fall behind on the selection set before it is refused
#: even if the verification set likes it.
TRAIN_TOLERANCE = 0.06

#: Largest McNemar p-value still treated as evidence rather than chance.
SIGNIFICANCE = 0.15


def _is_plain_int(value) -> bool:
    """True for a real integer that is not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


#: Phrases that mark a rule as a prohibition rather than a request. A rule that
#: says "never use $where" is the opposite of a rule that asks for it.
NEGATIONS = ("never", "do not", "don't", "avoid", "refrain", "without")


def _asks_for_forbidden(rule: str) -> str:
    """Return the forbidden operator a rule asks for, or an empty string.

    This is the first line of defence and it is deliberately simple. The second
    line is `mh.scorer`, which refuses a generated query that uses one of these
    operators whatever the rules said.
    """
    lowered = rule.lower()
    if any(negation in lowered for negation in NEGATIONS):
        return ""
    for forbidden in FORBIDDEN_IN_RULES:
        if forbidden in lowered:
            return forbidden
    return ""


def envelope_check(current: dict, candidate: dict) -> tuple[bool, str]:
    """Decide whether a proposed version is even allowed to be tested.

    Returns ``(allowed, reason)``. The reason is written to the ledger whatever
    the outcome, so a refusal can always be explained after the fact.
    """
    if not isinstance(candidate, dict):
        return False, "the proposal is not a configuration object"

    known = set(EDITABLE_KEYS) | set(FROZEN_KEYS)
    unknown = sorted(set(candidate) - known)
    if unknown:
        return False, f"the proposal adds keys that do not exist in a version: {', '.join(unknown)}"

    for key in FROZEN_KEYS:
        if key in candidate and candidate[key] != current.get(key):
            return False, f"{key} is frozen and no edit may change it ({current.get(key)} -> {candidate[key]})"

    merged = dict(current)
    merged.update({key: value for key, value in candidate.items() if key in EDITABLE_KEYS})

    prompt = merged.get("system_prompt")
    if not isinstance(prompt, str) or len(prompt.strip()) < 50:
        return False, "the system prompt would be emptied out"

    rules = merged.get("rules")
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        return False, f"rules must be a list of at most {MAX_RULES} entries"
    for rule in rules:
        if not isinstance(rule, str):
            return False, "every rule must be a string"
        if len(rule) > RULE_CHARS:
            return False, f"a rule is longer than {RULE_CHARS} characters"
        asked = _asks_for_forbidden(rule)
        if asked:
            return False, f"a rule asks for {asked}, which the envelope refuses"

    if not isinstance(merged.get("cot"), bool):
        return False, "cot must be true or false"
    if not isinstance(merged.get("replay_train_answers"), bool):
        return False, "replay_train_answers must be true or false"
    if not _is_plain_int(merged.get("sample_docs_n")) or not 0 <= merged["sample_docs_n"] <= 5:
        return False, "sample_docs_n must be a whole number between 0 and 5"
    if not _is_plain_int(merged.get("retrieve_k")) or not 0 <= merged["retrieve_k"] <= 10:
        return False, "retrieve_k must be a whole number between 0 and 10"

    tools = merged.get("tools")
    if not isinstance(tools, list) or not tools:
        return False, "the tool set would be empty"
    if len(set(tools)) != len(tools):
        return False, "the tool set repeats an entry"
    for tool in tools:
        if tool not in ALLOWED_TOOLS:
            return False, f"{tool} is not a tool the harness may use"
    widened = sorted(set(tools) - set(current.get("tools") or []))
    if widened:
        return False, f"the proposal widens its own tool access with: {', '.join(widened)}"

    return True, "the proposal stays inside the envelope"


def mcnemar_exact(only_incumbent: int, only_candidate: int) -> float:
    """Exact two-sided McNemar p-value for paired binary outcomes.

    ``only_incumbent`` counts questions the current version answered right and the
    candidate got wrong; ``only_candidate`` is the opposite count.
    """
    discordant = only_incumbent + only_candidate
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, index) for index in range(0, min(only_incumbent, only_candidate) + 1))
    return min(1.0, 2 * tail / (2 ** discordant))


def _per_task(results: list[dict]) -> dict[str, tuple[int, int]]:
    """Per task: how many of the repeats passed, and how many repeats there were."""
    counts: dict[str, list[int]] = {}
    for result in results:
        entry = counts.setdefault(result["task_id"], [0, 0])
        entry[1] += 1
        if result.get("passed"):
            entry[0] += 1
    return {task_id: (value[0], value[1]) for task_id, value in counts.items()}


def paired_counts(incumbent: list[dict], candidate: list[dict]) -> tuple[int, int]:
    """Count the disagreeing observations between two sets of runs.

    Every repeat of a question is one observation, so measuring the verification
    set three times gives three times as much evidence about the same questions.
    A question counts as gained when the candidate answered it right in a repeat
    where the current version got it wrong, and the other way round for a loss.
    """
    def keyed(results: list[dict]) -> dict[tuple[str, int], bool]:
        return {
            (result["task_id"], int(result.get("repeat", 1))): bool(result.get("passed"))
            for result in results
        }

    current = keyed(incumbent)
    other = keyed(candidate)
    only_incumbent = 0
    only_candidate = 0
    for key, value in current.items():
        if key not in other:
            continue
        if value and not other[key]:
            only_incumbent += 1
        elif other[key] and not value:
            only_candidate += 1
    return only_incumbent, only_candidate


def rate(results: list[dict]) -> float:
    """Share of questions answered correctly, averaged over repeats."""
    per_task = _per_task(results)
    if not per_task:
        return 0.0
    total = sum(passes / runs for passes, runs in per_task.values())
    return total / len(per_task)


def decide(
    incumbent_holdout: list[dict],
    candidate_holdout: list[dict],
    incumbent_train: list[dict],
    candidate_train: list[dict],
) -> tuple[str, str, dict]:
    """Decide whether the candidate replaces the current version.

    Returns ``(decision, reason, evidence)``.
    """
    before = rate(incumbent_holdout)
    after = rate(candidate_holdout)
    train_before = rate(incumbent_train)
    train_after = rate(candidate_train)
    only_incumbent, only_candidate = paired_counts(incumbent_holdout, candidate_holdout)
    p_value = mcnemar_exact(only_incumbent, only_candidate)
    repeats = {}
    for result in candidate_holdout:
        repeats[result["task_id"]] = repeats.get(result["task_id"], 0) + 1

    evidence = {
        "train_rate_before": round(train_before, 4),
        "train_rate_after": round(train_after, 4),
        "holdout_rate_before": round(before, 4),
        "holdout_rate_after": round(after, 4),
        "n_holdout": len(_per_task(candidate_holdout)),
        "repeats": max(repeats.values()) if repeats else 0,
        "only_incumbent": only_incumbent,
        "only_candidate": only_candidate,
        "p_value": round(p_value, 4),
    }

    if len(_per_task(candidate_holdout)) != len(_per_task(incumbent_holdout)):
        return (
            "rejected_insignificant",
            "the verification sets differ in size, so the two runs are not comparable",
            evidence,
        )

    if after < before:
        return (
            "rejected_regression",
            f"the version is worse on the verification set ({before:.1%} -> {after:.1%}), so it is not kept "
            "whatever it does on the selection set",
            evidence,
        )

    if after <= before:
        if train_after > train_before:
            return (
                "rejected_outsample",
                f"it improves on the selection set only ({train_before:.1%} -> {train_after:.1%}) while the "
                f"verification set does not move ({before:.1%} -> {after:.1%}): that is fitting the "
                "selection set, not learning",
                evidence,
            )
        return (
            "rejected_insignificant",
            f"nothing moves: selection set {train_before:.1%} -> {train_after:.1%}, verification set "
            f"{before:.1%} -> {after:.1%}",
            evidence,
        )

    if after < before + HOLD_MARGIN:
        return (
            "rejected_insignificant",
            f"the verification set does move ({before:.1%} -> {after:.1%}) but by less than the "
            f"{HOLD_MARGIN:.0%} this gate asks for, so the change is not separable from run-to-run noise "
            f"(McNemar p={p_value:.2f}, {only_candidate} question(s) gained against {only_incumbent} lost)",
            evidence,
        )

    if train_after < train_before - TRAIN_TOLERANCE:
        return (
            "rejected_narrow",
            f"the verification set improves ({before:.1%} -> {after:.1%}) but the selection set falls from "
            f"{train_before:.1%} to {train_after:.1%}, so the change is not broad improvement",
            evidence,
        )

    if p_value > SIGNIFICANCE:
        return (
            "rejected_insignificant",
            f"the gain on the verification set ({before:.1%} -> {after:.1%}) is within noise "
            f"(McNemar p={p_value:.2f}, {only_candidate} question(s) gained against {only_incumbent} lost)",
            evidence,
        )

    return (
        "promoted",
        f"better on the verification set ({before:.1%} -> {after:.1%}, p={p_value:.2f}) and no worse on the "
        f"selection set ({train_before:.1%} -> {train_after:.1%}), so the rule is kept",
        evidence,
    )
