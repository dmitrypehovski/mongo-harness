# Submission pack

Everything needed to hand this in, and the exact order to do it in.
Submission deadline: **5:00PM PT**. Deliverables: public repository, a one minute
video recorded today, and a short project description.

## 1. Atlas (required for the finals)

The project runs today against a local copy of `sample_mflix`; the finals require the
same thing on MongoDB Atlas. Three steps, in this order.

1. **Accept the sandbox invite** from MongoDB / Cerebral Valley and open Atlas.
   If it offers to create the cluster instead of handing one over:
   *Build a Database* → **M0 Free (Shared)** → region near San Francisco.
2. **Database Access** → add a database user (role `Atlas admin`). Generate the
   password and keep it; avoid `@`, `:` and `/` in it.
   **Network Access** → add the address `157.180.49.112` (the machine that loads the
   data), plus your own address if you will run it from the laptop.
3. **Connect → Drivers** → copy the `mongodb+srv://...` string into
   `/root/.secrets/atlas_uri` on that machine, then:

```bash
export MONGODB_URI="$(cat /root/.secrets/atlas_uri)"
bash scripts/restore_to_atlas.sh
```

That restores the dataset, creates the harness collections, its indexes and the
Atlas Vector Search index over the memory of past failures, and prints what the
cluster now holds. Nothing is ever echoed back.

Then measure the same numbers on Atlas:

```bash
.venv/bin/python -m mh.cli init
.venv/bin/python -m mh.cli run
```

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
| 0:00–0:10 | `python -m mh.cli status` — the current version document | a harness version is a document in MongoDB; everything it can change about itself lives there |
| 0:10–0:25 | `python -m mh.cli run` — the selection and verification numbers | it answers 57 plain-language questions about sample_mflix and is scored on returned rows, never on query text |
| 0:25–0:45 | `python -m mh.cli edits` — the ledger, scrolling to the refusals | it proposed changes to itself; the gate refused the ones that widened its power or that only helped on the data the search could see |
| 0:45–0:55 | `python -m mh.cli rollback` | every promotion is reversible, and the reason for each decision is in the ledger |
| 0:55–1:00 | `python -m mh.cli status` again | the harness is the same data it always was: auditable, diffable, reversible |

The ledger commands read MongoDB, so they are instant and safe to run live.

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
> promotion is undone with one command.

## 5. What is honest about the limits

* The gate is only as strong as its verification set. If the held-out questions
  resemble the selection questions, a strategy that memorises them will look like
  progress. `replay_train_answers` is exactly that strategy, and the ledger shows
  what the gate did with it.
* The thresholds (noise margin, p-value) are ours and are documented in
  `mh/gate.py`; they are judgement calls, not laws.
* The harness edits configuration, not code. That is what makes each step auditable,
  and it is also the ceiling.
