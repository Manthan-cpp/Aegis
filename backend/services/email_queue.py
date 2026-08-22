"""Persistent, retrying outbox for Aegis help emails.

The queue deliberately lives outside MongoDB. Email delivery must continue to
work during a temporary database or internet outage, so a small local SQLite
outbox is the reliable hand-off point on the machine running the backend.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Lock, Thread
from time import time
from typing import Any, Iterator

from services.emailjs_client import send_email_alert


DEFAULT_POLL_SECONDS = 5
DEFAULT_MAX_BACKOFF_SECONDS = 30

_worker_lock = Lock()
_worker_stop = Event()
_worker_thread: Thread | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _database_path() -> Path:
    configured = os.getenv("EMAIL_QUEUE_DB_PATH", "").strip()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[1] / path
    else:
        path = Path(__file__).resolve().parents[1] / "data" / "email_queue.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(_database_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    try:
        yield connection
    finally:
        connection.close()


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS email_queue (
            job_id TEXT PRIMARY KEY,
            client_request_id TEXT NOT NULL UNIQUE,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at REAL NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            sent_at TEXT,
            result_json TEXT,
            last_error TEXT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_queue_due ON email_queue(status, next_attempt_at, created_at)"
    )
    connection.commit()


def ensure_email_queue() -> None:
    with _connect() as connection:
        _ensure_schema(connection)


def recover_stale_sending_jobs() -> None:
    """Requeue jobs left mid-send by a previous backend process."""

    ensure_email_queue()
    with _connect() as connection:
        connection.execute(
            "UPDATE email_queue SET status = 'queued', next_attempt_at = ?, updated_at = ? WHERE status = 'sending'",
            (time(), _now_iso()),
        )
        connection.commit()


def _status_from_row(row: sqlite3.Row) -> dict[str, Any]:
    result: dict[str, Any] = {
        "job_id": row["job_id"],
        "status": row["status"],
        "attempts": int(row["attempts"]),
        "queued_at": row["created_at"],
        "updated_at": row["updated_at"],
        "sent_at": row["sent_at"],
        "last_error": row["last_error"],
    }
    if row["result_json"]:
        try:
            result.update(json.loads(row["result_json"]))
        except (TypeError, json.JSONDecodeError):
            pass
    try:
        payload = json.loads(row["payload_json"])
        recipient_type = payload.get("recipient_type")
        if recipient_type in {"trusted", "women_support"}:
            result["recipient_type"] = recipient_type
            result["recipient_label"] = (
                "Trusted contact" if recipient_type == "trusted" else "Women’s support authority"
            )
            result["demo_mode"] = (
                os.getenv("EMAIL_DEMO_MODE", "true").strip().casefold() in {"1", "true", "yes", "on"}
                and recipient_type == "women_support"
            )
    except (TypeError, json.JSONDecodeError):
        pass
    return result


def enqueue_email_job(payload: dict[str, Any], client_request_id: str | None = None) -> dict[str, Any]:
    """Persist a help email and return its idempotent queue record."""

    ensure_email_queue()
    request_id = (client_request_id or "").strip() or secrets.token_urlsafe(18)
    now = _now_iso()
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    with _connect() as connection:
        _ensure_schema(connection)
        existing = connection.execute(
            "SELECT * FROM email_queue WHERE client_request_id = ?",
            (request_id,),
        ).fetchone()
        if existing is not None:
            return _status_from_row(existing)

        job_id = secrets.token_urlsafe(16)
        connection.execute(
            """
            INSERT INTO email_queue (
                job_id, client_request_id, payload_json, status, attempts,
                next_attempt_at, created_at, updated_at
            ) VALUES (?, ?, ?, 'queued', 0, ?, ?, ?)
            """,
            (job_id, request_id, payload_json, time(), now, now),
        )
        row = connection.execute("SELECT * FROM email_queue WHERE job_id = ?", (job_id,)).fetchone()
        connection.commit()

    return _status_from_row(row)


def get_email_job(job_id: str) -> dict[str, Any] | None:
    ensure_email_queue()
    with _connect() as connection:
        row = connection.execute("SELECT * FROM email_queue WHERE job_id = ?", (job_id,)).fetchone()
    return _status_from_row(row) if row is not None else None


def _claim_due_job() -> sqlite3.Row | None:
    with _connect() as connection:
        _ensure_schema(connection)
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM email_queue WHERE status = 'queued' AND next_attempt_at <= ? ORDER BY created_at LIMIT 1",
            (time(),),
        ).fetchone()
        if row is None:
            connection.commit()
            return None
        now = _now_iso()
        connection.execute(
            "UPDATE email_queue SET status = 'sending', attempts = attempts + 1, updated_at = ? WHERE job_id = ? AND status = 'queued'",
            (now, row["job_id"]),
        )
        connection.commit()
    return row


def _retry_delay(attempts: int) -> float:
    configured = os.getenv(
        "EMAIL_QUEUE_MAX_BACKOFF_SECONDS",
        str(DEFAULT_MAX_BACKOFF_SECONDS),
    ).strip()
    try:
        max_backoff = max(5, int(configured))
    except ValueError:
        max_backoff = DEFAULT_MAX_BACKOFF_SECONDS
    return min(max_backoff, 5 * (2 ** max(0, attempts - 1)))


def _mark_sent(job_id: str, result: dict[str, Any]) -> None:
    now = _now_iso()
    with _connect() as connection:
        _ensure_schema(connection)
        connection.execute(
            "UPDATE email_queue SET status = 'sent', updated_at = ?, sent_at = ?, result_json = ?, last_error = NULL WHERE job_id = ?",
            (now, now, json.dumps(result, ensure_ascii=False), job_id),
        )
        connection.commit()


def _mark_retry(job_id: str, attempts: int, error: Exception) -> None:
    now = _now_iso()
    safe_error = " ".join(str(error).split())[:500] or type(error).__name__
    with _connect() as connection:
        _ensure_schema(connection)
        connection.execute(
            "UPDATE email_queue SET status = 'queued', next_attempt_at = ?, updated_at = ?, last_error = ? WHERE job_id = ?",
            (time() + _retry_delay(attempts), now, safe_error, job_id),
        )
        connection.commit()


def process_email_queue_once() -> dict[str, Any] | None:
    """Attempt one due job; network/config errors remain queued for retry."""

    row = _claim_due_job()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload_json"])
        result = send_email_alert(**payload)
    except Exception as error:  # noqa: BLE001 - the outbox must survive provider outages.
        _mark_retry(row["job_id"], int(row["attempts"]) + 1, error)
        status = get_email_job(row["job_id"])
        return status
    _mark_sent(row["job_id"], result)
    return get_email_job(row["job_id"])


def _worker_loop() -> None:
    poll_seconds = max(1, int(os.getenv("EMAIL_QUEUE_POLL_SECONDS", str(DEFAULT_POLL_SECONDS))))
    while not _worker_stop.is_set():
        try:
            process_email_queue_once()
        except Exception:
            # A malformed row or transient SQLite issue must not kill delivery
            # for every later job. The next loop will try again.
            pass
        _worker_stop.wait(poll_seconds)


def start_email_queue_worker() -> None:
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        recover_stale_sending_jobs()
        _worker_stop.clear()
        _worker_thread = Thread(target=_worker_loop, name="aegis-email-queue", daemon=True)
        _worker_thread.start()


def stop_email_queue_worker() -> None:
    global _worker_thread
    with _worker_lock:
        _worker_stop.set()
        if _worker_thread is not None and _worker_thread.is_alive():
            _worker_thread.join(timeout=2)
        _worker_thread = None


def clear_email_queue_for_tests() -> None:
    """Remove queue rows for isolated backend tests."""

    ensure_email_queue()
    with _connect() as connection:
        connection.execute("DELETE FROM email_queue")
        connection.commit()
