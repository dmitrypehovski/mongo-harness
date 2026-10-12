"""The harness under test: it turns questions into queries, and edits itself.

A *harness version* is a plain dictionary (see ``GENESIS``) stored verbatim in
MongoDB. Everything the harness can change about itself lives in that dictionary,
which is what makes self-improvement auditable: a version is data, not code.

Two model calls happen here:

* :func:`solve` — one question in, one query out.
* :func:`propose_edits` — the harness looks at its own failures and proposes
  several candidate versions of itself.
"""

from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

from bson import json_util

from mh import embed, llm, schema, scorer, tasks
from mh.tasks import TASKS

log = logging.getLogger(__name__)

#: Everything the harness may change about itself. Anything outside this list is
#: refused by the envelope, so a version can never smuggle in a new power.
EDITABLE_KEYS = (
    "system_prompt",
    "rules",
    "cot",
    "sample_docs_n",
    "include_indexes",
    "retrieve_k",
    "replay_train_answers",
    "tools",
)

#: Keys the envelope freezes: they exist in a version but no edit may touch them.
FROZEN_KEYS = ("envelope_version",)

REPLAY_THRESHOLD = float(os.environ.get("MH_REPLAY_THRESHOLD", "0.93"))

SCHEMA_TEXT = """Database: sample_mflix

collection movies — one document per film
  _id            string  (the identifier, not an ObjectId)
  title          string
  year           int     (release year; ranges from 1896 to 2014)
  runtime        int     minutes
  rated          string  content rating, e.g. "G", "PG", "PG-13", "R", "TV-G"; may be missing
  genres         array of strings, e.g. ["Action", "Comedy"]; may be missing
  cast           array of strings (actors); may be missing
  directors      array of strings; may be missing
  writers        array of strings; may be missing
  countries      array of strings, e.g. ["USA", "UK"]; may be missing
  languages      array of strings, e.g. ["English", "French"]
  released       date    full release date; may be missing
  plot           string  short description
  type           string  "movie"
  awards         object  { "wins": int, "nominations": int, "text": string }
  imdb           object  { "rating": double, "votes": int, "id": int }
  tomatoes       object  { "viewer": {"rating": double, "numReviews": int, "meter": int},
                           "critic": {"rating": double, "numReviews": int, "meter": int},
                           "fresh": int, "rotten": int }
                 the field may be missing entirely, and some documents store
                 numbers as strings or leave sub-fields out

collection comments — one document per comment written about a movie
  _id            string
  name           string  the commenter's name
  email          string
  movie_id       string  matches movies._id
  text           string
  date           date

collection theaters — one document per cinema
  _id            string
  theaterId      int
  location       object  { "address": {"street1": string, "city": string, "state": string,
                                       "zipcode": string},
                           "geo": {"type": "Point", "coordinates": [longitude, latitude]} }
"""

GENESIS: dict = {
    "envelope_version": 1,
    "system_prompt": (
        "You are an expert MongoDB developer. Given the schema of a database and a question in "
        "plain language, you write one MongoDB query that answers the question.\n"
        "Reply with the query only."
    ),
    "rules": [],
    "cot": False,
    "sample_docs_n": 0,
    "include_indexes": False,
    "retrieve_k": 0,
    "replay_train_answers": False,
    "tools": ["find", "aggregate", "count"],
}

#: What the starting version becomes once the search has had its way — kept here so
#: the repository shows the difference between where it began and what it found.
MONGO_GUIDANCE_RULES = [
    "Use the operator that matches the question: $gt/$gte/$lt/$lte for ranges, $in for membership, "
    "$regex with $options for text patterns.",
    "Match the stored type exactly: compare numbers with numbers, strings with strings.",
    "Return only the fields the question asks about, and add \"_id\": 0 to the projection so the "
    "identifier is not returned unless the question asks for it.",
    "When the question asks for a number of items (\"how many\", \"the 5 largest\"), use a limit or a "
    "count so the result size matches the question.",
    "When the question asks for the top N by some measure, sort on that measure and add a second "
    "sort key so the order is fully determined.",
    "Treat fields as possibly missing: use $exists or $type instead of assuming a field is always there.",
    "For array fields use $all, $size, $elemMatch or plain membership instead of comparing the whole array.",
    "For questions that span two collections use $lookup on movies._id <-> comments.movie_id.",
    "Never use $where, $function, $accumulator, $out or $merge.",
]

