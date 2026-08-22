"""Consent-gated conversation memory with MongoDB and local-demo fallbacks.

MongoDB is used when ``MONGODB_URI`` is configured. Until then, a process-local
store keeps the companion usable during development; that fallback disappears
when the backend restarts and is never presented as durable storage.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
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
        return list(_local_sessions.get(session_id, [])[-MAX_TURNS:]), "local-demo"


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
        current_turns = _local_sessions.setdefault(session_id, [])
        current_turns.extend(turns)
        del current_turns[:-MAX_TURNS]
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
    return "mongo" if cleared_from_mongo else "local-demo"


def clear_local_sessions_for_tests() -> None:
    """Test helper; never called by the application itself."""

    with _local_lock:
        _local_sessions.clear()
