"""Thin OpenRouter chat client used by the harness.

The key is never stored in the repository: it comes from ``OPENROUTER_API_KEY`` or,
as a convenience for local runs, from the file named by ``OPENROUTER_KEY_FILE``.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("MH_MODEL_DEFAULT", "z-ai/glm-5.3-flash")
DEFAULT_KEY_FILE = os.path.expanduser("~/.secrets/openrouter_dmitry.key")


def api_key() -> str:
    """Return the OpenRouter API key from the environment or the key file."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    path = os.environ.get("OPENROUTER_KEY_FILE", DEFAULT_KEY_FILE)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            key = handle.read().strip()
    except OSError as exc:
        raise RuntimeError(f"no OpenRouter key: set OPENROUTER_API_KEY or OPENROUTER_KEY_FILE ({exc})")
    if not key:
        raise RuntimeError("OpenRouter key file is empty")
    return key


def default_model() -> str:
    """Model id used unless a caller overrides it."""
    return os.environ.get("MH_MODEL", DEFAULT_MODEL)


class ModelError(RuntimeError):
    """Raised when the model could not be reached after every retry."""


def chat_raw(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1500,
    retries: int = 3,
    timeout: int = 120,
) -> dict:
    """Send a chat completion request and return the assistant message as it arrived.

    Retries on transport errors, rate limits and server errors with exponential
    backoff. Raises :class:`ModelError` when every attempt fails.
    """
    payload = {
        "model": model or default_model(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    body = json.dumps(payload).encode("utf-8")
    last_error = "unknown"
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(
            API_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key()}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/mongo-harness",
                "X-Title": "the harness that earns its edits",
            },
            method="POST",
        )
        started = time.time()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            log.debug("chat ok in %.1fs", time.time() - started)
            choices = data.get("choices") or []
            if not choices:
                last_error = f"no choices in response: {str(data)[:200]}"
                continue
            return choices[0].get("message", {})
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            last_error = f"HTTP {exc.code}: {detail}"
            if exc.code in (400, 401, 402, 403, 404):
                break
        except Exception as exc:  # transport, timeout, malformed body
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(min(2 ** attempt, 12))
    raise ModelError(f"model {model or default_model()} failed after {retries} attempts: {last_error}")


def message_text(message: dict) -> str:
    """The assistant's answer, from the content channel or, failing that, the reasoning one.

    Some reasoning models return an empty content field when they spend their output budget
    thinking, while still having written the answer inside the reasoning channel. Reading it
    back is the difference between a usable answer and a wasted call.
    """
    content = (message.get("content") or "").strip()
    if content:
        return content
    reasoning = (message.get("reasoning") or "").strip()
    if reasoning:
        log.warning("the model returned no content; reading the reasoning channel instead")
        return reasoning
    return ""


def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1500,
    retries: int = 3,
    timeout: int = 120,
) -> str:
    """Send a chat completion request and return the assistant text."""
    message = chat_raw(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
        timeout=timeout,
    )
    return message_text(message)