#: A tempting but overfitting strategy: reuse the query that worked on a very
#: similar training question. The gate is what refuses it.
STRATEGY_MENU = [
    "add, rewrite or drop rules (the rules list is yours)",
    "turn step-by-step reasoning on or off (cot)",
    "change how many sample documents are put in the context (sample_docs_n, 0-5)",
    "show or hide the collection indexes (include_indexes)",
    "change how many similar past failures are retrieved from memory (retrieve_k, 0-10)",
    "memorise training questions and reuse their earlier working query when a nearly identical "
    "question appears (replay_train_answers)",
    "narrow the set of query shapes the harness may use (tools, a subset of find, aggregate, count)",
]


def _sample_documents(db, count: int) -> str:
    """Render a few real documents as Extended JSON for the context."""
    if count <= 0:
        return ""
    blocks = []
    for collection in ("movies", "comments", "theaters"):
        try:
            document = db[collection].find_one({}, {"_id": 1, "title": 1, "year": 1, "runtime": 1,
                                                   "genres": 1, "cast": 1, "rated": 1, "imdb": 1,
                                                   "awards": 1, "tomatoes": 1, "released": 1,
                                                   "location": 1, "movie_id": 1, "date": 1})
        except Exception:
            continue
        if document:
            text = json_util.dumps(document)
            blocks.append(f"{collection} sample document:\n{text[:count * 400]}")
    return "\n\n".join(blocks)


def _indexes(db) -> str:
    """Render the indexes of the collections the questions touch."""
    lines = []
    for collection in ("movies", "comments", "theaters"):
        try:
            names = [list(index["key"].items()) for index in db[collection].list_indexes()]
        except Exception:
            continue
        lines.append(f"{collection}: " + ", ".join(str(name) for name in names))
    return "\n".join(lines)


def _lessons_block(lessons: list[dict]) -> str:
    """Render retrieved memories of similar past failures.

    The failed query itself is deliberately left out. Showing a model its own wrong
    query is an invitation to repeat it, and the first version of this block did
    exactly that: including it made the version measurably worse.
    """
    if not lessons:
        return ""
    lines = ["Questions like these were answered wrongly before. What went wrong:"]
    for lesson in lessons[:5]:
        lines.append(
            f"- {lesson.get('question', '')[:140]}\n"
            f"  why it failed: {str(lesson.get('reason', ''))[:180]}"
        )
    return "\n".join(lines)


def schema_text(db=None) -> str:
    """The description of the database the agent is given.

    The shipped questions keep the shipped film description, byte for byte, so the numbers already
    in the record were measured with the same apparatus. Any other question set gets a description
    read out of the database it is asked against: an agent told about movies, pointed at a cafe,
    answers "there is no orders collection here" instead of answering the question, which is exactly
    what happened the first time this ran on data it had not seen.
    """
    if not tasks.is_generated():
        return SCHEMA_TEXT
    database = tasks.pack_database()
    collections = tasks.pack_collections()
    fallback = f"Database: {database}\nCollections in play: {', '.join(collections)}"
    if db is None:
        return fallback
    try:
        return schema.describe(db, database, collections)
    except Exception as exc:  # noqa: BLE001 - a description that fails must not stop the measurement
        log.warning("could not describe %s: %s", database, exc)
        return fallback


def build_messages(config: dict, task: dict, lessons: list[dict], db) -> list[dict]:
    """Build the chat messages for one question under one harness version."""
    system = config.get("system_prompt", "")
    rules = config.get("rules") or []
    if rules:
        system += "\nRules:\n" + "\n".join(f"{number}. {rule}" for number, rule in enumerate(rules, 1))
    if config.get("cot"):
        system += (
            "\nThink it through first: name the collection, the fields, the operators and the edge "
            "cases. Then output the final query as the last line of your answer, starting with db."
        )

    parts = [schema_text(db)]
    samples = _sample_documents(db, int(config.get("sample_docs_n") or 0))
    if samples:
        parts.append(samples)
    if config.get("include_indexes"):
        parts.append("Indexes:\n" + _indexes(db))
    memory = _lessons_block(lessons)
    if memory:
        parts.append(memory)
    parts.append(f"Question: {task['question']}")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def _similarity(left: str, right: str) -> float:
    """Cosine similarity of two short texts, used by the replay strategy."""
    vectors = embed.embed([left, right])
    if len(vectors) != 2:
        return 0.0
    return embed.cosine(vectors[0], vectors[1])


