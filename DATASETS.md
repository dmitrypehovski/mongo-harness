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

## What is still tied to this repository

Named plainly, because a product that hides its edges cannot be trusted with a measurement:

- **Switching embedding models does not re-embed what is already stored.** `MH_EMBED_MODEL` and
  `MH_EMBED_DIM` select the model, but lessons already in the database keep the width they were
  written with, and recall cannot compare across widths. The harness warns with a count instead of
  returning an empty result, and `store.embedding_widths()` reports the mismatch — but there is no
  re-embed command yet. Changing the model also means re-creating the vector index; its width now
  comes from the embedding module rather than being typed in, so `scripts/update_vector_index.py`
  will offer to rebuild it.

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
- **A ledger written before any of this is repaired from evidence, not from guesswork.**
  `scripts/stamp_dataset_on_ledger.py` rewrites stamps from the task ids inside each document, leaves
  alone what it cannot decide, and marks a run it can only place by the database it executed against
  as approximate. On this repository's own database it rewrote 172 documents and left none
  undecided.
