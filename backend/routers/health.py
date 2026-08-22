from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.health_client import HealthReply, generate_health_reply


router = APIRouter(prefix="/health", tags=["health"])


class HealthContextTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1_200)


class HealthChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)
    context_turns: list[HealthContextTurn] = Field(default_factory=list, max_length=8)


class HealthChatResponse(BaseModel):
    reply: str
    reply_source: Literal["gemini", "groq", "ollama", "context-guided"]
    warning: str | None = None


@router.post("/chat", response_model=HealthChatResponse)
def chat_with_health_assistant(payload: HealthChatRequest):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Please write a health question before sending it.")

    try:
        reply: HealthReply = generate_health_reply(
            message,
            [turn.model_dump() for turn in payload.context_turns],
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail="The health assistant is temporarily unavailable. Check that the backend is running and that an online provider or Ollama is available.",
        ) from error

    return HealthChatResponse(
        reply=reply.text,
        reply_source=reply.source,
        warning=reply.warning,
    )