def replay_lookup(task: dict, bank: list[dict]) -> dict | None:
    """Find a nearly identical training question that already has a working query."""
    if not bank:
        return None
    best: tuple[float, dict] | None = None
    for entry in bank:
        if entry.get("task_id") == task["id"] or not entry.get("query"):
            continue
        score = _similarity(task["question"], entry.get("question", ""))
        if score >= REPLAY_THRESHOLD and (best is None or score > best[0]):
            best = (score, entry)
    return best[1] if best else None


def extract_query(raw: str) -> str:
    """The query inside the model's answer, whatever else came with it.

    Models wrap the query in markdown fences, open with a sentence, and break it across lines.
    Taking the last line of the answer — which is what this used to do — turns a perfectly good
    multi-line query into ``])``, and the harness then records a failure that belongs to the
    extractor rather than to the model. So the query is cut out properly instead: from the first
    ``db.`` to the point where its brackets balance, continuing past that point while the answer
    is still chaining another call (``.sort()``, ``.limit()``).
    """
    text = re.sub(r"```[a-zA-Z]*", " ", raw or "").replace("`", " ")
    start = text.find("db.")
    if start == -1:
        return text.strip()

    depth, quote, escaped = 0, "", False
    for index in range(start, len(text)):
        character = text[index]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
            continue
        if character in "\"'":
            quote = character
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
            if depth <= 0 and not re.match(r"\s*\.", text[index + 1 :]):
                return text[start : index + 1].strip()
    return text[start:].strip()


def solve(config: dict, task: dict, db, lessons: list[dict], bank: list[dict] | None = None) -> dict:
    """Answer one question under one harness version.

    Returns a dict with the raw model output, the parsed query when it parsed, and
    the execution outcome. Failures are values here, never exceptions: a version
    that produces broken queries has to be measurable.
    """
    used_replay = False
    raw = ""
    if config.get("replay_train_answers") and bank:
        replayed = replay_lookup(task, bank)
        if replayed:
            raw = replayed["query"]
            used_replay = True

    if not used_replay:
        try:
            raw = llm.chat(
                build_messages(config, task, lessons, db),
                temperature=float(os.environ.get("MH_TEMPERATURE", "0.1")),
                max_tokens=int(os.environ.get("MH_MAX_TOKENS", "900")),
            )
        except llm.ModelError as exc:
            return {
                "task_id": task["id"],
                "question": task["question"],
                "raw": "",
                "query": "",
                "status": "model_error",
                "error": str(exc)[:300],
                "passed": False,
                "reason": f"the model could not be reached: {str(exc)[:120]}",
            }

    query_text = extract_query(raw)
    try:
        mql = scorer.parse_mql(query_text)
    except scorer.ParseError as exc:
        return {
            "task_id": task["id"],
            "question": task["question"],
            "raw": raw[:600],
            "query": query_text[:600],
            "status": "invalid_query",
            "error": str(exc)[:300],
            "passed": False,
            "reason": f"the generated text was not a readable read-only query: {str(exc)[:120]}",
            "replayed": used_replay,
        }

    execution = scorer.execute(db, mql, config.get("tools"))
    return {
        "task_id": task["id"],
        "question": task["question"],
        "raw": raw[:600],
        "query": mql.canonical(),
        "readable_query": " ".join(query_text.split())[:400],
        "status": execution.status,
        "error": execution.error[:300],
        "rows": len(execution.rows),
        "rows_full": execution.rows,
        "digest": execution.digest,
        "latency_ms": execution.latency_ms,
        "passed": False,  # decided by the caller against the reference answer
        "replayed": used_replay,
    }


