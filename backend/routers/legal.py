from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.legal_client import LegalAnswer, generate_legal_answer
from services.legal_search import search_legal_chunks


router = APIRouter(prefix="/legal", tags=["legal"])

VAGUE_FOLLOW_UPS = (
    "i don't get it", "i dont get it", "i do not get it", "i don't understand",
    "i dont understand", "what does that mean", "explain that", "please explain",
    "samajh nahi", "samajh nahi aaya", "mujhe samajh nahi",
)


class LegalContextTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1_500)


class LegalAskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1_200)
    context_turns: list[LegalContextTurn] = Field(default_factory=list, max_length=8)


class LegalCitation(BaseModel):
    title: str
    section: str
    source: str
    source_url: str
    relevance: float
    status: str


class LegalAskResponse(BaseModel):
    answer: str
    answer_source: str
    in_scope: bool
    citations: list[LegalCitation]
    retrieval_source: Literal["atlas-vector", "local-cosine", "local-corpus", "not-configured"]
    warning: str | None = None


def _is_vague_follow_up(question: str) -> bool:
    lowered = question.casefold().strip()
    return any(phrase in lowered for phrase in VAGUE_FOLLOW_UPS)


def _latest_substantive_user_question(context_turns: list[dict[str, str]]) -> str:
    for turn in reversed(context_turns):
        if turn.get("role") != "user":
            continue
        candidate = turn.get("content", "").strip()
        if candidate and not _is_vague_follow_up(candidate):
            return candidate
    return ""


@router.post("/ask", response_model=LegalAskResponse)
def ask_legal_question(payload: LegalAskRequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Please write a legal question first.")

    context_turns = [turn.model_dump() for turn in payload.context_turns]
    user_context = " ".join(turn["content"] for turn in context_turns if turn["role"] == "user")
    # Retrieval should answer the latest substantive question. Only attach an
    # earlier user turn when the new message is genuinely elliptical; otherwise
    # a long conversation about abuse can drown out a later self-defence or
    # evidence question.
    lowered_question = question.casefold()
    follow_up = len(question.split()) <= 8 or lowered_question.startswith(
        ("what about", "and what", "does that", "would that", "can that", "how about", "then what", "what then")
    )
    prior_question = _latest_substantive_user_question(context_turns)
    search_query = f"{prior_question} {question}".strip() if prior_question and follow_up else question
    chunks, retrieval_source = search_legal_chunks(search_query)
    answer: LegalAnswer = generate_legal_answer(question, chunks, retrieval_source, context_turns)
    citations = [
        LegalCitation(
            title=chunk.title,
            section=chunk.section,
            source=chunk.source,
            source_url=chunk.source_url,
            relevance=round(chunk.score, 4),
            status=chunk.status,
        )
        for chunk in answer.citations
    ]
    return LegalAskResponse(
        answer=answer.text,
        answer_source=answer.source,
        in_scope=bool(answer.citations),
        citations=citations,
        retrieval_source=retrieval_source,
        warning=answer.warning,
    )
