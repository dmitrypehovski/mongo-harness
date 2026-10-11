"""Environment configuration for mongo-harness.

Loads `.env` via python-dotenv once on first access. No network I/O.
Secrets stay in the environment; this module never logs URI credentials.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

_DOTENV_LOADED = False


def _ensure_dotenv() -> None:
    """Load `.env` into the process environment at most once."""
    global _DOTENV_LOADED
    if not _DOTENV_LOADED:
        load_dotenv()
        _DOTENV_LOADED = True


@lru_cache(maxsize=1)
def mongodb_uri() -> str:
    """Return `MONGODB_URI` or raise if unset."""
    _ensure_dotenv()
    uri = os.environ.get("MONGODB_URI", "").strip()
    if not uri:
        raise RuntimeError("MONGODB_URI is required (set it in .env or the environment)")
    return uri


def db_name() -> str:
    """Return database name from `MH_DB`, defaulting to ``harness``."""
    _ensure_dotenv()
    return os.environ.get("MH_DB", "harness").strip() or "harness"


def use_vector() -> bool:
    """Return whether Atlas `$vectorSearch` should be attempted (`MH_USE_VECTOR`)."""
    _ensure_dotenv()
    raw = os.environ.get("MH_USE_VECTOR", "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def uri_kind(uri: str | None = None) -> str:
    """Classify a MongoDB URI as ``atlas`` or ``local``.

    Atlas is detected via ``mongodb+srv://`` or a ``mongodb.net`` host.
    """
    value = (uri if uri is not None else mongodb_uri()).lower()
    if value.startswith("mongodb+srv://") or "mongodb.net" in value:
        return "atlas"
    return "local"