def check_tools_in_use(results: list[dict]) -> dict:
    """Count which query shapes the version actually used."""
    counts: dict[str, int] = {}
    for result in results:
        query = result.get("query") or ""
        for shape in ("aggregate", "countDocuments", "find"):
            if f".{shape}(" in query:
                counts[shape] = counts.get(shape, 0) + 1
                break
    return counts


PROPOSAL_PROMPT = """You are improving an agent harness that answers questions about a MongoDB \
database by writing queries. You cannot change the model or the task suite; you can only change the \
harness configuration.

Here is the current configuration:
{config}

Here is how it performs now: {train_passed}/{train_total} correct on the selection set \
({train_rate:.1%}), {holdout_passed}/{holdout_total} correct on the verification set ({holdout_rate:.1%}).

These are the questions it currently gets wrong:
{failures}

{memory}

How the harness is scored: a question counts as correct only when the rows returned by the generated \
query match the rows returned by a reference query, so a query that returns the right documents with \
the wrong fields, or a wrong number of them, fails.

Propose exactly {want} different candidate configurations. Make them genuinely different from each \
other and from the current one: a version that changes nothing is useless, and trying several \
directions at once is how you find what works. You may change any of these:
{menu}

Reply with a JSON array, nothing else. Each element:
{{"strategy": "short name of the idea",
  "reasoning": "why you expect this to raise the number of correct answers, in one or two sentences",
  "config": {{ ...the COMPLETE new configuration, same keys as now, not a diff... }}}"""


def _format_failures(results: list[dict], limit: int = 8) -> str:
    """Render the questions the current version fails."""
    lines = []
    for result in results:
        if result.get("passed"):
            continue
        if len(lines) >= limit:
            break
        lines.append(
            f"- {result['question'][:130]}\n"
            f"  what it produced: {str(result.get('readable_query') or result.get('query') or '')[:180]}\n"
            f"  what went wrong: {str(result.get('reason') or result.get('error') or '')[:140]}"
        )
    return "\n".join(lines) or "- nothing, it answers every question in the selection set correctly"


def propose_edits(
    config: dict,
    train_results: list[dict],
    holdout_rate: float,
    train_rate: float,
    memories: list[dict],
    want: int = 4,
) -> list[dict]:
    """Ask the harness to propose several new versions of itself."""
    prompt = PROPOSAL_PROMPT.format(
        config=json.dumps(config, indent=2, ensure_ascii=False),
        train_passed=sum(1 for r in train_results if r.get("passed")),
        train_total=len(train_results),
        train_rate=train_rate,
        holdout_passed=int(round(holdout_rate * len([t for t in TASKS if t['split'] == 'holdout']))),
        holdout_total=len([task for task in TASKS if task["split"] == "holdout"]),
        holdout_rate=holdout_rate,
        failures=_format_failures(train_results),
        memory=_lessons_block(memories) or "No similar failures are stored yet.",
        menu="\n".join(f"- {item}" for item in STRATEGY_MENU),
        want=want,
    )
    text = llm.chat(
        [{"role": "user", "content": prompt}],
        temperature=float(os.environ.get("MH_PROPOSAL_TEMPERATURE", "0.7")),
        max_tokens=int(os.environ.get("MH_PROPOSAL_TOKENS", "3000")),
    )
    return _parse_proposals(text)


def _parse_proposals(text: str) -> list[dict]:
    """Extract the proposed configurations from the model's reply."""
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        log.warning("no JSON array in the proposal reply")
        return []
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        log.warning("proposal reply is not valid JSON: %s", exc)
        return []
    proposals = []
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("config"), dict):
            proposals.append(
                {
                    "strategy": str(item.get("strategy", "unnamed"))[:80],
                    "reasoning": str(item.get("reasoning", ""))[:600],
                    "config": item["config"],
                }
            )
    return proposals


def fan_out(function, items: list, workers: int | None = None) -> list:
    """Run a function over items in parallel, preserving order."""
    size = int(workers or os.environ.get("MH_WORKERS", "6"))
    if size <= 1 or len(items) <= 1:
        return [function(item) for item in items]
    with ThreadPoolExecutor(max_workers=size) as pool:
        return list(pool.map(function, items))
