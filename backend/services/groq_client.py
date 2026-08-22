"""Groq wrappers for Aegis's SOS and support-message generation."""

from __future__ import annotations

import os
from dataclasses import dataclass

from groq import Groq


DEFAULT_MODEL = "openai/gpt-oss-120b"


@dataclass(frozen=True)
class ExpansionResult:
    message: str
    source: str
    warning: str | None = None


def _local_fallback(keywords: str) -> str:
    return (
        "I need help and may not be safe right now. "
        f"Please check in with me soon. Context: {keywords.strip()}"
    )


def _valid_message(message: str) -> str | None:
    cleaned = " ".join(message.replace("\n", " ").split()).strip()
    if not cleaned or len(cleaned) > 1_000:
        return None
    return cleaned


def expand_distress_message(keywords: str) -> ExpansionResult:
    """Expand keywords with Groq, falling back to a safe local sentence if needed."""

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return ExpansionResult(
            message=_local_fallback(keywords),
            source="local-fallback",
            warning="GROQ_API_KEY is not set, so Aegis used its local demo message.",
        )

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", DEFAULT_MODEL),
            temperature=0.2,
            max_tokens=120,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You help a person turn short distress keywords into one concise, "
                        "first-person message for a trusted contact. Preserve only the facts "
                        "in the keywords. Do not invent names, places, injuries, diagnoses, "
                        "legal advice, medical advice, or emergency claims. Do not mention AI. "
                        "Return only one or two calm, direct sentences."
                    ),
                },
                {"role": "user", "content": keywords.strip()},
            ],
        )
        generated_message = _valid_message(response.choices[0].message.content or "")
        if generated_message:
            return ExpansionResult(message=generated_message, source="groq")
    except Exception as error:  # noqa: BLE001 - the local fallback keeps the demo usable.
        return ExpansionResult(
            message=_local_fallback(keywords),
            source="local-fallback",
            warning=f"Groq was unavailable, so Aegis used its local demo message ({type(error).__name__}).",
        )

    return ExpansionResult(
        message=_local_fallback(keywords),
        source="local-fallback",
        warning="Groq returned an empty response, so Aegis used its local demo message.",
    )


def _local_session_summary(user_messages: list[str]) -> str:
    """Keep the clipboard feature usable if Groq is temporarily unavailable."""

    joined = " ".join(" ".join(message.split()) for message in user_messages if message.strip())
    summary = f"The user reported the following situation during the Aegis support conversation: {joined}"
    return summary[:1_150].rstrip()


def summarize_support_session(user_messages: list[str]) -> ExpansionResult:
    """Turn the user's chat messages into a factual handoff summary with Groq.

    This intentionally uses the same Groq client, model, temperature, and
    failure strategy as the SOS message expansion. The assistant's replies are
    not sent because the handoff should contain only facts the user stated.
    """

    cleaned_messages = [" ".join(message.split()) for message in user_messages if message.strip()]
    if not cleaned_messages:
        return ExpansionResult(
            message="",
            source="local-fallback",
            warning="There were no user messages to summarize.",
        )

    local_summary = _local_session_summary(cleaned_messages)
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return ExpansionResult(
            message=local_summary,
            source="local-fallback",
            warning="GROQ_API_KEY is not set, so Aegis used its local summary.",
        )

    conversation = "\n".join(
        f"User message {index}: {message}"
        for index, message in enumerate(cleaned_messages, start=1)
    )[:8_000]

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", DEFAULT_MODEL),
            temperature=0.2,
            max_tokens=220,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Turn the user's emotional-support chat into one clear, factual handoff "
                        "summary for a trusted person or support contact. Use only facts explicitly "
                        "stated in the user messages. Preserve important incidents, current danger, "
                        "injuries, location, monitoring, timing, and the help they are asking for "
                        "when those details are present. Do not invent names, places, diagnoses, "
                        "legal conclusions, medical advice, or emergency claims. Do not include the "
                        "assistant's advice and do not mention AI. Write in first person as the user, "
                        "in a direct, calm, human tone. Combine repeated details instead of quoting "
                        "every message. Keep it under 900 characters and return only the summary text."
                    ),
                },
                {"role": "user", "content": conversation},
            ],
        )
        generated_summary = _valid_message(response.choices[0].message.content or "")
        if generated_summary and len(generated_summary) <= 1_150:
            return ExpansionResult(message=generated_summary, source="groq")
    except Exception as error:  # noqa: BLE001 - the local fallback keeps handoff usable.
        return ExpansionResult(
            message=local_summary,
            source="local-fallback",
            warning=f"Groq was unavailable, so Aegis used its local summary ({type(error).__name__}).",
        )

    return ExpansionResult(
        message=local_summary,
        source="local-fallback",
        warning="Groq returned an empty or oversized summary, so Aegis used its local summary.",
    )
