"""Give the harness an exam it has never seen: build a task suite from any database.

The harness can only judge an agent against questions whose right answer is known. On
sample_mflix those questions were written by hand. On someone else's database nobody is
going to write them, so this module writes them, and then throws most of them away.

How it works, in order:

1. **Look at the data.** List the collections, sample a few documents from each, and
   describe their shape — field paths, types, example values.
2. **Ask the model for candidates.** For each collection, a batch of questions in plain
   language, each with a reference query that answers it.
3. **Throw away everything that does not survive contact with the database.** Every
   candidate reference query is parsed, checked to be read-only, executed, and executed
   again. A query that does not run, or that returns a different result the second time,
   is dropped with its reason. This is the point of the whole exercise: a generated
   question is only usable as an exam if its answer is stable, and the only way to know
   that is to run it twice against the real collection.
4. **Split what survives.** Both halves get every family that survived, so the gate can
   compare a change on the split the agent is tuned on and the split it is not.

    from mh import scaffold

    report = scaffold.build(db, database="shop", collections=["orders"], want=12)
    print(report.summary())
    scaffold.write_pack(report, "datasets/shop.json")
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import bson

from mh import datasets, llm, scorer

log = logging.getLogger(__name__)

READ_ONLY_TOOLS = ["find", "aggregate", "count"]
MAX_SHAPE_CHARS = 6000


@dataclass
class Candidate:
    """One proposed question and the query that answers it."""

    question: str
    reference: str
    collection: str
    family: str = "find"
    id: str = ""
    rows: int | None = None
    status: str = "pending"
    reason: str = ""
    clarified: str = ""


@dataclass
class Report:
    """What the scaffolding produced, and what it refused to use."""

    database: str
    kept: list[Candidate] = field(default_factory=list)
    dropped: list[Candidate] = field(default_factory=list)
    collections: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        """Counts for printing and for the record."""
        return {
            "database": self.database,
            "collections": self.collections,
            "candidates": len(self.kept) + len(self.dropped),
            "kept": len(self.kept),
            "clarified": sum(1 for candidate in self.kept if candidate.clarified),
            "dropped": len(self.dropped),
            "drop_reasons": {
                reason: sum(1 for candidate in self.dropped if candidate.reason == reason)
                for reason in sorted({candidate.reason for candidate in self.dropped})
            },
            "families": sorted({candidate.family for candidate in self.kept}),
        }


# ----------------------------------------------------------------- inspecting the data


def collections_overview(db, limit: int = 12) -> list[dict]:
    """Every collection with a document count, largest first."""
    overview = []
    for name in sorted(db.list_collection_names()):
        if name.startswith("system."):
            continue
        try:
            overview.append({"collection": name, "documents": db[name].estimated_document_count()})
        except Exception as exc:  # a collection we are not allowed to read
            log.warning("cannot count %s: %s", name, exc)
    overview.sort(key=lambda entry: entry["documents"], reverse=True)
    return overview[:limit]


def describe_shape(db, collection: str, sample: int = 3) -> str:
    """A short description of one collection's shape, for the model to write against."""
    lines = [f"collection: {collection}", f"documents: {db[collection].estimated_document_count()}"]
    seen: dict[str, set[str]] = {}
    for document in db[collection].find({}).limit(sample):
        for key, value in document.items():
            kind = type(value).__name__
            seen.setdefault(key, set()).add(kind)
    for key in sorted(seen):
        lines.append(f"  {key}: {', '.join(sorted(seen[key]))}")
    example = db[collection].find_one({}, {"_id": 0})
    if example:
        lines.append("  example document: " + json.dumps(example, default=str)[:600])
    return "\n".join(lines)[:MAX_SHAPE_CHARS]


# ------------------------------------------------------------------- asking the model

PROMPT = """You write exam questions for a database agent.

Given the shape of the data below, write {want} questions in plain English, each with a
MongoDB query whose result set is the correct answer.

Rules:
- The question must be answerable from the fields shown, and phrased the way a person would ask.
- The query must be read only: db.<collection>.find(...), db.<collection>.aggregate([...]) or
  db.<collection>.countDocuments(...).
- Use Extended JSON for dates and identifiers.
- Every query that returns several rows must sort with a tie breaker, so the same rows come
  back in the same order every time.
- Vary the families: filters, ranges, membership, arrays, dotted paths, grouping, counting.

Answer with JSON only, no prose and no markdown fences:

[{{"family": "find|aggregate|count", "collection": "<name>", "question": "...", "reference": "db...."}}]

Data:
{shape}
"""


