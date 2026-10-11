# Interface contract — the harness that earns its edits

Everything in the repository is in **English** (public repo, US judges).
Secrets never in code: only `.env` (gitignored), read via `os.environ` / `python-dotenv`.

## Repository layout

```
mongo-harness/
  PLAN.md                  design notes (already written)
  INTERFACE.md             this contract
  README.md                public description (owner: lead)
  .env.example
  .gitignore
  requirements.txt
  mh/
    __init__.py
    config.py              env loading                     -> WORKER A (store)
    store.py               all MongoDB access              -> WORKER A (store)
    embed.py               text -> vector, 384 dims        -> LEAD
    tasks.py               ground-truth task suite         -> LEAD
    agent.py               harness config -> MQL           -> LEAD
    scorer.py              execute + compare to expected   -> LEAD
    gate.py                promotion decision + envelope   -> LEAD
    loop.py                the self-improvement loop       -> LEAD
    cli.py                 `python -m mh.cli ...`          -> LEAD
  scripts/
    init_atlas.py          collections + indexes           -> WORKER A
    load_mflix.py          load sample_mflix into Atlas    -> WORKER A
  tests/
    test_store_local.py    runs against docker mongo       -> WORKER A
  demo/
    run_demo.sh
```

## Worker A scope (mh/config.py, mh/store.py, scripts/*, tests/test_store_local.py)

Environment:
- `MONGODB_URI` — required, e.g. `mongodb://localhost:27017` locally or `mongodb+srv://...` for Atlas
- `MH_DB` — database name, default `harness`
- `MH_USE_VECTOR` — `1`/`0`, default `1`; when `0` or when `$vectorSearch` is unavailable (plain mongod),
  `vector_search()` must fall back to an in-process cosine similarity over the `lessons` collection.

`mh/store.py` must expose exactly:

```python
def get_db() -> pymongo.database.Database: ...
def ensure_schema(db=None) -> dict: ...          # create collections + MQL indexes, return what exists
def ok() -> dict: ...                            # {"ok": bool, "uri_kind": "atlas"|"local", "db": str, "server_version": str}

# writes
def record_run(doc: dict) -> str: ...            # returns inserted id as str
def record_step(doc: dict) -> str: ...
def record_version(doc: dict) -> str: ...        # doc has: version_id(int), config(dict), parent(int|None), created_at, fingerprint(str)
def record_edit(doc: dict) -> str: ...
def record_lesson(doc: dict) -> str: ...         # doc has: task_id, question, reason, failed_query, expected, got, embedding(list[float])

# reads
def latest_version() -> dict | None: ...
def get_version(version_id: int) -> dict | None: ...
def list_edits(limit: int = 50) -> list[dict]: ...
def run_score(run_id: str) -> dict: ...          # {"passed": int, "total": int, "rate": float}

# vector memory
def vector_search(query_vector: list[float], k: int = 5, db=None) -> list[dict]:
    """Return up to k lessons sorted by similarity desc, each with a `score` key."""

def vector_index_spec(name: str = "lessons_vec") -> dict: ...
def ensure_vector_index(db=None) -> dict:
    """Create the Atlas Vector Search index if the deployment is Atlas;
    if it is not (plain mongod), return {"created": False, "reason": "not_atlas"}.
    Must never raise on a local server."""
```

Collections and fields (all timestamps UTC `datetime`):

- `runs`: `run_id`, `version_id`, `suite` (`"train"`|`"holdout"`), `started_at`, `finished_at`, `total`, `passed`, `rate`, `notes`
- `steps`: `run_id`, `task_id`, `question`, `db`, `collection`, `generated_query`, `executed_ok`, `result_digest`, `expected_digest`, `passed`, `latency_ms`, `error`
- `lessons`: `task_id`, `question`, `reason` (`"wrong_result"`|`"invalid_query"`|`"exception"`), `failed_query`, `expected_digest`, `got_digest`, `embedding`, `created_at`
- `versions`: `version_id`, `config` (see below), `parent`, `created_at`, `fingerprint`, `promoted_by` (`"genesis"`|`"gate"`|`"manual"`)
- `edits`: `version_from`, `version_to`, `proposal` (the config diff), `rationale` (LLM text), `evidence` (`{"train_rate_before","train_rate_after","holdout_before","holdout_after","n_before","n_after"}`), `decision` (`"promoted"`|`"rejected_outsample"`|`"rejected_envelope"`|`"rejected_insignificant"`), `reason`, `created_at`, `rolled_back` (bool)
- `fetches`: `ts`, `tool`, `method`, `url`, `status`, `content_type`, `bytes`, `sha256`, `note` (provenance journal; secrets redacted)

Harness config shape (owned by the lead, stored verbatim in `versions.config`):

```json
{
  "system_prompt": "str",
  "rules": ["str", "..."],
  "cot": true,
  "sample_docs_n": 3,
  "include_indexes": true,
  "retrieve_k": 5,
  "tools": ["find", "aggregate", "count"]
}
```

Vector index (`vector_index_spec`): Atlas Vector Search, type `vector`, path `embedding`,
384 dimensions, similarity `cosine`, name `lessons_vec`.

`scripts/init_atlas.py` — ensures schema, tries to create the vector index, prints a readable
status report (what was created, whether the deployment is Atlas or local, the exact command to
create the index by hand if the API refused). Never prints the URI.

`scripts/load_mflix.py` — loads the `sample_mflix` dataset into the target database:
`movies`, `comments`, `theaters`, `users`, `sessions`. Preferred path: if `MONGODB_URI` points at
Atlas and `mongorestore` is unavailable, download the official sample BSON archive
(`https://atlas-education.s3.amazonaws.com/sample_mflix.archive`) and restore it with the
`mongorestore` binary if it exists, otherwise fall back to downloading the JSON collections from
the public sample-data dump and `insert_many`-ing in batches of 1000. It must be idempotent and
print progress counts at the end. Do not embed any credential.

`tests/test_store_local.py` — pytest, runs against `mongodb://localhost:27017` (docker `mh-mongo`),
uses a scratch database `harness_test`, drops it at the end. Must cover: ok(), ensure_schema(),
record/get version, record run + steps + run_score, record lesson + vector_search local fallback
(assert ordering by similarity), ensure_vector_index returning `not_atlas` without raising,
edits listing, and that `record_lesson` stores the embedding as a plain list of floats.

Rules: no new heavy dependencies beyond `pymongo`, `python-dotenv`, `pytest`; no network access at
import time; every public function has a docstring; no `print` inside `mh/` (use `logging`);
no data files committed to the repo.
