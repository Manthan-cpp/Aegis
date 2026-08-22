from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from services.cases import CaseRecord, CaseStorage, delete_case, list_cases, save_case
from services.severity import Severity, SeverityResult, classify_severity
from services.steganography import SteganographyError, decode_message


router = APIRouter(prefix="/responder", tags=["responder"])


class ResponderDecodeResponse(BaseModel):
    message: str
    filename: str | None = None
    severity: Severity
    severity_reason: str
    classification_source: Literal["groq", "rule-based"]


class CaseSubmitRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8_192)
    severity: Severity
    severity_reason: str = Field(min_length=1, max_length=400)
    filename: str | None = Field(default=None, max_length=255)
    classification_source: Literal["groq", "rule-based"] = "rule-based"


class CaseResponse(BaseModel):
    case_id: str
    message: str
    severity: Severity
    severity_reason: str
    filename: str | None
    created_at: datetime
    classification_source: Literal["groq", "rule-based"]


class CaseSubmitResponse(BaseModel):
    case: CaseResponse
    memory_store: CaseStorage


class CaseListResponse(BaseModel):
    cases: list[CaseResponse]
    memory_store: CaseStorage


class CaseDeleteResponse(BaseModel):
    deleted: bool
    memory_store: CaseStorage


def _case_response(record: CaseRecord) -> CaseResponse:
    return CaseResponse(
        case_id=record.case_id,
        message=record.message,
        severity=record.severity,
        severity_reason=record.severity_reason,
        filename=record.filename,
        created_at=record.created_at,
        classification_source=record.classification_source,
    )


@router.post("/decode", response_model=ResponderDecodeResponse)
async def decode_responder_image(image: UploadFile = File(...)):
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Please upload an image file.")
    if len(image_bytes) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="That image is too large for the demo.")

    try:
        message = decode_message(image_bytes)
    except SteganographyError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    classification: SeverityResult = classify_severity(message)
    return ResponderDecodeResponse(
        message=message,
        filename=image.filename,
        severity=classification.level,
        severity_reason=classification.reason,
        classification_source=classification.source,
    )


@router.post("/cases", response_model=CaseSubmitResponse)
def submit_responder_case(payload: CaseSubmitRequest):
    record, storage = save_case(
        message=payload.message.strip(),
        severity=payload.severity,
        severity_reason=payload.severity_reason.strip(),
        filename=payload.filename,
        classification_source=payload.classification_source,
    )
    return CaseSubmitResponse(case=_case_response(record), memory_store=storage)


@router.get("/cases", response_model=CaseListResponse)
def get_responder_cases(limit: int = 50):
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="Case limit must be between 1 and 100.")
    records, storage = list_cases(limit=limit)
    return CaseListResponse(cases=[_case_response(record) for record in records], memory_store=storage)


@router.delete("/cases/{case_id}", response_model=CaseDeleteResponse)
def remove_responder_case(case_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", case_id):
        raise HTTPException(status_code=422, detail="That responder case id is not valid.")
    deleted, storage = delete_case(case_id)
    return CaseDeleteResponse(deleted=deleted, memory_store=storage)
