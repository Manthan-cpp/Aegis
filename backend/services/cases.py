"""Responder case storage with a MongoDB store and transparent local fallback."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Literal

from pymongo.errors import PyMongoError

from services.mongo import mongo_database


CaseStorage = Literal["mongo", "local-demo"]
Severity = Literal["low", "medium", "high"]
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}
CASES_COLLECTION = "sos_cases"


@dataclass(frozen=True)
class CaseRecord:
    case_id: str
    message: str
    severity: Severity
    severity_reason: str
    filename: str | None
    created_at: datetime
    classification_source: Literal["groq", "rule-based"]


_local_cases: list[CaseRecord] = []
_local_lock = Lock()


def _cases_collection():
    database = mongo_database()
    return database[CASES_COLLECTION] if database is not None else None


def _record_from_document(document: dict) -> CaseRecord:
    created_at = document.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = datetime.now(UTC)
    return CaseRecord(
        case_id=str(document.get("case_id", "")),
        message=str(document.get("message", "")),
        severity=document.get("severity", "low"),
        severity_reason=str(document.get("severity_reason", "")),
        filename=document.get("filename"),
        created_at=created_at,
        classification_source=document.get("classification_source", "rule-based"),
    )


def save_case(
    message: str,
    severity: Severity,
    severity_reason: str,
    filename: str | None,
    classification_source: Literal["groq", "rule-based"],
) -> tuple[CaseRecord, CaseStorage]:
    record = CaseRecord(
        case_id=uuid.uuid4().hex,
        message=message,
        severity=severity,
        severity_reason=severity_reason,
        filename=filename,
        created_at=datetime.now(UTC),
        classification_source=classification_source,
    )
    document = {
        "case_id": record.case_id,
        "message": record.message,
        "severity": record.severity,
        "severity_rank": SEVERITY_RANK[record.severity],
        "severity_reason": record.severity_reason,
        "filename": record.filename,
        "classification_source": record.classification_source,
        "created_at": record.created_at,
    }
    try:
        collection = _cases_collection()
        if collection is not None:
            collection.insert_one(document)
            return record, "mongo"
    except PyMongoError:
        pass

    with _local_lock:
        _local_cases.append(record)
    return record, "local-demo"


def list_cases(limit: int = 50) -> tuple[list[CaseRecord], CaseStorage]:
    try:
        collection = _cases_collection()
        if collection is not None:
            documents = collection.find().sort([("severity_rank", -1), ("created_at", -1)]).limit(limit)
            return [_record_from_document(document) for document in documents], "mongo"
    except PyMongoError:
        pass

    with _local_lock:
        records = sorted(_local_cases, key=lambda item: (SEVERITY_RANK[item.severity], item.created_at), reverse=True)
        return list(records[:limit]), "local-demo"


def delete_case(case_id: str) -> tuple[bool, CaseStorage]:
    """Delete exactly one responder case by its generated id."""

    try:
        collection = _cases_collection()
        if collection is not None:
            result = collection.delete_one({"case_id": case_id})
            return result.deleted_count > 0, "mongo"
    except PyMongoError:
        pass

    with _local_lock:
        original_count = len(_local_cases)
        _local_cases[:] = [record for record in _local_cases if record.case_id != case_id]
        return len(_local_cases) < original_count, "local-demo"


def clear_local_cases_for_tests() -> None:
    with _local_lock:
        _local_cases.clear()
