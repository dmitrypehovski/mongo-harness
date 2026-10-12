# Bringing your own data

The gate, the audit and the adapter know nothing about films. Three things do: the questions,
the reference answers, and the probes that check the instrument against a particular collection.
A **dataset pack** is where those live, so you can point the harness at your own database.

There are two ways to get a pack, and you can mix them.

## 1. Let the harness write the exam

```bash
python -m mh.cli scaffold-dataset \
    --database shop \
    --collections orders,customers \
    --want 14 \
    --out datasets/shop.json
```

It lists the collections, samples a few documents from each, asks a model for questions with
reference queries, and then **throws most of them away**. Nothing is kept on the model's word:

- every reference query is parsed and required to be read-only;
- every reference query is **run twice against the real collection**, and a question whose answer
  moves between the two runs is dropped — a question with a drifting answer cannot judge anything;
- a query that returns no rows is dropped, unless it is a count;
- a question whose reference disagrees with it about the shape of the answer is dropped (see below);
- questions that repeat each other are dropped;
- a question that would otherwise be unfair is **made precise instead of dropped**: if the
  reference returns a field the question never named, the question is amended to name the keys of
  each row (``Return each row with the keys `_id`, `theaterCount`.``); if the question asks for
  particular fields while the reference returns whole documents, the question now says so.

Every refusal is printed with its reason, so the output is a record of what the model proposed and
what survived, not a silent filter:

```
"kept": 7,
"dropped": 7,
"drop_reasons": {
  "the same question was already asked": 3,
  "the question asks for particular fields but the reference returns whole documents": 2,
  "the reference returns a field (theaterCount) the question never names": 2
}
```

### Why an unfair question is worse than no question

Measuring a generated exam taught this the hard way. The harness marked the agent wrong twice for
things the agent was right about:

- the question asked *"how many theatres in each state?"*, the reference grouped the count under
  `theaterCount`, and the agent grouped it under `count`. The question never named a field, so both
  names answer it. The reference was unfair.
- the question asked for *"each theater's ID and city"*, the reference returned whole documents, and
  the agent did what the question asked and projected those fields. Again the reference was unfair.

An exam that decides like that teaches an agent to guess the reference author's habits. So the
scaffolder refuses those pairs outright, with the reason stated.

## 2. Write the pack yourself

```json
{
  "name": "shop",
  "database": "shop",
  "description": "orders and customers, taken from the production replica",
  "tasks": [
    {
      "id": "o01",
      "family": "count",
      "split": "train",
      "collection": "orders",
      "question": "How many orders were placed in 2024?",
      "reference": "db.orders.countDocuments({\"placed_at\": {\"$gte\": {\"$date\": \"2024-01-01T00:00:00Z\"}}})"
    }
  ]
}
```

Rules the loader enforces before anything is measured:

- every task needs `id`, `question`, `reference`, `split` and `collection`;
- ids are unique; `split` is `train` or `holdout`;
- the reference is a `db.<collection>` query — the answer is the rows it returns, never the text of
  the agent's query;
- **both splits must be non-empty.** The gate compares a change on the split the agent was tuned on
  and on the split it was not; one without the other cannot tell a real improvement from a fit.

Keep reference queries deterministic: sort with a tie breaker (`{"theaterId": 1, "_id": 1}`) so a
top-k boundary cannot flip between runs and turn into a phantom improvement.

## 3. Run against it

```bash
python -m mh.cli run --dataset datasets/shop.json --show-failures
python -m mh.cli status  --dataset datasets/shop.json
python -m mh.cli generation --dataset datasets/shop.json --want 4
```

Or set `MH_DATASET=datasets/shop.json` once and every command follows it. Without either, the
shipped `sample_mflix` suite is used — the film questions are the reference pack, not the only one.

Reference answers are cached per question set (keyed by a fingerprint of the questions), so
switching datasets never mixes one dataset's answers into another's measurements.

## How the claim is checked

`scripts/stranger_journey.sh` runs the whole path in a fresh virtual environment against a database
it creates itself (a cafe: 48 orders, 6 menu items), installing the built wheel rather than reading
the checkout: create the environment, write the data, write the exam, compute the references,
measure, audit the instrument from the pack's own probes, then print the ledger's memory.

It is what caught the film-shaped prompt: with the shipped film description in front of it, the agent
answered "the sample_mflix database contains no orders collection" and once produced a query over
`movies` that returned the wrong rows. After the description was derived from the data, the same four
questions scored 3 of 3 and 1 of 1. It also caught its own invalid run: pip skips an install when the
version number is already present, so the script now forces the package to be replaced and refuses to
continue if the installed copy is missing modules the wheel carries.

## What is still tied to this repository

Named plainly, because a product that hides its edges cannot be trusted with a measurement:

- **A vector index has to be rebuilt when the width changes.** `MH_EMBED_DIM` selects the width, and
  the index definition now takes it from the same place rather than holding a literal, but an index
  already built for another width refuses the vectors this code produces.
  `scripts/update_vector_index.py` reports the difference and rebuilds it.

## What is general now, and how it is enforced

- **Memory is scoped to the data, not to the questions.** Every run and every lesson is stamped with
  the scope of what it measured: the database plus the collections its questions touch
  (`tasks.pack_scope()`). Recall filters on that scope inside the `$vectorSearch` stage itself, so a
  new question never recalls a lesson about another collection — and regenerating an exam over the
  same data keeps everything learned about it. The exact question wording is recorded separately as
  `pack`, for provenance only.
- **The instrument audit travels with the pack.** `mh.cli audit-ruler --dataset <pack>` builds its
  equivalence probes from the pack's `audit_probes`, anchored in values read out of that data now.
  `scaffold-dataset` writes those probes when it writes the exam, and
  `scripts/write_audit_probes.py --dataset <pack>` adds them to a pack that predates them. A pack
  that declares none is audited only for what the instrument refuses, and the report says so rather
  than passing film probes off as a check.
- **The prompt describes the database in front of the agent.** `mh/schema.py` reads the collections
  the pack asks about and writes the description the agent is given: field paths (nested ones
  included), the types actually stored, numeric ranges, and how often a field is missing. The
  shipped film description is kept unchanged for the shipped questions, so the recorded rates stay
  comparable; every other question set gets its own. Without this, running on unfamiliar data
  produced answers like "the sample_mflix database contains no orders collection" and one query over
  films that silently returned the wrong rows.
- **Changing the embedding model is a recoverable operation, not amnesia.** `python -m mh.cli
  reembed` reports what cannot be compared, rewrites it, and then reads the result back out of the
  database. Equal widths are not equal models: two 384-number models live in different spaces, and
  comparing across them returns confident nonsense rather than an error — so each vector records the
  model that produced it, and an unrecorded vector is rewritten rather than assumed comparable.
  `mh status` prints how many lessons are comparable and points at the command when they are not.
- **A ledger written before any of this is repaired from evidence, not from guesswork.**
  `scripts/stamp_dataset_on_ledger.py` rewrites stamps from the task ids inside each document, leaves
  alone what it cannot decide, and marks a run it can only place by the database it executed against
  as approximate. On this repository's own database it rewrote 172 documents and left none
  undecided.
