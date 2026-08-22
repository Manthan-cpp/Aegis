from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.omnidim_client import OmniDimensionError, create_web_session


router = APIRouter(prefix="/voice", tags=["voice"])


class WebVoiceSessionRequest(BaseModel):
    user_name: str = Field(min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=240)
    situation: str | None = Field(default=None, max_length=1_200)
    instructions: str | None = Field(default=None, max_length=800)
    chat_summary: str | None = Field(default=None, max_length=2_000)


class CompanionVoiceSessionRequest(BaseModel):
    chat_summary: str | None = Field(default=None, max_length=4_000)
    language: str | None = Field(default=None, max_length=120)


class WebVoiceSessionResponse(BaseModel):
    ws_url: str
    session_id: int | str | None = None
    expires_at: str | None = None


def _clean(value: str | None) -> str:
    return (value or "").strip()


@router.post("/web-session", response_model=WebVoiceSessionResponse)
def start_web_voice_session(payload: WebVoiceSessionRequest):
    user_name = _clean(payload.user_name)
    if not user_name:
        raise HTTPException(status_code=422, detail="Please enter a name for the demo call.")

    custom_variables = {
        "user_name": user_name,
        "location": _clean(payload.location) or "Not provided",
        "situation": _clean(payload.situation) or "The user asked Aegis to contact a trusted person for help.",
        "instructions": _clean(payload.instructions) or "Explain only the facts provided, answer follow-up questions calmly, and do not invent information.",
        "chat_summary": _clean(payload.chat_summary) or "No previous chat summary was provided.",
    }

    try:
        return WebVoiceSessionResponse(**create_web_session(custom_variables))
    except OmniDimensionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/companion-session", response_model=WebVoiceSessionResponse)
def start_companion_voice_session(payload: CompanionVoiceSessionRequest):
    """Create a live, voice-to-voice session for the companion screen."""

    custom_variables = {
        "mode": "live companion conversation",
        "chat_summary": _clean(payload.chat_summary) or "No previous text chat context was provided.",
        "language": _clean(payload.language) or "Use the language the user is speaking. Support English and Hindi.",
    }

    try:
        return WebVoiceSessionResponse(
            **create_web_session(custom_variables, agent_env_name="OMNIDIM_COMPANION_AGENT_ID")
        )
    except OmniDimensionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
