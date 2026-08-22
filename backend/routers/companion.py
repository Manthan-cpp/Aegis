from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.companion_client import CompanionReply, SupportMode, classify_support_mode, generate_companion_reply
from services.groq_client import summarize_support_session
from services.mongo import clear_memory, load_recent_turns, save_turns


router = APIRouter(prefix="/companion", tags=["companion"])

URGENT_PATTERNS = (
    r"\b(?:kill myself|end my life|suicide|suicidal|self[- ]?harm)\b",
    r"\b(?:kidnapped|kidnap(?:ping|ped)?|abducted|abduction|held against my will|taken by force)\b",
    r"\b(?:he|she|they) (?:is|are) (?:hitting|hurting|attacking|strangling|threatening) me\b",
    r"\b(?:sexual assault|sexual abuse|sexually assaulted|sexually abused|rape|raped|forced sex|forced intercourse)\b",
    r"\b(?:weapon|knife|gun)\b",
    r"\b(?:immediate danger|not safe right now|trapped|cannot leave|can'?t leave)\b",
)

ABUSE_PATTERNS = (
    r"\b(?:my\s+)?(?:family|parents|partner|husband|wife|brother|sister|relative|in[- ]laws?)\b.*\b(?:abusive|abusing|hurting|hitting|threatening|controlling)\b",
    r"\b(?:family|parents|partner|husband|wife)\b.*\b(?:abuse|control|hurt|threaten)\w*\b",
)

MONITORING_PATTERNS = (
    r"\b(?:being monitored|monitored strictly|monitoring me|watching my phone|phone is checked|phone gets checked|tracking my phone|tracking me)\b",
    r"\b(?:cannot|can not|can't) reach anyone\b",
)

URGENT_SUPPORT = (
    "Your safety matters. If you are in immediate danger in India, call 112 only "
    "if you can do so without increasing the danger. You do not need to make a "
    "detectable move or respond to anyone who may be monitoring you."
)


def has_urgent_language(message: str) -> bool:
    return any(re.search(pattern, message, flags=re.IGNORECASE) for pattern in URGENT_PATTERNS)


def has_abuse_language(message: str) -> bool:
    return any(re.search(pattern, message, flags=re.IGNORECASE | re.DOTALL) for pattern in ABUSE_PATTERNS)


def has_monitoring_language(message: str) -> bool:
    return any(re.search(pattern, message, flags=re.IGNORECASE) for pattern in MONITORING_PATTERNS)


class ContextTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1_000)


class CompanionChatRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=1_600)
    memory_consent: bool = False
    # Recent turns keep one open chat coherent without saving them to the backend.
    context_turns: list[ContextTurn] = Field(default_factory=list, max_length=8)


class CompanionChatResponse(BaseModel):
    reply: str
    reply_source: Literal["gemini", "groq", "ollama", "local-fallback", "safety-guided", "context-guided"]
    urgent_support: bool
    urgent_support_message: str | None = None
    memory_saved: bool
    memory_store: Literal["mongo", "local-demo", "not-saved"]
    warning: str | None = None


class CompanionSummaryRequest(BaseModel):
    user_messages: list[str] = Field(min_length=1, max_length=40)


class CompanionSummaryResponse(BaseModel):
    summary: str
    source: Literal["groq", "local-fallback"]
    warning: str | None = None


class ClearMemoryResponse(BaseModel):
    cleared: bool
    memory_store: Literal["mongo", "local-demo"]


@router.post("/chat", response_model=CompanionChatResponse)
def chat_with_companion(payload: CompanionChatRequest):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Please write a message before sending it.")

    stored_history, _ = load_recent_turns(payload.session_id) if payload.memory_consent else ([], "local-demo")
    recent_context = [turn.model_dump() for turn in payload.context_turns]
    # Saved memory is preferred when enabled. Otherwise, the browser supplies only
    # the current in-memory conversation; it is never persisted here.
    history = stored_history or recent_context
    support_mode: SupportMode = classify_support_mode(message, history)
    # Keep the urgent support panel available during a follow-up turn when the
    # immediate-danger signal is still present in the recent conversation.
    urgent = support_mode == "urgent"
    generated_reply: CompanionReply = generate_companion_reply(message, history, support_mode)

    if payload.memory_consent:
        memory_store = save_turns(
            payload.session_id,
            [
                {"role": "user", "content": message},
                {"role": "assistant", "content": generated_reply.text},
            ],
        )
        memory_saved = True
    else:
        memory_store = "not-saved"
        memory_saved = False

    return CompanionChatResponse(
        reply=generated_reply.text,
        reply_source=generated_reply.source,
        urgent_support=urgent,
        urgent_support_message=URGENT_SUPPORT if urgent else None,
        memory_saved=memory_saved,
        memory_store=memory_store,
        warning=generated_reply.warning,
    )


@router.post("/summary", response_model=CompanionSummaryResponse)
def summarize_companion_session(payload: CompanionSummaryRequest):
    user_messages = [message.strip() for message in payload.user_messages if message.strip()]
    if not user_messages:
        raise HTTPException(status_code=422, detail="Share something about your situation before creating a summary.")
    if sum(len(message) for message in user_messages) > 8_000:
        raise HTTPException(status_code=422, detail="That conversation is too long to summarize at once.")

    summary = summarize_support_session(user_messages)
    if not summary.message:
        raise HTTPException(status_code=502, detail="Aegis could not create a session summary.")
    return CompanionSummaryResponse(
        summary=summary.message,
        source=summary.source,
        warning=summary.warning,
    )


@router.delete("/sessions/{session_id}", response_model=ClearMemoryResponse)
def delete_companion_memory(session_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", session_id):
        raise HTTPException(status_code=422, detail="That companion session is not valid.")

    return ClearMemoryResponse(cleared=True, memory_store=clear_memory(session_id))
