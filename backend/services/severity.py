"""Conservative urgency classification for decoded SOS messages."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Literal

from groq import Groq


Severity = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class SeverityResult:
    level: Severity
    reason: str
    source: Literal["groq", "rule-based"]


HIGH_PATTERNS = (
    r"\b(?:kill myself|end my life|suicide|suicidal|self[- ]?harm)\b",
    r"\b(?:immediate danger|not safe right now|help now|need help now|trapped|locked in|cannot leave|can'?t leave)\b",
    r"\b(?:hitting|attacking|strangling|stabbing|shooting)\b",
    r"\b(?:weapon|knife|gun)\b",
)

MEDIUM_PATTERNS = (
    r"\b(?:abuse|abusive|threat|threatening|hurt|harass|assault|injur|scared|afraid)\w*\b",
    r"\b(?:monitoring me|being monitored|phone is checked|need help|please check in)\b",
)


def _rule_based_level(message: str) -> Severity:
    if any(re.search(pattern, message, flags=re.IGNORECASE) for pattern in HIGH_PATTERNS):
        return "high"
    if any(re.search(pattern, message, flags=re.IGNORECASE) for pattern in MEDIUM_PATTERNS):
        return "medium"
    return "low"


def _level_rank(level: Severity) -> int:
    return {"low": 0, "medium": 1, "high": 2}[level]


def classify_severity(message: str) -> SeverityResult:
    """Use Groq when available, but never allow it to downgrade rule-based danger."""

    rule_level = _rule_based_level(message)
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return SeverityResult(
            level=rule_level,
            reason=_reason_for(rule_level),
            source="rule-based",
        )

    try:
        response = Groq(api_key=api_key).chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=0,
            max_tokens=80,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify the urgency of an SOS message as exactly low, medium, or high. "
                        "high means explicit immediate danger, violence in progress, a weapon, or self-harm. "
                        "medium means threats, abuse, injury, monitoring, or a clear request for help without "
                        "explicit immediate danger. low means distress without those signals. "
                        "Return only JSON: {\"level\":\"low|medium|high\"}. Do not add facts."
                    ),
                },
                {"role": "user", "content": message.strip()},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        model_level = parsed.get("level")
        if model_level not in {"low", "medium", "high"}:
            raise ValueError("Groq returned an invalid severity level")
        final_level: Severity = model_level if _level_rank(model_level) >= _level_rank(rule_level) else rule_level
        return SeverityResult(level=final_level, reason=_reason_for(final_level), source="groq")
    except Exception:  # noqa: BLE001 - deterministic rules keep triage available.
        return SeverityResult(
            level=rule_level,
            reason=_reason_for(rule_level),
            source="rule-based",
        )


def _reason_for(level: Severity) -> str:
    return {
        "high": "The message contains language associated with immediate danger or urgent harm.",
        "medium": "The message contains distress, abuse, threat, monitoring, or a request for help without an explicit immediate-danger signal.",
        "low": "The message does not contain an explicit immediate-danger or threat signal.",
    }[level]
