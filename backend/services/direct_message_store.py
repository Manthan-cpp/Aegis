"""Durable local fallback for authenticated one-to-one messages.

MongoDB remains the preferred store.  This small SQLite store exists so that
local development and a disconnected hackathon demo do not lose private
profiles or conversations when Atlas is temporarily unreachable.
"""

from __future__ import annotations

import sqlite3
import uuid
import re
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator


DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "direct_messages.sqlite3"
DEFAULT_DISAPPEARING_HOURS = 6
DEFAULT_DISAPPEARING_SECONDS = DEFAULT_DISAPPEARING_HOURS * 60 * 60
MIN_DISAPPEARING_SECONDS = 10


class LocalDirectMessageStoreError(RuntimeError):
    """A user-facing local private-message storage error."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _profile(row: sqlite3.Row | dict[str, Any]) -> dict[str, str]:
    return {
        "user_id": str(row.get("user_id", "") if isinstance(row, dict) else row["user_id"]),
        "username": str(row.get("username", "") if isinstance(row, dict) else row["username"]),
        "display_name": str(
            (row.get("display_name") if isinstance(row, dict) else row["display_name"])
            or (row.get("username") if isinstance(row, dict) else row["username"])
            or "Aegis user"
        ),
    }


def _value(row: sqlite3.Row, key: str, default: Any = "") -> Any:
    value = row[key]
    return default if value is None else value


class LocalDirectMessageStore:
    """SQLite-backed store with the same data guarantees as the Mongo path."""

    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(self.database_path), timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            self._ensure_schema(connection)
            yield connection
            connection.commit()
        except sqlite3.IntegrityError:
            raise
        except sqlite3.Error as error:
            raise LocalDirectMessageStoreError("Aegis could not save private messages locally.") from error
        finally:
            if "connection" in locals():
                connection.close()

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS dm_profiles (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                username_normalized TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dm_conversations (
                conversation_id TEXT PRIMARY KEY,
                participant_a TEXT NOT NULL,
                participant_b TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_message TEXT NOT NULL DEFAULT '',
                last_sender_id TEXT NOT NULL DEFAULT '',
                disappearing_enabled INTEGER NOT NULL DEFAULT 0,
                disappearing_hours INTEGER NOT NULL DEFAULT 6,
                disappearing_seconds INTEGER NOT NULL DEFAULT 21600,
                UNIQUE(participant_a, participant_b)
            );

            CREATE TABLE IF NOT EXISTS dm_messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                FOREIGN KEY(conversation_id) REFERENCES dm_conversations(conversation_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_dm_profiles_username
                ON dm_profiles(username_normalized);
            CREATE INDEX IF NOT EXISTS idx_dm_conversations_participants
                ON dm_conversations(participant_a, participant_b);
            CREATE INDEX IF NOT EXISTS idx_dm_conversations_updated
                ON dm_conversations(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_dm_messages_conversation
                ON dm_messages(conversation_id, created_at);
            """
        )
        conversation_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(dm_conversations)").fetchall()
        }
        if "disappearing_enabled" not in conversation_columns:
            connection.execute(
                "ALTER TABLE dm_conversations ADD COLUMN disappearing_enabled INTEGER NOT NULL DEFAULT 0"
            )
        if "disappearing_hours" not in conversation_columns:
            connection.execute(
                "ALTER TABLE dm_conversations ADD COLUMN disappearing_hours INTEGER NOT NULL DEFAULT 6"
            )
        if "disappearing_seconds" not in conversation_columns:
            connection.execute(
                "ALTER TABLE dm_conversations ADD COLUMN disappearing_seconds INTEGER NOT NULL DEFAULT 21600"
            )
            connection.execute(
                """
                UPDATE dm_conversations
                SET disappearing_seconds = disappearing_hours * 3600
                WHERE disappearing_hours != 6
                """
            )
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(dm_messages)").fetchall()
        }
        if "expires_at" not in columns:
            connection.execute("ALTER TABLE dm_messages ADD COLUMN expires_at TEXT")
        if "client_message_id" not in columns:
            connection.execute("ALTER TABLE dm_messages ADD COLUMN client_message_id TEXT")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_dm_messages_client_id
                ON dm_messages(conversation_id, client_message_id)
                WHERE client_message_id IS NOT NULL
            """
        )

    def sync_profile(self, user_id: str, username: str, display_name: str | None = None) -> dict[str, str]:
        now = _now()
        try:
            with self._connect() as connection:
                existing = connection.execute(
                    "SELECT created_at FROM dm_profiles WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                created_at = str(existing["created_at"]) if existing else now
                connection.execute(
                    """
                    INSERT INTO dm_profiles
                        (user_id, username, username_normalized, display_name, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = excluded.username,
                        username_normalized = excluded.username_normalized,
                        display_name = excluded.display_name,
                        updated_at = excluded.updated_at
                    """,
                    (
                        user_id,
                        username,
                        username.casefold(),
                        (display_name or username).strip()[:120] or username,
                        created_at,
                        now,
                    ),
                )
                row = connection.execute(
                    "SELECT user_id, username, display_name FROM dm_profiles WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                return _profile(row)
        except sqlite3.IntegrityError as error:
            raise LocalDirectMessageStoreError(
                "That username is already being used by another Aegis account."
            ) from error

    def search_profiles(self, user_id: str, query: str, limit: int = 20) -> list[dict[str, str]]:
        normalized_query = query.strip().casefold()
        compact_query = re.sub(r"[\s_.-]+", "", normalized_query)
        escaped_query = (
            compact_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        like = f"%{escaped_query}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT user_id, username, display_name
                FROM dm_profiles
                WHERE user_id != ?
                  AND (? = '' OR REPLACE(REPLACE(REPLACE(username_normalized, ' ', ''), '_', ''), '-', '') LIKE ? ESCAPE '\\')
                ORDER BY username_normalized ASC
                LIMIT ?
                """,
                (user_id, normalized_query, like, limit),
            ).fetchall()
            return [_profile(row) for row in rows]

    @staticmethod
    def _conversation(row: sqlite3.Row, recipient: dict[str, Any], current_user_id: str) -> dict[str, Any]:
        last_sender_id = str(_value(row, "last_sender_id"))
        legacy_hours = int(_value(row, "disappearing_hours", DEFAULT_DISAPPEARING_HOURS))
        seconds = int(_value(row, "disappearing_seconds", legacy_hours * 60 * 60))
        return {
            "conversation_id": str(row["conversation_id"]),
            "recipient": recipient,
            "last_message": str(_value(row, "last_message")),
            "last_sender_id": last_sender_id,
            "updated_at": str(_value(row, "updated_at")),
            "is_last_message_from_me": last_sender_id == current_user_id,
            "disappearing_enabled": bool(_value(row, "disappearing_enabled", 0)),
            "disappearing_seconds": seconds,
        }

    @staticmethod
    def _purge_expired(connection: sqlite3.Connection, conversation_id: str) -> None:
        now = _now()
        deleted = connection.execute(
            """
            DELETE FROM dm_messages
            WHERE conversation_id = ? AND expires_at IS NOT NULL AND expires_at <= ?
            """,
            (conversation_id, now),
        ).rowcount
        if not deleted:
            return
        latest = connection.execute(
            """
            SELECT content, sender_id
            FROM dm_messages WHERE conversation_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
        connection.execute(
            """
            UPDATE dm_conversations
            SET last_message = ?, last_sender_id = ?, updated_at = ?
            WHERE conversation_id = ?
            """,
            (
                str(latest["content"]) if latest else "",
                str(latest["sender_id"]) if latest else "",
                now,
                conversation_id,
            ),
        )

    @staticmethod
    def _expiry_for(conversation: sqlite3.Row, now: datetime) -> str | None:
        if not bool(_value(conversation, "disappearing_enabled", 0)):
            return None
        legacy_hours = int(_value(conversation, "disappearing_hours", DEFAULT_DISAPPEARING_HOURS))
        seconds = max(
            MIN_DISAPPEARING_SECONDS,
            int(_value(conversation, "disappearing_seconds", legacy_hours * 60 * 60)),
        )
        try:
            return (now + timedelta(seconds=seconds)).isoformat()
        except OverflowError:
            return datetime.max.replace(tzinfo=UTC).isoformat()

    def create_conversation(self, user_id: str, recipient_username: str) -> dict[str, Any]:
        normalized_username = recipient_username.strip().casefold()
        with self._connect() as connection:
            target_row = connection.execute(
                "SELECT user_id, username, display_name FROM dm_profiles WHERE username_normalized = ?",
                (normalized_username,),
            ).fetchone()
            if not target_row:
                raise LocalDirectMessageStoreError("That Aegis user could not be found.")
            target = _profile(target_row)
            target_id = target["user_id"]
            if not target_id or target_id == user_id:
                raise LocalDirectMessageStoreError("Choose another signed-in user to start a conversation.")

            participant_a, participant_b = sorted((user_id, target_id))
            row = connection.execute(
                """
                SELECT conversation_id, last_message, last_sender_id, updated_at,
                       disappearing_enabled, disappearing_hours, disappearing_seconds
                FROM dm_conversations
                WHERE participant_a = ? AND participant_b = ?
                """,
                (participant_a, participant_b),
            ).fetchone()
            if row:
                return self._conversation(row, target, user_id)

            now = _now()
            conversation_id = uuid.uuid4().hex
            connection.execute(
                """
                INSERT INTO dm_conversations
                    (conversation_id, participant_a, participant_b, created_at, updated_at,
                     disappearing_enabled, disappearing_hours, disappearing_seconds)
                VALUES (?, ?, ?, ?, ?, 0, 6, 21600)
                """,
                (conversation_id, participant_a, participant_b, now, now),
            )
            row = connection.execute(
                """
                SELECT conversation_id, last_message, last_sender_id, updated_at,
                       disappearing_enabled, disappearing_hours, disappearing_seconds
                FROM dm_conversations WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
            return self._conversation(row, target, user_id)

    def list_conversations(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT conversation_id, participant_a, participant_b, last_message, last_sender_id, updated_at,
                       disappearing_enabled, disappearing_hours, disappearing_seconds
                FROM dm_conversations
                WHERE participant_a = ? OR participant_b = ?
                ORDER BY updated_at DESC
                LIMIT 50
                """,
                (user_id, user_id),
            ).fetchall()
            result = []
            for row in rows:
                self._purge_expired(connection, str(row["conversation_id"]))
                row = connection.execute(
                    """
                    SELECT conversation_id, participant_a, participant_b, last_message, last_sender_id, updated_at,
                           disappearing_enabled, disappearing_hours, disappearing_seconds
                    FROM dm_conversations WHERE conversation_id = ?
                    """,
                    (row["conversation_id"],),
                ).fetchone()
                recipient_id = row["participant_b"] if row["participant_a"] == user_id else row["participant_a"]
                recipient_row = connection.execute(
                    "SELECT user_id, username, display_name FROM dm_profiles WHERE user_id = ?",
                    (recipient_id,),
                ).fetchone()
                recipient = _profile(recipient_row) if recipient_row else {
                    "user_id": recipient_id,
                    "username": "Aegis user",
                    "display_name": "Aegis user",
                }
                result.append(self._conversation(row, recipient, user_id))
            return result

    def get_messages(self, user_id: str, conversation_id: str, limit: int = 80) -> list[dict[str, Any]]:
        with self._connect() as connection:
            conversation = connection.execute(
                """
                SELECT conversation_id, participant_a, participant_b,
                       disappearing_enabled, disappearing_hours, disappearing_seconds
                FROM dm_conversations WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
            if not conversation:
                raise LocalDirectMessageStoreError("That conversation no longer exists.")
            if user_id not in {conversation["participant_a"], conversation["participant_b"]}:
                raise LocalDirectMessageStoreError("You do not have access to this conversation.")
            self._purge_expired(connection, conversation_id)
            rows = connection.execute(
                """
                SELECT message_id, sender_id, content, created_at, expires_at
                FROM dm_messages WHERE conversation_id = ?
                ORDER BY created_at ASC LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
            return [
                {
                    "message_id": str(row["message_id"]),
                    "sender_id": str(row["sender_id"]),
                    "content": str(row["content"]),
                    "created_at": str(row["created_at"]),
                    "expires_at": str(row["expires_at"]) if row["expires_at"] else None,
                    "is_from_me": str(row["sender_id"]) == user_id,
                }
                for row in rows
            ]

    def send_message(
        self,
        user_id: str,
        conversation_id: str,
        content: str,
        client_message_id: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            conversation = connection.execute(
                """
                SELECT conversation_id, participant_a, participant_b,
                       disappearing_enabled, disappearing_hours, disappearing_seconds
                FROM dm_conversations WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
            if not conversation:
                raise LocalDirectMessageStoreError("That conversation no longer exists.")
            if user_id not in {conversation["participant_a"], conversation["participant_b"]}:
                raise LocalDirectMessageStoreError("You do not have access to this conversation.")
            self._purge_expired(connection, conversation_id)

            if client_message_id:
                existing = connection.execute(
                    """
                    SELECT message_id, sender_id, content, created_at, expires_at
                    FROM dm_messages
                    WHERE conversation_id = ? AND client_message_id = ?
                    """,
                    (conversation_id, client_message_id),
                ).fetchone()
                if existing:
                    return {
                        "message_id": str(existing["message_id"]),
                        "sender_id": str(existing["sender_id"]),
                        "content": str(existing["content"]),
                        "created_at": str(existing["created_at"]),
                        "expires_at": str(existing["expires_at"]) if existing["expires_at"] else None,
                        "is_from_me": str(existing["sender_id"]) == user_id,
                    }

            now = _now()
            expiry = self._expiry_for(conversation, datetime.now(UTC))
            message_id = uuid.uuid4().hex
            connection.execute(
                """
                INSERT INTO dm_messages
                    (message_id, conversation_id, sender_id, content, created_at, expires_at, client_message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, conversation_id, user_id, content, now, expiry, client_message_id),
            )
            connection.execute(
                """
                UPDATE dm_conversations
                SET last_message = ?, last_sender_id = ?, updated_at = ?
                WHERE conversation_id = ?
                """,
                (content, user_id, now, conversation_id),
            )
            return {
                "message_id": message_id,
                "sender_id": user_id,
                "content": content,
                "created_at": now,
                "expires_at": expiry,
                "is_from_me": True,
            }

    def update_settings(self, user_id: str, conversation_id: str, enabled: bool, seconds: int) -> dict[str, Any]:
        with self._connect() as connection:
            conversation = connection.execute(
                """
                SELECT conversation_id, participant_a, participant_b,
                       disappearing_enabled, disappearing_hours, disappearing_seconds
                FROM dm_conversations WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
            if not conversation:
                raise LocalDirectMessageStoreError("That conversation no longer exists.")
            if user_id not in {conversation["participant_a"], conversation["participant_b"]}:
                raise LocalDirectMessageStoreError("You do not have access to this conversation.")
            connection.execute(
                """
                UPDATE dm_conversations
                SET disappearing_enabled = ?, disappearing_hours = ?, disappearing_seconds = ?
                WHERE conversation_id = ?
                """,
                (1 if enabled else 0, max(1, (seconds + 3599) // 3600), seconds, conversation_id),
            )
            return {
                "conversation_id": conversation_id,
                "disappearing_enabled": enabled,
                "disappearing_seconds": seconds,
            }

    def delete_messages(self, user_id: str, conversation_id: str, message_ids: list[str]) -> dict[str, Any]:
        with self._connect() as connection:
            conversation = connection.execute(
                "SELECT conversation_id, participant_a, participant_b FROM dm_conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if not conversation:
                raise LocalDirectMessageStoreError("That conversation no longer exists.")
            if user_id not in {conversation["participant_a"], conversation["participant_b"]}:
                raise LocalDirectMessageStoreError("You do not have access to this conversation.")
            self._purge_expired(connection, conversation_id)
            unique_ids = list(dict.fromkeys(message_ids))
            if not unique_ids:
                return {"conversation_id": conversation_id, "deleted_message_ids": []}
            placeholders = ", ".join("?" for _ in unique_ids)
            rows = connection.execute(
                f"SELECT message_id FROM dm_messages WHERE conversation_id = ? AND message_id IN ({placeholders})",
                [conversation_id, *unique_ids],
            ).fetchall()
            deleted_ids = [str(row["message_id"]) for row in rows]
            if deleted_ids:
                connection.execute(
                    f"DELETE FROM dm_messages WHERE conversation_id = ? AND message_id IN ({placeholders})",
                    [conversation_id, *deleted_ids],
                )
                self._purge_expired(connection, conversation_id)
                latest = connection.execute(
                    "SELECT content, sender_id FROM dm_messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
                    (conversation_id,),
                ).fetchone()
                connection.execute(
                    "UPDATE dm_conversations SET last_message = ?, last_sender_id = ?, updated_at = ? WHERE conversation_id = ?",
                    (str(latest["content"]) if latest else "", str(latest["sender_id"]) if latest else "", _now(), conversation_id),
                )
            return {"conversation_id": conversation_id, "deleted_message_ids": deleted_ids}
