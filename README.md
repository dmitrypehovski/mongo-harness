# The harness that earns its edits

An agent harness that improves itself — and a gate that decides whether the
improvement is real.

Built for the **Harness Engineering & Model Wrangling** hackathon (SF Tech Week),
against **Statement 1: Recursive Harnessing**, with a deliberate reach into
**Statement 2: Long Horizon Engineering**: every run is kept in MongoDB, and the
harness starts each new attempt from what its own past failures taught it.

## The idea

Most self-improving agents edit their own prompt and then declare victory, because
nothing measures whether the edit helped. This one cannot do that: **a version only
becomes current if it survives a gate**, and the gate is code, not a sentence in a
prompt.

A *harness version* is a plain document in MongoDB. Everything the harness may
change about itself lives there:

| field | meaning |
|---|---|
| `system_prompt` | the instructions given to the model |
| `rules` | query-writing rules, added, rewritten or dropped |
| `cot` | whether the model reasons step by step first |
| `sample_docs_n` | how many real documents are shown in the context |
| `include_indexes` | whether collection indexes are shown |
| `retrieve_k` | how many similar past failures are pulled from memory |
| `replay_train_answers` | whether to reuse a query that worked on a similar earlier question |
| `tools` | which query shapes are allowed |

Because a version is data, every change is diffable, storable and reversible. There
is no code generation anywhere in the loop: the harness rewrites its own
**configuration**, which is what makes the whole thing auditable.

## The task suite

Questions in plain language about the `sample_mflix` dataset, each with a reference
query whose **result set** defines the right answer. The harness is never scored on
query text — any query that returns the right rows passes.

* **57 questions**, 32 for selecting edits and 25 for verifying them, across six
  families: filters, sorting and projection, aggregation, cross-collection joins,
  geography, and type traps.
* The split is fixed by hand so both halves cover every family. A promoted version
  cannot redraw the boundary to make itself look better.
* `scripts/check_tasks.py` verifies every reference query: it parses, runs twice,
  confirms the digest is stable, and looks one row past every cut-off to catch
  ambiguous "top N" questions where two correct queries could legitimately return
  different rows.

Two rules make the measurement fair:

* a document's `_id` is ignored for "find" answers (asking for titles should not
  fail because the identifier was or was not included), and kept for grouped
  answers, where the identifier *is* the group key;
* field naming is free — `{"count": 47}` and `{"movies": 47}` are the same answer —
  but returning extra fields, or the wrong number of rows, is not.

## The gate

Every proposed version is checked in this order.

1. **Envelope.** Refused before anything runs if it introduces unknown keys,
   touches `envelope_version`, empties the prompt, widens its own tool access, or
   adds a rule asking for `$where`, `$function`, `$accumulator`, `$out` or `$merge`.
   The harness cannot grant itself new powers.
2. **Selection set.** It has to do at least as well as the current version on the 32
   questions that drive the search.
3. **Verification set**, measured over repeated runs, because a single pass of 25
   questions cannot tell an improvement from a good day.
4. **Decision.** Promote only if the verification set improves by more than the
   noise margin and the paired test (exact McNemar) backs it. Otherwise the edit is
   refused, and the reason recorded is specific: `rejected_outsample` when the gain
   lives only on the selection set, `rejected_insignificant` when it is inside the
   noise, `rejected_envelope` when it tried to widen its own powers.

Every proposal — accepted or refused — is written to the `edits` ledger with its
evidence: rates before and after, sample sizes, discordant counts, p-value and a
sentence explaining the decision. A promotion is undone with one command.

## What MongoDB is doing here

* `versions`, `runs`, `steps`, `edits`, `lessons`, `fetches` — the harness's
  state, history and audit trail. Memory is the database, not the process: a new
  run rebuilds what it knows by querying the ledger.
* **Atlas Vector Search** over `lessons.embedding` — before answering, the harness
  retrieves the most similar past failures and puts them in the context. This is
  the long-horizon part: the harness gets better because it remembers, not because
  anyone retrained anything.
* **MQL indexes** on the ledger collections, and a `$vectorSearch` aggregation with
  an automatic fall back to in-process cosine similarity so the same code runs on a
  laptop and on Atlas.
* **`$lookup` across collections** — eight of the questions can only be answered by
  joining `movies` with `comments`.

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # then fill in MONGODB_URI and OPENROUTER_API_KEY

# a local MongoDB with the dataset loaded
docker run -d --name mh-mongo -p 27017:27017 mongo:7
bash scripts/load_mflix_local.sh

