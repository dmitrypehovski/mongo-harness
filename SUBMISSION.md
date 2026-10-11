# Submission pack

Everything needed to hand this in, and the exact order to do it in.
Submission deadline: **5:00PM PT**, through the Cerebral Valley form. Deliverables:
a link to a public repository, a one minute video recorded today with video and audio,
and a short description.

## 1. Atlas (required for the finals)

The submission runs on **Cluster0** (`cluster0.te8e8r.mongodb.net`, MongoDB 8.0.34) in
the hackathon sandbox project, organised as: dataset in `sample_mflix`, ledger in
`harness`, vector index `lessons_vec` over `harness.lessons.embedding`.

What was done, and what to repeat on another cluster:

1. **Database user** with `Atlas admin`, and the host that loads the data added to
   **Network Access**.
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

**Done and verified:** <https://github.com/dmitrypehovski/mongo-harness> — public, read
anonymously with no token (HTTP 200), 84 files, 6 commits, `main` in sync with local
`HEAD`, README readable without authentication. No secret is present in any commit.

## 3. What you can use, not just read

`python -m web.app` opens the product surface: ask the database a question in plain
language and get the query, the rows and whether they match the reference answer; then
review the gate's last refusal with the arithmetic behind it and record a human override
in MongoDB. It is one page over the same ledger the CLI writes.

## 4. The one minute video

**Recorded by rendering it, not by pointing a camera at a screen.** The film is built
with Remotion from `video/`, and every number on screen is exported from the live ledger
by `scripts/export_video_data.py`, so the video cannot drift from what the gate actually
decided. Verified output: 60.00 seconds, 1920x1080, h264 with an AAC stereo track at
48 kHz, mean level -25.5 dB, 4.02 MB.

* script and beat list: `demo/VIDEO_60S.md`;
* source: `video/src/HarnessDemo.tsx`, cuts in `video/src/timeline.ts`;
* re-render: `cd video && npm install && npm run render`;
* the narration is synthesised, which satisfies the audio requirement without depending
  on a microphone in a loud room.

The **live** demo in front of the judges is a different three minutes, and
`demo/VIDEO_60S.md` has that plan too, with the two questions to expect and the honest
answer to each. Commands it relies on were timed against the cluster: `mh.cli status`
3.1s, `mh.cli edits` 2.5s, `mh.cli audit-ruler` about 5s.

## 4. Description (paste into the submission form)

> **The harness that earns its edits.** Recursive self-improvement has a failure mode
> nobody watches: a self-improving agent edits its own prompt, looks better on the
> examples it can see, and declares victory, because nothing tests the edit. This
> project is the missing half — a harness whose every self-edit faces a gate that can
> refuse it, backed by a ledger in MongoDB.
>
> A version of the harness is a document in MongoDB, and a change only becomes current
> if the gate promotes it. It answers 57 plain-language questions about the
> sample_mflix dataset by writing MongoDB queries, and is scored on the rows it
> returns against reference answers, never on the text of the query. Each generation
> it reads its own failures back out of Atlas and proposes several new versions of
> itself. Every one of them faces two checks: an envelope that refuses any edit
> widening its own tool access or asking for code execution, and a held-out
> measurement over repeated runs with an exact paired test.
>
> In the recorded generation, five plausible strategies were proposed and all five
> were refused — the silent failure this project is built to catch. The memorising
> strategy bought +12.5 points on the data the search could see and +2 on the data it
> could not, which is overfitting wearing the costume of progress. The retrieval
> strategy made the harness measurably worse: 78.0% down to 62.0%, p=0.04, a
> regression no amount of reasoning about it would have predicted. One edit asked for
> more power and never ran: with its aggregation tool revoked the harness falls to
> 18.8%, asks for the privilege back, is refused, tries a banned operator instead, and
> is refused again — a human restores it, the harness cannot.
>
> The most useful finding was not in the harness at all: the sandbox was rejecting
> JavaScript regular expressions that mongosh accepts, so every version was being
> punished for output the database would have run. Repairing that ruler moved the same
> version from 65.6%/80.0% to 75.0%/88.0% without touching the harness. That repair is
> no longer a story, it is a command: `mh.cli audit-ruler` puts eleven statements to the
> sandbox in both spellings, the sugar a model writes and the strict Extended JSON that
> MongoDB equally accepts, and requires identical rows from both. Five more probes go
> the other way and must be refused. Sixteen probes, no model involved, and a
> fault-injection switch that proves the auditor can fail: with the historical defect
> switched back on it reports four divergences in seconds and exits non-zero. Every
> version,
> run, step, proposal and refusal is in the ledger, and a promotion is undone with one
> command. Everything in the repository was written during the event, in the
> hackathon's Atlas sandbox cluster; the only borrowed artefacts are MongoDB's own
> sample dataset and its published query guidance, both credited in the README.

## 5. What is honest about the limits

* The gate is only as strong as its verification set. If the held-out questions
  resemble the selection questions, a strategy that memorises them will look like
  progress. `replay_train_answers` is exactly that strategy, and the ledger shows
  what the gate did with it.
* The thresholds (noise margin, p-value) are ours and are documented in
  `mh/gate.py`; they are judgement calls, not laws.
* The harness edits configuration, not code. That is what makes each step auditable,
  and it is also the ceiling.
* The absolute numbers move between runs at temperature 0, because provider-side
  nondeterminism survives the setting. The same untouched version measured 68.8% and
  71.9% on the selection set in different runs; the verdicts on the five proposals did
  not change. What the gate compares is always candidate against incumbent inside one
  run.
* Statement Two's "billions of tokens in one session" is not demonstrated. The ledger
  currently holds 17 runs, 467 steps and 119 lessons. The mechanism is built to grow
  with the session; the scale is not claimed.
