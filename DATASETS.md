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
- questions that repeat each other are dropped.

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

## What is not general yet

Named plainly, because a product that hides its edges cannot be trusted with a measurement:

- **Lessons are per-dataset in principle, film-flavoured in practice.** The agent's memory of past
  mistakes is keyed by question family and was written while working on `sample_mflix`. On a new
  dataset the agent starts without anything useful to recall.
- **The instrument audit is written against `sample_mflix`.** `mh.cli audit-ruler` probes the scoring
  sandbox with pairs of queries over the film collections. A pack can carry its own probes in an
  `audit_probes` field, but the runner does not consume them yet.
- **The embedder is fixed** (`BAAI/bge-small-en-v1.5` via fastembed) and is used for lesson recall.
