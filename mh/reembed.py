"""Bring stored lesson embeddings in line with the model in use.

Switching ``MH_EMBED_MODEL`` changes nothing about what is already stored: old lessons keep the
width they were written with, and recall cannot compare across widths — it would silently score
them zero and look empty rather than broken. This module decides what has to be rewritten, and
rewrites it while recording which model produced each vector, so a mismatch stays visible instead
of being inferred from lengths.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from mh import embed, store

log = logging.getLogger(__name__)

#: How many lessons to keep as examples in a plan, so a report stays readable.
SAMPLE_LIMIT = 8


@dataclass
class Plan:
    """What the stored embeddings look like against the model in use."""

    model: str
    dim: int
    total: int = 0
    ok: int = 0
    missing: int = 0
    mismatched: int = 0
    unstamped: int = 0
    samples: list[dict] = field(default_factory=list)

    @property
    def needed(self) -> int:
        """How many lessons have to be rewritten."""
        return self.missing + self.mismatched + self.unstamped

    def summary(self) -> dict:
        """The plan as plain data, for printing and for the record."""
        return {
            "model": self.model,
            "dim": self.dim,
            "stored": self.total,
            "usable": self.ok,
            "missing": self.missing,
            "mismatched": self.mismatched,
            "unstamped": self.unstamped,
            "needed": self.needed,
        }


def plan(
    db: Optional[Any] = None,
    dataset_key: str | None = None,
    sample_limit: int = SAMPLE_LIMIT,
) -> Plan:
    """Read every lesson and say which ones the current model cannot compare.

    Nothing is written here: the point is to be able to look before deciding, and to be able to
    report honestly when there is nothing to do.
    """
    database = db if db is not None else store.get_db()
    query: dict = {}
    if dataset_key:
        query["dataset.key"] = dataset_key

    result = Plan(model=embed.MODEL_NAME, dim=embed.DIM)
    for doc in database["lessons"].find(query):
        result.total += 1
        stored = doc.get("embedding")
        written_by = doc.get("embedding_model")
        if not isinstance(stored, list) or not stored:
            result.missing += 1
            reason = "no embedding stored"
        elif len(stored) != embed.DIM:
            result.mismatched += 1
            reason = f"width {len(stored)} where the model produces {embed.DIM}"
        elif written_by != embed.MODEL_NAME:
            # equal widths are not equal models: two 384-number models live in different spaces, and
            # comparing across them returns confident nonsense instead of an error
            result.unstamped += 1
            reason = (
                f"embedded by {written_by}, not by {embed.MODEL_NAME}"
                if written_by
                else f"no model recorded, and recall needs to know it was {embed.MODEL_NAME}"
            )
        else:
            result.ok += 1
            continue
        if len(result.samples) < sample_limit:
            result.samples.append(
                {
                    "id": str(doc.get("_id")),
                    "task_id": doc.get("task_id"),
                    "question": str(doc.get("question") or doc.get("lesson") or "")[:70],
                    "reason": reason,
                    "model": doc.get("embedding_model"),
                }
            )
    return result


def apply(
    db: Optional[Any],
    lessons: list[dict],
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    batch: int = 32,
) -> int:
    """Re-embed the given lessons and record which model produced each vector.

    Returns the number of documents actually written. A lesson with no text to embed is skipped
    rather than written with an empty vector, which would look usable and match nothing.
    """
    if not lessons:
        return 0
    embed_text = embed_fn if embed_fn is not None else embed.embed
    database = db if db is not None else store.get_db()

    written = 0
    for start in range(0, len(lessons), max(1, batch)):
        chunk = lessons[start : start + max(1, batch)]
        texts: list[str] = []
        keep: list[dict] = []
        for doc in chunk:
            text = str(doc.get("question") or doc.get("lesson") or "").strip()
            if text:
                texts.append(text)
                keep.append(doc)
            else:
                log.warning("lesson %s has no text to embed; leaving it alone", doc.get("_id"))
        if not texts:
            continue
        vectors = embed_text(texts)
        for doc, vector in zip(keep, vectors):
            if len(vector) != embed.DIM:
                log.warning(
                    "the embedding model returned %d numbers where it is configured for %d; "
                    "not writing a vector of the wrong width",
                    len(vector),
                    embed.DIM,
                )
                continue
            database["lessons"].update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "embedding": [float(x) for x in vector],
                        "embedding_model": embed.MODEL_NAME,
                        "reembedded_at": store.utc_now(),
                    }
                },
            )
            written += 1
    return written


def reembed(
    db: Optional[Any] = None,
    dataset_key: str | None = None,
    dry_run: bool = False,
    batch: int = 32,
) -> tuple[Plan, Plan, int]:
    """Plan, rewrite what has to be rewritten, then plan again.

    Both plans are returned on purpose: the second one is read back out of the database, so the
    caller reports what is actually stored rather than what was sent.
    """
    database = db if db is not None else store.get_db()
    before = plan(database, dataset_key=dataset_key, sample_limit=1000)
    if dry_run or before.needed == 0:
        return before, before, 0

    query: dict = {}
    if dataset_key:
        query["dataset.key"] = dataset_key
    stale: list[dict] = []
    for doc in database["lessons"].find(query):
        stored = doc.get("embedding")
        stale_here = (
            not isinstance(stored, list)
            or not stored
            or len(stored) != embed.DIM
            or doc.get("embedding_model") != embed.MODEL_NAME
        )
        if stale_here:
            stale.append(doc)
    written = apply(database, stale, batch=batch)

    after = plan(database, dataset_key=dataset_key)
    return before, after, written