def _repair_escapes(text: str) -> str:
    """Double the backslashes the model left single inside strings.

    A query like ``{"$regex": "\\d{5}"}`` is not valid JSON: the model writes regex escapes
    as if the string were a Python literal. Doubling them is safe — the extra slash only ever
    appears inside a string, where it is exactly what was meant.
    """
    return re.sub(r'\\(?!["\\\\/bfnrtu])', r"\\\\", text)


def _load_lenient(text: str):
    """Parse JSON that came out of a model: control characters and regex escapes allowed."""
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        return json.loads(_repair_escapes(text), strict=False)


def _complete_objects(text: str) -> list[dict]:
    """Pull out every complete JSON object, ignoring prose and truncated tails.

    A reasoning model can run out of output budget halfway through its list. The objects it
    did finish are still usable, so they are recovered instead of the whole batch being lost.
    """
    objects: list[dict] = []
    # braces are matched by hand because the batch may be cut off mid-object
    depth, start, in_string, escaped = 0, None, False, False
    for index, character in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            if depth == 0:
                start = index
            depth += 1
        elif character == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    objects.append(_load_lenient(text[start : index + 1]))
                except json.JSONDecodeError as exc:
                    log.warning("skipped an unreadable object at offset %s: %s", start, exc)
                start = None
    return objects


def _parse_candidates(text: str, collections: list[str]) -> list[Candidate]:
    """Read the model's answer, tolerating the fences, prose and truncation it adds."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    if not cleaned:
        raise ValueError("the model returned nothing at all")
    try:
        raw = _load_lenient(cleaned)
    except json.JSONDecodeError:
        raw = _complete_objects(cleaned)
    if not isinstance(raw, list) or not raw:
        raise ValueError("the model did not return a JSON list of questions")
    if len(raw) < 3:
        log.warning("the model returned only %s questions", len(raw))
    candidates = []
    for item in raw:
        question = str(item.get("question") or "").strip()
        reference = str(item.get("reference") or "").strip()
        collection = str(item.get("collection") or "").strip()
        if not question or not reference:
            continue
        if collection not in collections:
            collection = collections[0] if collections else ""
        candidates.append(
            Candidate(
                question=question,
                reference=reference,
                collection=collection,
                family=str(item.get("family") or "find").strip().lower(),
            )
        )
    return candidates


def propose(
    db,
    collections: list[str],
    want: int,
    model: str | None = None,
    batch: int = 4,
    attempts: int = 3,
) -> list[Candidate]:
    """Ask the model for candidate questions, a few at a time and with second chances.

    Two things this has to survive, both seen in practice with a reasoning model: it can spend
    its whole output budget thinking and return an empty answer, and it can be cut off
    mid-list. So the questions are asked for in small batches, an empty or unreadable answer
    is retried, and whatever complete questions came back are used even if the batch was cut
    short. Nothing here decides whether a question is good — that is :func:`verify`.
    """
    shape = "\n\n".join(describe_shape(db, name) for name in collections)
    candidates: list[Candidate] = []
    remaining = want
    while remaining > 0:
        ask = min(batch, remaining)
        remaining -= ask
        for attempt in range(1, attempts + 1):
            try:
                message = llm.chat_raw(
                    [{"role": "user", "content": PROMPT.format(want=ask, shape=shape)}],
                    model=model,
                    temperature=0.4 if attempt == 1 else 0.2,
                    # the reasoning spend counts against this budget, so leave headroom
                    max_tokens=max(4000, 700 * ask),
                    retries=2,
                )
            except llm.ModelError as exc:
                log.warning("asking for questions failed: %s", exc)
                continue
            text = llm.message_text(message)
            if not text:
                log.warning("empty answer on attempt %s/%s", attempt, attempts)
                continue
            try:
                got = _parse_candidates(text, collections)
            except ValueError as exc:
                log.warning("unreadable answer on attempt %s/%s: %s", attempt, attempts, exc)
                continue
            candidates.extend(got)
            break
    return candidates


# --------------------------------------------------- the part that matters: verification


def _fingerprint(text: str) -> str:
    """A question's identity: whitespace and case cannot be allowed to make two of one."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def deduplicate(candidates: list[Candidate]) -> tuple[list[Candidate], list[Candidate]]:
    """Split candidates into the ones worth verifying and the repeats.

    Asking the model for questions in batches makes it cover the same ground twice: two
    batches over the same collection produced two identical questions about the same city and
    two identical group-by-state aggregations. Left in, the exam would look twice as big as it
    is and would weigh one easy idea twice in every measurement.
    """
    seen_questions: set[str] = set()
    seen_queries: set[str] = set()
    unique: list[Candidate] = []
    repeats: list[Candidate] = []
    for candidate in candidates:
        by_question = _fingerprint(candidate.question)
        by_query = _fingerprint(candidate.reference)
        if by_question in seen_questions or by_query in seen_queries:
            candidate.status = "dropped"
            candidate.reason = "the same question was already asked"
            repeats.append(candidate)
            continue
        seen_questions.add(by_question)
        seen_queries.add(by_query)
        unique.append(candidate)
    return unique, repeats


