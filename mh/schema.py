"""Describe a database to the agent, from the data in front of it.

The film description this repository ships with is a good description of ``sample_mflix`` and a
wrong description of anything else. Pointed at another database, an agent told about movies answers
"there is no orders collection here" or invents a query over films, which is what happened the first
time the harness was run on somebody else's data. This derives the description from the data instead:
the collections in play, their fields, the types actually stored, and how often a field is absent.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import bson

log = logging.getLogger(__name__)

#: Documents read per collection when describing it. Enough to see the shape, cheap on any database.
SAMPLE_LIMIT = 200
#: Fields listed per collection, so a wide collection does not turn the prompt into a data dump.
MAX_FIELDS = 40
#: Example values are truncated to this many characters.
MAX_EXAMPLE = 40
#: How deep nested objects are followed, expressed as dotted paths.
MAX_DEPTH = 2


def _kind(value: Any) -> str:
    """Name the stored type in the words a model can act on."""
    if isinstance(value, bson.ObjectId):
        return "objectId"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, datetime):
        return "date"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__.lower()


def _walk(document: dict, prefix: str = "", depth: int = MAX_DEPTH) -> list[tuple[str, Any]]:
    """Field paths inside a document, nested objects followed to a fixed depth."""
    found: list[tuple[str, Any]] = []
    for name, value in document.items():
        path = f"{prefix}{name}"
        if isinstance(value, dict) and depth > 0:
            found.extend(_walk(value, f"{path}.", depth - 1))
        else:
            found.append((path, value))
    return found


def _example(value: Any) -> str:
    """A short, printable example of a value."""
    if isinstance(value, list):
        shown = ", ".join(_example(item) for item in value[:3])
        return f"[{shown}]"[:MAX_EXAMPLE]
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, bson.ObjectId):
        return f'ObjectId("{value}")'
    text = str(value)
    return text[:MAX_EXAMPLE] + ("…" if len(text) > MAX_EXAMPLE else "")


def _range_note(values: list[Any]) -> str:
    """A range for numbers, or a note that a value can be either a number or a string."""
    numbers = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    if len(numbers) != len(values):
        return "sometimes stored as a string"
    if not numbers:
        return ""
    low, high = min(numbers), max(numbers)
    return f"ranges {low}..{high}" if low != high else f"always {low}"


def describe_collection(db, collection: str, sample_limit: int = SAMPLE_LIMIT) -> list[str]:
    """Describe one collection: field, stored type, what it looks like, how often it is missing."""
    try:
        documents = list(db[collection].find({}).limit(sample_limit))
    except Exception as exc:  # noqa: BLE001 - a collection that cannot be read is described as such
        log.warning("cannot describe %s: %s", collection, exc)
        return [f"collection {collection} — could not be read: {exc}"]

    if not documents:
        return [f"collection {collection} — exists but is empty"]

    seen: dict[str, list[Any]] = {}
    order: list[str] = []
    for document in documents:
        for path, value in _walk(document):
            if path not in seen:
                seen[path] = []
                order.append(path)
            if value is not None:
                seen[path].append(value)

    total = len(documents)
    lines = [f"collection {collection} — one document per record, {total} document(s) examined"]
    for path in order[:MAX_FIELDS]:
        values = seen[path]
        if not values:
            continue
        kinds = sorted({_kind(value) for value in values})
        numeric = set(kinds) <= {"int", "double"}
        notes: list[str] = []
        if numeric:
            notes.append(_range_note(values))
        elif "string" in kinds and ({"int", "double"} & set(kinds)):
            # a mixed column is worth naming: an equality on the wrong type silently matches nothing
            notes.append(_range_note(values))
            notes.append(f"e.g. {_example(values[0])}")
        elif kinds == ["string"]:
            notes.append(f'e.g. "{_example(values[0])}"')
        else:
            notes.append(f"e.g. {_example(values[0])}")
        missing = total - len(values)
        if missing:
            notes.append(f"absent in {missing} of {total}")
        type_text = " or ".join(kinds)
        bullets = "; ".join(note for note in notes if note)
        lines.append(f"  {path:<26} {type_text:<16} {bullets}".rstrip())
    if len(order) > MAX_FIELDS:
        lines.append(f"  … and {len(order) - MAX_FIELDS} more field(s)")
    return lines


def describe(db, database: str, collections: list[str]) -> str:
    """The schema description handed to the agent, in the shape the shipped one uses.

    Nothing here is specific to any dataset: it is read out of the database the questions are asked
    against, so the agent's instructions are about the data it actually has.
    """
    header = [f"Database: {database}"]
    if collections:
        header.append(f"Collections in play: {', '.join(collections)}")
    else:
        try:
            collections = sorted(db.list_collection_names())
        except Exception:  # noqa: BLE001 - naming them is a convenience, not a requirement
            collections = []
        header.append(f"Collections available: {', '.join(collections)}")

    lines = list(header)
    for collection in collections:
        lines.append("")
        lines.extend(describe_collection(db, collection))
    return "\n".join(lines)
