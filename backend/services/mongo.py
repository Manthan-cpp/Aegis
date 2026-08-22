"""Consent-gated conversation memory with MongoDB and local fallbacks.

MongoDB is used when ``MONGODB_URI`` is configured. If Atlas is unavailable,
the companion uses a small SQLite fallback in ``backend/data`` so opted-in
memory remains available during local development and temporary outages.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Literal, TypedDict

from pymongo import MongoClient
from pymongo.errors import PyMongoError


MAX_TURNS = 12
StorageKind = Literal["mongo", "local-demo"]


class ConversationTurn(TypedDict):
    role: Literal["user", "assistant"]
    content: str


_local_sessions: dict[str, list[ConversationTurn]] = {}
_local_lock = Lock()
_LOCAL_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "companion_memory.sqlite3"
_mongo_client: MongoClient | None = None
_mongo_lock = Lock()
_mongo_retry_after = 0.0

# Atlas is optional for local development. When it is unavailable, do not make
# every DM request wait for the full network timeout before using SQLite.
MONGO_SERVER_SELECTION_TIMEOUT_MS = 750
MONGO_FAILURE_COOLDOWN_SECONDS = 30.0


def mongo_database():
    """Return the configured database, or ``None`` when Mongo is not configured."""

    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        return None

    global _mongo_client, _mongo_retry_after
    with _mongo_lock:
        now = time.monotonic()
        if _mongo_client is None and now < _mongo_retry_after:
            return None
        if _mongo_client is None:
            client: MongoClient | None = None
            try:
                client = MongoClient(
                    uri,
                    serverSelectionTimeoutMS=MONGO_SERVER_SELECTION_TIMEOUT_MS,
                    connectTimeoutMS=MONGO_SERVER_SELECTION_TIMEOUT_MS,
                )
                client.admin.command("ping")
            except PyMongoError:
                if client is not None:
                    client.close()
                _mongo_retry_after = time.monotonic() + MONGO_FAILURE_COOLDOWN_SECONDS
                raise
            _mongo_client = client
            _mongo_retry_after = 0.0
        return _mongo_client[os.getenv("MONGODB_DB_NAME", "aegis")]


def mark_mongo_unavailable() -> None:
    """Open the local fallback circuit after a Mongo operation fails."""

    global _mongo_client, _mongo_retry_after
    with _mongo_lock:
        client = _mongo_client
        _mongo_client = None
        _mongo_retry_after = time.monotonic() + MONGO_FAILURE_COOLDOWN_SECONDS
    if client is not None:
        client.close()


def _mongo_collection():
    """Return the companion collection or ``None`` when Mongo is not configured."""

    database = mongo_database()
    return database["companion_sessions"] if database is not None else None


def _local_database() -> sqlite3.Connection:
    """Open the durable local fallback used when MongoDB is unavailable."""

    _LOCAL_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(_LOCAL_DATABASE_PATH), timeout=10)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS companion_sessions (
            session_id TEXT PRIMARY KEY,
            turns_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return connection


def _normalise_turns(turns: object) -> list[ConversationTurn]:
    if not isinstance(turns, list):
        return []
    return [
        {"role": turn["role"], "content": turn["content"]}
        for turn in turns
        if isinstance(turn, dict)
        and turn.get("role") in {"user", "assistant"}
        and isinstance(turn.get("content"), str)
    ][-MAX_TURNS:]


def _load_local_turns(session_id: str) -> list[ConversationTurn]:
    cached_turns = _local_sessions.get(session_id)
    if cached_turns is not None:
        return list(cached_turns[-MAX_TURNS:])

    try:
        with _local_database() as connection:
            row = connection.execute(
                "SELECT turns_json FROM companion_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
    except sqlite3.Error:
        return []

    if not row:
        return []
    try:
        turns = _normalise_turns(json.loads(row[0]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    _local_sessions[session_id] = turns
    return list(turns)


def _save_local_turns(session_id: str, turns: list[ConversationTurn]) -> None:
    trimmed_turns = turns[-MAX_TURNS:]
    _local_sessions[session_id] = list(trimmed_turns)
    try:
        with _local_database() as connection:
            connection.execute(
                """
                INSERT INTO companion_sessions(session_id, turns_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    turns_json = excluded.turns_json,
                    updated_at = excluded.updated_at
                """,
                (session_id, json.dumps(trimmed_turns), datetime.now(UTC).isoformat()),
            )
    except sqlite3.Error:
        # The in-process cache still keeps the current conversation usable.
        pass


def load_recent_turns(session_id: str) -> tuple[list[ConversationTurn], StorageKind]:
    try:
        collection = _mongo_collection()
        if collection is not None:
            document = collection.find_one({"session_id": session_id}, {"turns": 1}) or {}
            turns = document.get("turns", [])[-MAX_TURNS:]
            return [
                {"role": turn["role"], "content": turn["content"]}
                for turn in turns
                if turn.get("role") in {"user", "assistant"} and isinstance(turn.get("content"), str)
            ], "mongo"
    except PyMongoError:
        # A local fallback is safer than failing a support conversation because a
        # free-tier database is temporarily unavailable.
        pass

    with _local_lock:
        return _load_local_turns(session_id), "local-demo"


def save_turns(session_id: str, turns: list[ConversationTurn]) -> StorageKind:
    stamped_turns = [
        {**turn, "created_at": datetime.now(UTC)}
        for turn in turns
    ]
    try:
        collection = _mongo_collection()
        if collection is not None:
            collection.update_one(
                {"session_id": session_id},
                {
                    "$push": {"turns": {"$each": stamped_turns, "$slice": -MAX_TURNS}},
                    "$set": {"updated_at": datetime.now(UTC)},
                    "$setOnInsert": {"created_at": datetime.now(UTC)},
                },
                upsert=True,
            )
            return "mongo"
    except PyMongoError:
        pass

    with _local_lock:
        # Load the durable fallback first so a backend restart does not discard
        # earlier opted-in turns when MongoDB is temporarily unreachable.
        current_turns = _load_local_turns(session_id)
        current_turns.extend(turns)
        _save_local_turns(session_id, current_turns)
    return "local-demo"


def clear_memory(session_id: str) -> StorageKind:
    cleared_from_mongo = False
    try:
        collection = _mongo_collection()
        if collection is not None:
            collection.delete_one({"session_id": session_id})
            cleared_from_mongo = True
    except PyMongoError:
        pass

    with _local_lock:
        _local_sessions.pop(session_id, None)
        try:
            with _local_database() as connection:
                connection.execute("DELETE FROM companion_sessions WHERE session_id = ?", (session_id,))
        except sqlite3.Error:
            pass
    return "mongo" if cleared_from_mongo else "local-demo"


def clear_local_sessions_for_tests() -> None:
    """Test helper; never called by the application itself."""

    with _local_lock:
        _local_sessions.clear()
        try:
            with _local_database() as connection:
                connection.execute("DELETE FROM companion_sessions")
        except sqlite3.Error:
            pass
