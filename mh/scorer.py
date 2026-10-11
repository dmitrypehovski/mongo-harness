"""Parse, sandbox and score generated MQL.

Scoring compares *results*, not query text: many different queries are correct,
so a task passes when the rows it returns match the rows the reference query
returns. Order matters only when the reference query sorts.

The parser is deliberately strict and acts as an envelope: only the read-only
methods listed in the harness config may be used, and code-execution or
write stages are refused before anything touches the database.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from bson import json_util
from pymongo import MongoClient

log = logging.getLogger(__name__)

MAX_ROWS = int(os.environ.get("MH_MAX_ROWS", "500"))
MAX_TIME_MS = int(os.environ.get("MH_MAX_TIME_MS", "20000"))
ROW_CHARS = 8000

CHAIN_METHODS = {"sort", "limit", "skip", "project", "count"}
INT_ARG_METHODS = {"limit", "skip", "count"}
READ_METHODS = {"find", "aggregate", "countDocuments"}

BLOCKED_OPERATORS = {
    "$where",
    "$function",
    "$accumulator",
    "$out",
    "$merge",
    "$unionWith",
}

_JS_CALLS = (
    (re.compile(r'ObjectId\(\s*"([^"]*)"\s*\)'), r'{"$oid": "\1"}'),
    (re.compile(r'ObjectId\(\s*\'([^\']*)\'\s*\)'), r'{"$oid": "\1"}'),
    (re.compile(r'ISODate\(\s*"([^"]*)"\s*\)'), r'{"$date": "\1"}'),
    (re.compile(r'new Date\(\s*"([^"]*)"\s*\)'), r'{"$date": "\1"}'),
)


class ParseError(ValueError):
    """Raised when the model output is not a readable read-only MQL statement."""


@dataclass
class Mql:
    """A parsed MQL statement."""

    collection: str
    method: str
    args: list[Any] = field(default_factory=list)
    chain: list[tuple[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict:
        """JSON-friendly view, used when recording steps."""
        return {
            "collection": self.collection,
            "method": self.method,
            "args": _jsonable(self.args),
            "chain": [[name, _jsonable(value)] for name, value in self.chain],
        }

    def canonical(self) -> str:
        """Stable string form of the statement."""
        return json.dumps(self.as_dict(), sort_keys=True, default=str)


@dataclass
class Execution:
    """Outcome of running an MQL statement."""

    ok: bool
    rows: list[Any] = field(default_factory=list)
    digest: str = ""
    latency_ms: int = 0
    error: str = ""
    status: str = "ok"  # ok | invalid_query | tool_denied | blocked | exception


def _jsonable(value: Any) -> Any:
    """Best-effort conversion to plain JSON for storage."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _strip_fences(text: str) -> str:
    """Remove markdown fences and surrounding prose from model output."""
    if not text:
        return ""
    cleaned = text.strip()
    fence = re.search(r"```(?:json|javascript|js|mql)?\s*(.+?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("db.")
    if start == -1:
        raise ParseError("no 'db.' statement found in the output")
    return cleaned[start:]


def _match_paren(text: str, open_index: int) -> int:
    """Return the index of the ')' matching the '(' at ``open_index``."""
    depth = 0
    quote = ""
    escaped = False
    for index in range(open_index, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    raise ParseError("unbalanced parentheses in the statement")


def _split_args(text: str) -> list[str]:
    """Split an argument list on top-level commas."""
    parts: list[str] = []
    depth = 0
    quote = ""
    escaped = False
    current = ""
    for char in text:
        if escaped:
            current += char
            escaped = False
            continue
        if char == "\\":
            current += char
            escaped = True
            continue
        if quote:
            current += char
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
            current += char
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        parts.append(current.strip())
    return [part for part in parts if part]


def _js_to_json(text: str) -> str:
    """Rewrite JavaScript object syntax into JSON.

    Models write executable MQL, so they leave keys unquoted, use single quotes
    and add trailing commas. All three are converted here instead of being treated
    as a generation failure, because the query itself may be perfectly correct.
    """
    out: list[str] = []
    index = 0
    length = len(text)
    quote = ""
    while index < length:
        char = text[index]
        if quote:
            if char == "\\" and index + 1 < length:
                out.append(char)
                out.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                out.append('"' if quote == "'" else char)
                quote = ""
            elif char == '"':
                out.append('\\"')
            else:
                out.append(char)
            index += 1
            continue
        if char in "\"'":
            quote = char
            out.append('"')
            index += 1
            continue
        out.append(char)
        index += 1

    joined = "".join(out)
    # quote bare keys: { title: ... } and [, $match: ... ]
    joined = re.sub(r'([{,]\s*)([A-Za-z_$][A-Za-z0-9_$.]*)(\s*:)', r'\1"\2"\3', joined)
    joined = joined.rstrip()
    # drop trailing commas before a closing bracket
    joined = re.sub(r",(\s*[\]}])", r"\1", joined)
    # values that JSON does not have
    joined = re.sub(r"\bundefined\b", "null", joined)
    joined = re.sub(r"\bNaN\b", "null", joined)
    return joined


def _load_value(text: str) -> Any:
    """Parse one argument value, accepting Extended JSON and JavaScript syntax."""
    stripped = text.strip()
    for pattern, replacement in _JS_CALLS:
        stripped = pattern.sub(replacement, stripped)
    attempts = (stripped, _js_to_json(stripped))
    errors = []
    for attempt in attempts:
        for loader in (json_util.loads, json.loads):
            try:
                return loader(attempt)
            except Exception as exc:  # try the next combination
                errors.append(str(exc))
    raise ParseError(f"cannot parse argument {text[:120]!r}: {errors[0][:120]}")


def parse_mql(text: str) -> Mql:
    """Parse a read-only MQL statement, rejecting anything unexpected."""
    statement = _strip_fences(text)
    head = re.match(r"db\.([A-Za-z0-9_\-]+)\.([A-Za-z]+)\s*\(", statement)
    if not head:
        raise ParseError("the statement does not start with db.<collection>.<method>(")
    collection, method = head.group(1), head.group(2)
    if method not in READ_METHODS:
        raise ParseError(f"method {method!r} is not a read method")
    open_index = statement.index("(", head.end() - 1)
    close_index = _match_paren(statement, open_index)
    args_text = statement[open_index + 1:close_index]
    args = [_load_value(part) for part in _split_args(args_text)]

    chain: list[tuple[str, Any]] = []
    cursor = close_index + 1
    while True:
        tail = statement[cursor:].lstrip()
        if not tail.startswith("."):
            break
        step = re.match(r"\.\s*([A-Za-z]+)\s*\(", tail)
        if not step:
            break
        name = step.group(1)
        if name not in CHAIN_METHODS:
            raise ParseError(f"chained method {name!r} is not allowed")
        step_open = cursor + (len(statement[cursor:]) - len(tail)) + tail.index("(", step.end() - 1)
        step_close = _match_paren(statement, step_open)
        raw = statement[step_open + 1:step_close]
        if name in INT_ARG_METHODS:
            try:
                value: Any = int(str(_load_value(raw)))
            except Exception as exc:
                raise ParseError(f"{name}(...) needs an integer") from exc
        else:
            value = _load_value(raw)
        chain.append((name, value))
        cursor = step_close + 1
    return Mql(collection=collection, method=method, args=args, chain=chain)


def find_blocked(node: Any) -> str:
    """Return the first blocked operator found in a parsed statement, if any."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in BLOCKED_OPERATORS:
                return key
            found = find_blocked(value)
            if found:
                return found
    elif isinstance(node, (list, tuple)):
        for item in node:
            found = find_blocked(item)
            if found:
                return found
    return ""


def row_digest(row: Any, drop_id: bool = False) -> str:
    """Canonical, stable digest of one result row.

    For questions that ask for documents, a top-level ``_id`` is dropped: a
    question about titles must not fail because the answer did or did not include
    the identifier. For grouped answers the identifier *is* the group key, so it is
    kept.
    """
    if isinstance(row, dict) and drop_id and "_id" in row:
        row = {key: value for key, value in row.items() if key != "_id"}
    return json_util.dumps(row, sort_keys=True)[:ROW_CHARS]


def digest_rows(rows: list[Any], order_sensitive: bool = False, drop_id: bool = False) -> str:
    """Digest a result set, honouring order only when the query sorted."""
    digests = [row_digest(row, drop_id=drop_id) for row in rows]
    if not order_sensitive:
        digests = sorted(digests)
    payload = "\n".join(digests)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _value_row(row: Any, drop_id: bool) -> tuple[str, ...]:
    """A row reduced to its values, so that field naming does not decide the score."""
    if isinstance(row, dict):
        values = [value for key, value in row.items() if not (drop_id and key == "_id")]
        return tuple(sorted(json_util.dumps(value)[:ROW_CHARS] for value in values))
    return (json_util.dumps(row)[:ROW_CHARS],)


def _shape(row: Any, drop_id: bool) -> int:
    """How many values a row carries."""
    if isinstance(row, dict):
        return len(row) - (1 if drop_id and "_id" in row else 0)
    return 1


def compare(
    expected_rows: list[Any],
    got_rows: list[Any],
    order_sensitive: bool = False,
    drop_id: bool = False,
) -> tuple[bool, str]:
    """Compare two result sets and say how they matched.

    Two ways to match:

    * ``digest`` — the rows are identical, including field names;
    * ``values`` — the rows carry the same values and the same number of values per
      row, but name them differently. An answer that says ``count`` where the
      reference says ``movies`` is the same answer, and is accepted; an answer that
      returns extra fields or the wrong number of rows is not.
    """
    if digest_rows(expected_rows, order_sensitive, drop_id) == digest_rows(got_rows, order_sensitive, drop_id):
        return True, "digest"

    if len(expected_rows) == len(got_rows) and expected_rows:
        expected_shapes = sorted(_shape(row, drop_id) for row in expected_rows)
        got_shapes = sorted(_shape(row, drop_id) for row in got_rows)
        if expected_shapes == got_shapes:
            expected_values = [_value_row(row, drop_id) for row in expected_rows]
            got_values = [_value_row(row, drop_id) for row in got_rows]
            if order_sensitive:
                if expected_values == got_values:
                    return True, "values"
            elif sorted(expected_values) == sorted(got_values):
                return True, "values"

    return False, "mismatch"


def connect(uri: str | None = None) -> MongoClient:
    """Open a MongoDB client from an explicit URI or the environment."""
    target = uri or os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    return MongoClient(target, serverSelectionTimeoutMS=15000, appname="mongo-harness")


def execute(db, mql: Mql, allowed_tools: list[str] | None = None) -> Execution:
    """Run a parsed statement under the harness envelope."""
    tools = list(allowed_tools or ["find", "aggregate", "count"])
    if mql.method == "countDocuments" and "count" in tools:
        pass
    elif mql.method not in tools:
        return Execution(ok=False, status="tool_denied", error=f"tool {mql.method!r} is not enabled")

    blocked = find_blocked({"args": mql.args, "chain": [value for _, value in mql.chain]})
    if blocked:
        return Execution(ok=False, status="blocked", error=f"operator {blocked} is refused")

    started = time.time()
    try:
        rows = _run(db, mql)
    except Exception as exc:
        return Execution(
            ok=False,
            status="exception",
            error=f"{type(exc).__name__}: {exc}"[:400],
            latency_ms=int((time.time() - started) * 1000),
        )
    latency = int((time.time() - started) * 1000)
    order_sensitive = any(name == "sort" for name, _ in mql.chain) or _sorts(mql)
    return Execution(
        ok=True,
        rows=rows,
        digest=digest_rows(rows, order_sensitive=order_sensitive),
        latency_ms=latency,
    )


def _sorts(mql: Mql) -> bool:
    """True when an aggregation pipeline sorts, so row order is meaningful."""
    if mql.method != "aggregate" or not mql.args:
        return False
    pipeline = mql.args[0] if isinstance(mql.args[0], list) else []
    return any(isinstance(stage, dict) and "$sort" in stage for stage in pipeline)


def _run(db, mql: Mql) -> list[Any]:
    """Execute the statement and materialise at most ``MAX_ROWS`` rows.

    Every query carries a server-side time limit so a pathological generated
    statement fails fast instead of hanging the whole run.
    """
    collection = db[mql.collection]
    if mql.method == "find":
        filter_doc = mql.args[0] if mql.args else {}
        projection = mql.args[1] if len(mql.args) > 1 else None
        cursor = collection.find(filter_doc, projection).max_time_ms(MAX_TIME_MS)
        requested: int | None = None
        for name, value in mql.chain:
            if name == "sort":
                cursor = cursor.sort(list(value.items()) if isinstance(value, dict) else value)
            elif name == "limit":
                requested = int(value)
            elif name == "skip":
                cursor = cursor.skip(value)
        cursor = cursor.limit(min(requested, MAX_ROWS) if requested else MAX_ROWS)
        return [row for row in cursor]

    if mql.method == "countDocuments":
        return [
            {
                "count": int(
                    collection.count_documents(mql.args[0] if mql.args else {}, maxTimeMS=MAX_TIME_MS)
                )
            }
        ]

    pipeline = mql.args[0] if mql.args else []
    if not isinstance(pipeline, list):
        raise ValueError("aggregate needs a pipeline array")
    rows: list[Any] = []
    for row in collection.aggregate(pipeline, allowDiskUse=True, maxTimeMS=MAX_TIME_MS):
        rows.append(row)
        if len(rows) >= MAX_ROWS:
            break
    return rows
