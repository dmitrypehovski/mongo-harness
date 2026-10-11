# Using this gate in your own harness

The gate decides whether a change an agent makes to itself actually made it better. It
knows nothing about MongoDB, about `sample_mflix`, or about the agent in this repository:
that knowledge lives in `mh/agent.py`, `mh/tasks.py` and the ledger. What is reusable is
`mh/gate.py` (the rules) and `mh/adapter.py` (the glue that lets your harness call them).

## What your harness has to provide

Two methods. Nothing else:

```python
class MyHarness:
    name = "my-harness"

    def measure(self, config: dict, split: str) -> list[dict]:
        """Run one configuration over one split. One entry per case."""
        return [{"task_id": case_id, "passed": True_or_False}, ...]

    def propose(self, incumbent: dict) -> dict | None:
        """The change the agent wants to make to itself, or None."""
```

`config` is yours: a dict of whatever your agent can change about itself. The gate never
reads inside it, except in the permission check described below.

Optional, when your agent has capabilities rather than only settings:

```python
    def envelope(self) -> dict:
        return {"tools": ["search", "summarise"], "rules": [], ...}
```

## Calling it

```python
from mh.adapter import Gate

gate = Gate(
    MyHarness(),
    selection="train",        # the split you optimise against
    verification="holdout",   # the split the change has to generalise to
    repeats=2,                # how many times the verification split is re-run
    allowed_tools=("search", "summarise"),
)

verdict = gate.review(incumbent_config)              # let your harness propose
verdict = gate.review(incumbent, candidate)          # or judge a specific change

if verdict.accepted:
    deploy(verdict.config)                           # the gate measured it; you deploy it
else:
    print(f"refused: {verdict.reason}")              # one sentence, safe to show a person
```

`verdict.as_dict()` is shaped for a log or a collection. `Gate(..., on_review=fn)` gets
called with every verdict, so refusals can live in your own history instead of ours.

A complete, runnable example with no model, no database and no network:
`python examples/foreign_harness.py`.

## What the gate refuses, in order

1. A proposal that grants the agent a capability it did not have. Refused before a single
   measurement is spent on it.
2. A change that makes the verification split worse, whatever it does on the selection
   split.
3. A change that improves the selection split while the verification split does not move:
   fitting the selection set, not learning.
4. A change whose verification gain is smaller than the margin the gate asks for.
5. A change that improves verification but costs the selection split more than the
   tolerance allows.
6. A change whose gain is inside run-to-run noise, by an exact McNemar test.

## What it needs from your measurements

* **Per-case pass or fail**, not just a total. Every rule above is a paired comparison:
  which cases the old version got right and the new one lost, and the other way round.
* **The same case ids on both splits.** The gate compares each split against its own
  earlier run; case sets of different sizes are reported as not comparable rather than
  quietly compared.
* **Repeats for small sets.** One pass over twenty-five cases cannot separate a real gain
  from a lucky one. Our own harness measures its verification split twice, and the gate
  records how many times each case was seen.

## What you will want to change, and should

The thresholds are constants in `mh/gate.py` and they encode our judgement, not a law:

| constant | value | what it means |
| --- | --- | --- |
| `HOLD_MARGIN` | `0.08` | verification gain below this is not acted on |
| `TRAIN_TOLERANCE` | `0.06` | how much the selection split may fall |
| `SIGNIFICANCE` | `0.15` | McNemar p above this counts as noise |
| `FORBIDDEN_IN_RULES` | `$where`, `$function`, ... | operators a rule may not ask for |

The last one is the most domain-specific: it says server-side JavaScript is not something
our agent may grant itself. Yours will be a different list, and it is the part worth
writing carefully, because it is the only rule here that is about safety rather than
about measurement.

## What the gate does not do

It judges measured outcomes. It does not review code, check security, or decide whether
the change was a good idea in any other sense. A change that survives it has earned the
right to be deployed, and nothing more than that.