def verify(db, candidate: Candidate) -> Candidate:
    """Run a candidate's reference query twice and keep it only if it is stable.

    A question whose answer moves between two runs of the same query cannot be used to
    judge anything: every later measurement against it would be measuring the drift.
    """
    try:
        parsed = scorer.parse_mql(candidate.reference)
    except Exception as exc:
        candidate.status, candidate.reason = "dropped", "the query could not be parsed"
        log.info("dropped (%s): %s", candidate.reason, exc)
        return candidate

    if getattr(parsed, "collection", candidate.collection) != candidate.collection:
        candidate.status, candidate.reason = "dropped", "the query reads a different collection"
        return candidate

    first = scorer.execute(db, parsed, READ_ONLY_TOOLS)
    if not first.ok:
        candidate.status, candidate.reason = "dropped", "the query does not run"
        log.info("dropped (%s): %s", candidate.reason, first.error)
        return candidate

    second = scorer.execute(db, parsed, READ_ONLY_TOOLS)
    if not second.ok:
        candidate.status, candidate.reason = "dropped", "the query only ran once"
        return candidate

    if json.dumps(first.rows, default=str) != json.dumps(second.rows, default=str):
        candidate.status, candidate.reason = "dropped", "the answer moved between two runs"
        return candidate

    if not getattr(parsed, "method", "") == "countDocuments" and not first.rows:
        candidate.status, candidate.reason = "dropped", "the query returns no rows"
        return candidate

    mismatch = _shape_mismatch(candidate, parsed)
    if mismatch and not candidate.clarified:
        candidate.status, candidate.reason = "dropped", mismatch
        return candidate

    candidate.status, candidate.reason, candidate.rows = "kept", "", len(first.rows)
    return candidate


#: Words that mean the question is asking for particular fields back.
_ASKS_FOR_FIELDS = re.compile(
    r"\b(return|show|list|give)\b[^.]*?\b(id|title|name|city|state|count|total|number)\b",
    re.IGNORECASE,
)


def _shape_mismatch(candidate: Candidate, parsed) -> str:
    """Reasons a question and its reference disagree about the shape of the answer.

    Found by measuring a generated exam: the harness marked the agent wrong for grouping a count
    under ``count`` when the reference called it ``theaterCount`` — a name the question never
    mentioned — and for projecting the fields the question asked for while the reference returned
    whole documents. Both are the reference being unfair, not the agent being wrong, and an exam
    that decides like that cannot be used to judge anything.
    """
    question = candidate.question
    reference = candidate.reference

    if "$group" in reference:
        # only the fields the grouping produces are names the question has to have chosen
        grouped = reference.split("$group", 1)[1]
        for field in re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:', grouped):
            if field != "_id" and field.lower() not in question.lower():
                return f"the reference returns a field ({field}) the question never names"

    elif _ASKS_FOR_FIELDS.search(question) and not _limits_fields(reference):
        return "the question asks for particular fields but the reference returns whole documents"
    return ""


