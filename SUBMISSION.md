# Submission pack

Everything needed to hand this in, and the exact order to do it in.
Submission deadline: **5:00PM PT**. Deliverables: public repository, a one minute
video recorded today, and a short project description.

## 1. Atlas (required for the finals)

The submission runs on **Cluster0** (`cluster0.te8e8r.mongodb.net`, MongoDB 8.0.34) in
the hackathon sandbox project, organised as: dataset in `sample_mflix`, ledger in
`harness`, vector index `lessons_vec` over `harness.lessons.embedding`.

What was done, and what to repeat on another cluster:

1. **Database user** with `Atlas admin`, and the machine that loads the data added to
   **Network Access** (the loading host is `157.180.49.112`).
2. **Load and prepare**, from the machine allowed above:

```bash
export MONGODB_URI="$(cat /root/.secrets/atlas_uri)"
bash scripts/restore_to_atlas.sh
.venv/bin/python scripts/ensure_dataset_indexes.py
.venv/bin/python -m mh.cli init
.venv/bin/python -m mh.cli run
```

`restore_to_atlas.sh` restores the dataset, creates the ledger collections, their MQL
indexes and the `lessons_vec` Vector Search index, and prints what the cluster holds.
`ensure_dataset_indexes.py` is required: the Atlas dump ships without the
`comments.movie_id` index, so the eight join questions time out before their reference
answers can be computed. Verified on the cluster: 21,349 movies, 41,079 comments,
1,564 theaters, 3,483 embedded movies; `$vectorSearch` answers on `lessons_vec`.

## 2. Public repository

The repository is committed locally at `/root/hack/mongo-harness` (25 files). It has
to be public for the submission. GitHub is not authenticated on this machine, so
whichever is easier for you:

* run `gh auth login` yourself and I will create and push the repository, or
* tell me and I will start the device login flow here: you get a short code, you
  approve it on your phone, exactly like the Cursor login earlier.

## 3. The one minute video

Record on site, today, with sound. Screen plus voice is enough. Suggested shots:

| time | what is on screen | what to say |
|---|---|---|
| 0:00–0:10 | Atlas UI → **Browse Collections** → `harness.versions` | a version of this harness is a document in MongoDB; everything it can change about itself lives in that document |
| 0:10–0:20 | `python -m mh.cli run` on the cluster | it answers 57 plain-language questions about sample_mflix and is scored on the rows it returns, never on the text of the query |
| 0:20–0:35 | `python -m mh.cli edits` — the ledger, down to the refusals | it proposed five changes to itself; the gate refused all five, and each refusal carries its numbers |
| 0:35–0:50 | `bash demo/gate_proof.sh` — the crippled run | with the aggregation tool revoked the harness falls to 19%, 47 questions refused; it asks for the tool back and the envelope says no; a human grants it, not the harness |
| 0:50–0:58 | Atlas UI → **Search & Vector Search** → `lessons_vec` | it remembers its own past failures through a vector index on the cluster |
| 0:58–1:00 | `python -m mh.cli rollback` | every promotion is reversible with one command |

The ledger commands read MongoDB, so they are instant and safe to run live. The two
guards in the fourth shot are the reason the rest is worth believing: no language
model decides those outcomes.

## 4. Description (paste into the submission form)

> **The harness that earns its edits.** A self-improving agent usually edits its own
> prompt and declares victory, because nothing tests the edit. This harness cannot.
> A version of it is a document in MongoDB, and a change only becomes current if the
> gate promotes it. It answers 57 plain-language questions about the sample_mflix
> dataset by writing MongoDB queries, and is scored on the rows it returns against a
> reference answer, never on the text of the query. Each generation it reads its own
> failures back out of Atlas and proposes several new versions of itself. Every one
> of them faces two checks: an envelope that refuses any edit widening its own tool
> access or asking for code execution, and a held-out measurement over repeated runs
> with an exact paired test. In the run recorded in the repository, five plausible
> strategies were proposed and all five were refused: the memorising one bought
> +12.5 points on the data the search could see and +2 on the data it could not; the
> retrieval one made the harness measurably worse; one asked for more power and never
> ran. The most useful finding was not in the harness at all: the sandbox was
> rejecting JavaScript regular expressions that mongosh accepts, and repairing that
> ruler moved the same version from 65.6%/80.0% to 75.0%/88.0% without touching the
> harness. Every version, run, step, proposal and refusal is in the ledger, and a
> promotion is undone with one command. Everything in the repository was written
> during the event, in the hackathon's Atlas sandbox cluster; the only borrowed
> artefacts are MongoDB's own sample dataset and its published query guidance, both
> credited in the README.

## 5. What is honest about the limits

* The gate is only as strong as its verification set. If the held-out questions
  resemble the selection questions, a strategy that memorises them will look like
  progress. `replay_train_answers` is exactly that strategy, and the ledger shows
  what the gate did with it.
* The thresholds (noise margin, p-value) are ours and are documented in
  `mh/gate.py`; they are judgement calls, not laws.
* The harness edits configuration, not code. That is what makes each step auditable,
  and it is also the ceiling.