.venv/bin/python -m mh.cli init          # collections, starting version, reference answers
.venv/bin/python -m mh.cli run           # measure the current version, change nothing
.venv/bin/python -m mh.cli generation    # propose, measure, decide
.venv/bin/python -m mh.cli edits         # the ledger
.venv/bin/python -m mh.cli rollback      # undo the last promotion
.venv/bin/python -m mh.cli demo          # the scripted demonstration
bash demo/gate_proof.sh                  # the two guards, on outcomes no model decides
```

Against Atlas:

```bash
export MONGODB_URI='mongodb+srv://...'
bash scripts/restore_to_atlas.sh          # the dataset, the harness schema, the vector index
.venv/bin/python scripts/ensure_dataset_indexes.py   # the join key the questions need
.venv/bin/python -m mh.cli init
.venv/bin/python -m mh.cli run
```

`restore_to_atlas.sh` loads the official sample dump, creates the ledger collections,
their MQL indexes and the `lessons_vec` Atlas Vector Search index. The second step is
not optional: the Atlas dump arrives with nothing but the default indexes, so the
eight questions that join `comments` with `movies` on `comments.movie_id` scan the
whole collection and hit the server-side time limit before the reference answers can
even be computed. The first time this ran against Atlas, that is exactly what
happened, and it is the kind of failure that only shows up on the real cluster.

## Results

**The measuring instrument was wrong before anything else was.** The sandbox
rejected JavaScript regular expressions — `{ email: /@example\.com$/ }` — which
mongosh accepts, so every version was being punished for output the database would
have run happily. Fixing the sandbox and changing nothing else moved the same
version from **65.6% / 80.0%** to **75.0% / 88.0%** on the two suites, and removed
every parse failure. Most of what looks like progress in a self-improving system is
a repair to the ruler.

One generation at temperature 0, both suites measured twice over the repeats:

* current version: selection set **22/32 = 68.8%**, verification set **78.0%**

| proposal | selection | verification | decision |
|---|---|---|---|
| write the rules down instead of rediscovering them | 68.8% → 68.8% | 78.0% → 84.0% (5 gained, 2 lost, p=0.45) | `rejected_insignificant` — real, but under the margin |
| remember what already worked | 68.8% → **81.3%** | 78.0% → 80.0% | `rejected_insignificant` — +12.5 points where the search can see, +2 where it cannot |
| express hard filters in JavaScript | — | — | `rejected_envelope` — a rule asked for `$where` |
| return exactly what was asked for | 68.8% → 75.0% | 78.0% → 76.0% | `rejected_regression` |
| learn from the questions it keeps getting wrong | 68.8% → 59.4% | 78.0% → 66.0% | `rejected_regression` |

**Nothing was promoted in this generation.** Every proposal, its measurements, the
decision and the reason are in the ledger; `mh.cli edits` prints them. That is the
result the harness is built to produce: five plausible ways to improve itself, none
of them provable, and not one of them taken on the strength of how good the idea
sounded.

Two of the refusals are worth reading twice. The memorising strategy — reuse the
query that worked on a nearly identical earlier question — bought **+12.5 points on
the selection set and +2 on the verification set**. It is the exact shape of
overfitting, and it looks like the best idea in the table until the second column
is read. The retrieval strategy — put the most similar past failures into the
context — made the harness *worse* (78.0% → 66.0%), which no amount of reasoning
about it would have predicted and which the measurement says plainly.

The same generation was then run **on Atlas**, against the cluster instead of a local
server, with the ledger, the searches and the vector index all living there: the same
five proposals produced the same five refusals, and the retrieval strategy was worse
again (78.0% → 62.0%, p=0.04). The verdicts did not depend on where the data was.

### On Atlas

The whole loop also runs on the cluster, not just the dataset: the ledger collections,
their indexes and the `lessons_vec` Vector Search index live there, and the harness
reads its own failures back out of Atlas. The nearest-neighbour query is a real
`$vectorSearch` against that index — the harness falls back to cosine similarity
in-process only when the cluster is a plain MongoDB, so the same code runs in both
places without branching in the agent.

### On run-to-run variation

The same version measured 68.8% / 78.0% inside this generation and 75.0% / 88.0% in
a separate process minutes earlier, at temperature 0. Provider-side nondeterminism
survives the temperature setting, and it is larger than most edits. This is why the
gate compares two versions inside the same generation, repeats every verification
question, pools the paired observations, and refuses anything under an eight point
margin even when the direction looks right.

## What this does not do

* It does not generate code. It edits configuration. That is the point, and it is
  also the limit: it can only improve along axes someone thought to put in the
  version document.
* The gate is only as good as its verification set. If the verification questions
  resemble the selection questions, a strategy that memorises them will look like
  progress. Memory reuse (`replay_train_answers`) is exactly such a strategy, and
  the ledger shows what the gate did with it and why.
* The thresholds — the noise margin, the p-value — are ours, documented in
  `mh/gate.py`. They are judgement calls, not laws of nature.
* Models drift between runs. Every holdout measurement is repeated, and the spread
  is visible in the ledger, but a small true gain can still hide under it.
