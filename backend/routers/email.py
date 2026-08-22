from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from services.email_queue import enqueue_email_job, get_email_job
from services.emailjs_client import EmailJSError, email_recipient_metadata, validate_email_recipient


router = APIRouter(prefix="/email", tags=["email"])


class EmailAlertRequest(BaseModel):
    recipient_type: Literal["trusted", "women_support"]
    client_request_id: str | None = Field(default=None, min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    trusted_email: str | None = Field(default=None, max_length=254)
    user_name: str = Field(min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=240)
    situation: str | None = Field(default=None, max_length=2_000)
    instructions: str | None = Field(default=None, max_length=800)
    chat_summary: str | None = Field(default=None, max_length=4_000)
    confirmation: bool = False


class EmailAlertResponse(BaseModel):
    queued: bool
    sent: bool
    job_id: str
    status: Literal["queued", "sending", "sent"]
    recipient_type: Literal["trusted", "women_support"]
    recipient_label: str
    demo_mode: bool


class EmailQueueStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "sending", "sent"]
    sent: bool
    attempts: int
    queued_at: str
    updated_at: str
    sent_at: str | None = None
    recipient_type: Literal["trusted", "women_support"] | None = None
    recipient_label: str | None = None
    demo_mode: bool = False
    last_error: str | None = None


def _clean(value: str | None) -> str:
    return (value or "").strip()


@router.post("/send", response_model=EmailAlertResponse, status_code=status.HTTP_202_ACCEPTED)
def send_help_email(payload: EmailAlertRequest):
    if not payload.confirmation:
        raise HTTPException(status_code=422, detail="Please confirm that you want to send this email.")
    if not _clean(payload.user_name):
        raise HTTPException(status_code=422, detail="Please enter your name.")
    if not _clean(payload.situation) and not _clean(payload.chat_summary):
        raise HTTPException(status_code=422, detail="Add a situation message or chat summary before sending.")

    try:
        validate_email_recipient(payload.recipient_type, payload.trusted_email)
        metadata = email_recipient_metadata(payload.recipient_type, payload.trusted_email)
    except EmailJSError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    job = enqueue_email_job(
        {
            "recipient_type": payload.recipient_type,
            "trusted_email": payload.trusted_email,
            "user_name": payload.user_name,
            "location": payload.location,
            "situation": payload.situation,
            "instructions": payload.instructions,
            "chat_summary": payload.chat_summary,
        },
        client_request_id=payload.client_request_id,
    )
    return EmailAlertResponse(
        queued=job["status"] != "sent",
        sent=job["status"] == "sent",
        job_id=job["job_id"],
        status=job["status"],
        **metadata,
    )


@router.get("/queue/{job_id}", response_model=EmailQueueStatusResponse)
def email_queue_status(job_id: str):
    if not job_id or len(job_id) > 100:
        raise HTTPException(status_code=422, detail="That email queue id is not valid.")
    job = get_email_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="That queued email was not found.")

    return EmailQueueStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        sent=job["status"] == "sent",
        attempts=job["attempts"],
        queued_at=job["queued_at"],
        updated_at=job["updated_at"],
        sent_at=job.get("sent_at"),
        last_error=job.get("last_error"),
        recipient_type=job.get("recipient_type"),
        recipient_label=job.get("recipient_label"),
        demo_mode=job.get("demo_mode", False),
    )
