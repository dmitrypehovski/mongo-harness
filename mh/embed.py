"""Text embeddings for the harness memory.

Uses a small local ONNX model through ``fastembed`` so the repository needs no
embedding API key and no quota. If the model cannot be loaded, a deterministic
hashing vectoriser keeps the loop running instead of crashing the demo.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from functools import lru_cache

log = logging.getLogger(__name__)

MODEL_NAME = os.environ.get("MH_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
DIM = int(os.environ.get("MH_EMBED_DIM", "384"))

_TOKEN = re.compile(r"[a-z0-9_]+")


@lru_cache(maxsize=1)
def _model():
    """Load the local embedding model once per process."""
    from fastembed import TextEmbedding

    log.info("loading embedding model %s", MODEL_NAME)
    return TextEmbedding(model_name=MODEL_NAME)


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts, returning one L2-normalised vector each."""
    texts = [t if isinstance(t, str) else str(t) for t in texts]
    if not texts:
        return []
    try:
        vectors = [list(map(float, vector)) for vector in _model().embed(texts)]
    except Exception as exc:  # model missing, no network on first download, onnxruntime missing
        log.warning("falling back to hashing embeddings: %s", exc)
        vectors = [_hash_vector(text) for text in texts]
    return [_normalise(vector) for vector in vectors]


def embed_one(text: str) -> list[float]:
    """Embed a single text."""
    return embed([text])[0]


def _hash_vector(text: str) -> list[float]:
    """Deterministic bag-of-words hashing vector, used only as a fallback."""
    vector = [0.0] * DIM
    for token in _TOKEN.findall(text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    return vector


def _normalise(vector: list[float]) -> list[float]:
    """Scale a vector to unit length so cosine similarity is a dot product."""
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    """Cosine similarity of two vectors of equal length."""
    if not left or not right or len(left) != len(right):
        return 0.0
    return float(sum(a * b for a, b in zip(left, right)))