def clarify(candidate: Candidate) -> Candidate:
    """Make the question say what shape the answer has, when it otherwise would not.

    A question like *"how many theatres does each state have?"* has more than one right answer:
    the asking person gets their counts whichever key the count sits under. Measured literally,
    the reference called one of them wrong for naming the key ``state`` instead of ``_id`` — the
    agent was right and the exam was ambiguous. Dropping every such question would leave the
    exam without a single aggregation, so the question is made precise instead: it now states the
    shape of the answer, and every later measurement is against a question that says what it wants.
    """
    fields = _group_output_fields(candidate.reference)
    if fields:
        spelled = ", ".join(f"`{field}`" for field in fields)
        candidate.question = f"{candidate.question} Return each row with the keys {spelled}."
        candidate.clarified = "named the keys of each row"
    elif "$group" not in candidate.reference and _ASKS_FOR_FIELDS.search(
        candidate.question
    ) and not _limits_fields(candidate.reference):
        candidate.question = f"{candidate.question} Return whole documents, without limiting the fields."
        candidate.clarified = "said the answer is whole documents"
    return candidate


def _group_output_fields(reference: str) -> list[str]:
    """The keys an aggregation's grouping produces, in the order the query names them."""
    marker = reference.find("$group")
    if marker == -1:
        return []
    opening = reference.find("{", marker)
    if opening == -1:
        return []
    depth, index = 0, opening
    while index < len(reference):
        character = reference[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                break
        index += 1
    return re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:', reference[opening : index + 1])


def _limits_fields(reference: str) -> bool:
    """Whether a query returns chosen fields rather than whole documents.

    Either form counts: an aggregation stage, or the second argument of ``find``, which is
    where a plain query puts its projection.
    """
    if "$project" in reference:
        return True
    opening = reference.find("find(")
    if opening == -1:
        return False
    index, depth, comma_inside = opening + len("find("), 1, False
    while index < len(reference) and depth:
        character = reference[index]
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
        elif character == "," and depth == 1:
            comma_inside = True  # the argument after the filter is a projection
        index += 1
    return comma_inside


def assign_splits(candidates: list[Candidate]) -> list[Candidate]:
    """Give both splits every family, by alternating within each family."""
    by_family: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        by_family.setdefault(candidate.family, []).append(candidate)

    ordered: list[tuple[Candidate, str]] = []
    for family in sorted(by_family):
        for index, candidate in enumerate(by_family[family]):
            ordered.append((candidate, "train" if index % 2 == 0 else "holdout"))

    # a one-family database would otherwise land everything in train
    if not any(split == "holdout" for _, split in ordered) and ordered:
        ordered[-1] = (ordered[-1][0], "holdout")
    if not any(split == "train" for _, split in ordered) and ordered:
        ordered[0] = (ordered[0][0], "train")

    result = []
    for index, (candidate, split) in enumerate(ordered, 1):
        candidate.id = f"g{index:02d}"
        setattr(candidate, "split", split)
        result.append(candidate)
    return result


def build(
    db,
    database: str,
    collections: list[str] | None = None,
    want: int = 12,
    model: str | None = None,
) -> Report:
    """Inspect, propose, verify, split: a usable exam with its refusals listed."""
    overview = collections_overview(db)
    names = collections or [entry["collection"] for entry in overview[:3]]
    report = Report(database=database, collections=names)
    if not names:
        return report

    try:
        candidates = propose(db, names, want, model=model)
    except Exception as exc:
        log.warning("could not propose questions: %s", exc)
        return report

    unique, repeats = deduplicate(candidates)
    report.dropped.extend(repeats)
    log.info("%s candidates, %s of them new", len(candidates), len(unique))

    for candidate in unique:
        clarify(candidate)
        verified = verify(db, candidate)
        (report.kept if verified.status == "kept" else report.dropped).append(verified)
    assign_splits(report.kept)
    return report


# ------------------------------------------------------------------------- the output


def _flatten(sample: dict, prefix: str = "", depth: int = 2) -> list[tuple[str, object]]:
    """Field paths inside a document, nested ones included.

    Nested paths matter: a theatres document keeps its state three levels down, and a probe that
    cannot reach a real string value anywhere in the document is a probe that never runs.
    """
    found: list[tuple[str, object]] = []
    for name, value in sample.items():
        path = f"{prefix}{name}"
        if isinstance(value, dict) and depth > 0:
            found.extend(_flatten(value, f"{path}.", depth - 1))
        elif not isinstance(value, (dict, list)):
            found.append((path, value))
    return found


def _objectid_probe(collection: str, path: str) -> dict:
    """The sugar and canonical spellings of an object id, anchored on a real one."""
    return {
        "name": f"object id spelling in {collection}",
        "why": f"{collection}.{path} holds ObjectIds: the sandbox must accept both spellings alike",
        "anchor": {"collection": collection, "field": path, "as": "objectid"},
        "sugar": f'db.{collection}.find({{"{path}": ObjectId("{{{{value}}}}")}}, {{"{path}": 1}}).limit(2)',
        "canonical": f'db.{collection}.find({{"{path}": {{"$oid": "{{{{value}}}}"}}}}, {{"{path}": 1}}).limit(2)',
    }


def _date_probe(collection: str, path: str) -> dict:
    """The two spellings of a date, anchored on a date that is in the data."""
    return {
        "name": f"date spelling in {collection}",
        "why": f"{collection}.{path} holds dates: both spellings must select the same rows",
        "anchor": {"collection": collection, "field": path, "as": "date"},
        "sugar": f'db.{collection}.find({{"{path}": ISODate("{{{{value}}}}")}}, {{"{path}": 1}}).limit(2)',
        "canonical": f'db.{collection}.find({{"{path}": {{"$date": "{{{{value}}}}"}}}}, {{"{path}": 1}}).limit(2)',
    }


def _equality_probe(collection: str, path: str) -> dict:
    """A plain value against an explicit ``$eq``, anchored on a value that exists."""
    return {
        "name": f"equality in {collection}",
        "why": f"a plain value and an explicit $eq must select the same rows in {collection}",
        "anchor": {"collection": collection, "field": path, "as": "string"},
        "sugar": f'db.{collection}.find({{"{path}": "{{{{value}}}}"}}, {{"{path}": 1}}).limit(2)',
        "canonical": f'db.{collection}.find({{"{path}": {{"$eq": "{{{{value}}}}"}}}}, {{"{path}": 1}}).limit(2)',
    }


def audit_probes_for(db, collections: list[str]) -> list[dict]:
    """Declare instrument checks for a database, from what is actually in it.

    Nothing here is specific to any dataset: a collection holding an ObjectId gets the spelling
    probe, one holding a date gets the date probe, and one holding a string gets the equality probe.
    Every value a probe compares is read out of the database, so the probe checks the sandbox rather
    than a value typed in once and forgotten.
    """
    specs: list[dict] = []

    def already(kind: str) -> bool:
        return any(spec.get("anchor", {}).get("as") == kind for spec in specs)

    def already_equality(collection: str) -> bool:
        return any(spec.get("name") == f"equality in {collection}" for spec in specs)

    for collection in collections:
        try:
            sample = db[collection].find_one({})
        except Exception as exc:  # noqa: BLE001 - an unreadable collection is skipped, not fatal
            log.warning("cannot sample %s for audit probes: %s", collection, exc)
            continue
        if not sample:
            continue

        fields = _flatten(sample)
        if not already("objectid"):
            for path, value in fields:
                if isinstance(value, bson.ObjectId):
                    specs.append(_objectid_probe(collection, path))
                    break
        if not already("date"):
            for path, value in fields:
                if isinstance(value, datetime):
                    specs.append(_date_probe(collection, path))
                    break
        if not already_equality(collection) and not any(
            spec.get("name", "").startswith("equality in") for spec in specs
        ):
            for path, value in fields:
                if isinstance(value, str) and value:
                    specs.append(_equality_probe(collection, path))
                    break
    return specs


def to_pack(report: Report, name: str | None = None, audit_probes: list[dict] | None = None) -> datasets.Pack:
    """Turn a report into a dataset pack, ready for the harness to run on."""
    tasks = []
    for candidate in report.kept:
        tasks.append(
            {
                "id": candidate.id,
                "family": candidate.family,
                "split": getattr(candidate, "split", "train"),
                "collection": candidate.collection,
                "question": candidate.question,
                "reference": candidate.reference,
            }
        )
    collections = sorted({task["collection"] for task in tasks if task.get("collection")})
    return datasets.Pack(
        name=name or report.database,
        tasks=tasks,
        database=report.database,
        description=f"generated from {report.database} and verified against it",
        audit_probes=list(audit_probes or []),
    )


def write_pack(report: Report, path: str | Path, db=None) -> Path:
    """Write the verified questions out as a dataset pack, with an audit for its own data."""
    probes = audit_probes_for(db, to_pack(report).summary()["collections"]) if db is not None else []
    return datasets.write(to_pack(report, audit_probes=probes), path)