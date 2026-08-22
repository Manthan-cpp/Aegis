"""Small, server-side Gemini adapter used by Aegis's two chatbots."""

from __future__ import annotations

import os

from google import genai
from google.genai import types


# Keep the primary model on a broadly available, stable Flash tier. The model
# chain below still respects a deliberate GEMINI_MODEL choice first, then moves
# through Gemini-only backups before the chatbot services fall back to Groq or
# Ollama.
DEFAULT_MODEL = "gemini-3.5-flash"
GEMINI_BACKUP_MODELS = (
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
)
DEFAULT_TIMEOUT_MS = 15_000


def gemini_api_key() -> str:
    """Return the configured key without ever logging or exposing it."""

    return os.getenv("GEMINI_API_KEY", "").strip()


def _thinking_config(model: str) -> types.ThinkingConfig | None:
    # Gemini 3 models support explicit thinking levels. Keeping the level minimal
    # gives Aegis a responsive chat experience while leaving room for the model's
    # normal reasoning. Older/latest aliases have different supported settings.
    if model.startswith("gemini-3."):
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
    return None


def generate_gemini_text(
    *,
    system_instruction: str,
    prompt: str,
    temperature: float,
    max_output_tokens: int,
) -> str:
    """Generate one text response, raising a safe error when Gemini is unavailable."""

    api_key = gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    configured_model = os.getenv("GEMINI_MODEL", "").strip()
    # Keep the configured model first, but make the backup sequence useful when
    # that model is rate-limited or temporarily unavailable. Deduplication keeps
    # us from spending a second request on the same exhausted model.
    models: list[str] = []
    for model in (configured_model, DEFAULT_MODEL, *GEMINI_BACKUP_MODELS):
        if model and model not in models:
            models.append(model)
    try:
        timeout_ms = int(os.getenv("GEMINI_TIMEOUT_MS", str(DEFAULT_TIMEOUT_MS)))
    except ValueError:
        timeout_ms = DEFAULT_TIMEOUT_MS

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=timeout_ms),
    )
    last_error: Exception | None = None
    for model in models:
        config_kwargs: dict[str, object] = {
            "system_instruction": system_instruction,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        thinking_config = _thinking_config(model)
        if thinking_config is not None:
            config_kwargs["thinking_config"] = thinking_config
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            text = (response.text or "").strip()
            if not text:
                raise RuntimeError("Gemini returned an empty response")
            return text
        except Exception as error:  # noqa: BLE001 - try the current fallback model only.
            last_error = error
    assert last_error is not None
    raise last_error
