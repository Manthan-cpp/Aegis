"""Optional local Ollama adapter used only after online providers fail."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama3.2:1b"
DEFAULT_TIMEOUT_SECONDS = 12.0


def ollama_enabled() -> bool:
    """Return whether the local provider is allowed as a fallback."""

    return os.getenv("OLLAMA_ENABLED", "true").strip().casefold() in {"1", "true", "yes", "on"}


def ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/") or DEFAULT_BASE_URL


def _timeout_seconds() -> float:
    try:
        return max(1.0, float(os.getenv("OLLAMA_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def generate_ollama_text(
    *,
    system_instruction: str,
    prompt: str,
    temperature: float,
    max_output_tokens: int,
) -> str:
    """Generate text from the local Ollama chat endpoint."""

    if not ollama_enabled():
        raise RuntimeError("OLLAMA_ENABLED is disabled")

    payload = {
        "model": ollama_model(),
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_output_tokens,
        },
    }
    request = Request(
        f"{_base_url()}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=_timeout_seconds()) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Ollama is unavailable") from error

    text = str(body.get("message", {}).get("content", "")).strip()
    if not text:
        raise RuntimeError("Ollama returned an empty response")
    return text
