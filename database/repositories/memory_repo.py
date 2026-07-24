"""
Memory Repository -- SQLite backend for conversations and user profile.

Replaces the JSON read/write in memory.py with indexed SQL queries.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from database.db import get_connection


# ---------------------------------------------------------------------------
# Conversations (short-term memory)
# ---------------------------------------------------------------------------

def save_conversation(
    user_input: str, role: str, response: str, timestamp: str | None = None,
) -> int:
    """Insert a conversation and return its row id."""
    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (user_input, role, response, timestamp) "
            "VALUES (?, ?, ?, ?)",
            (user_input, role, response, ts),
        )
        return cur.lastrowid


def get_recent_conversations(limit: int = 20) -> list[dict[str, str]]:
    """Return the most recent N conversations, oldest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT user_input, role, response, timestamp "
            "FROM conversations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    # Reverse so oldest is first (matches deque behaviour)
    return [dict(r) for r in reversed(rows)]


def get_last_conversation() -> dict[str, str] | None:
    """Return the most recent conversation, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT user_input, role, response, timestamp "
            "FROM conversations ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_conversation_count() -> int:
    """Return the total number of stored conversations."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()
    return row[0] if row else 0


def clear_conversations() -> None:
    """Delete all conversations."""
    with get_connection() as conn:
        conn.execute("DELETE FROM conversations")


def trim_conversations(keep: int = 20) -> None:
    """Keep only the most recent N conversations, delete the rest."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM conversations WHERE id NOT IN "
            "(SELECT id FROM conversations ORDER BY id DESC LIMIT ?)",
            (keep,),
        )


# ---------------------------------------------------------------------------
# User Profile (long-term memory)
# ---------------------------------------------------------------------------

def save_user_info(key: str, value: Any) -> None:
    """Upsert a user profile key-value pair. Value is JSON-encoded."""
    k = key.lower().strip()
    now = datetime.now().isoformat(timespec="seconds")
    v = json.dumps(value, ensure_ascii=False)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO user_profile (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (k, v, now),
        )


def get_user_info(key: str) -> Any | None:
    """Retrieve a user profile value by key, or None."""
    k = key.lower().strip()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM user_profile WHERE key = ?", (k,)
        ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return row[0]


def get_all_user_info() -> dict[str, Any]:
    """Return all user profile data as a dict."""
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM user_profile").fetchall()
    result = {}
    for row in rows:
        try:
            result[row[0]] = json.loads(row[1])
        except (json.JSONDecodeError, TypeError):
            result[row[0]] = row[1]
    return result


def delete_user_info(key: str) -> bool:
    """Delete a user profile key. Returns True if it existed."""
    k = key.lower().strip()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM user_profile WHERE key = ?", (k,))
    return cur.rowcount > 0


def clear_user_info() -> None:
    """Delete all user profile data."""
    with get_connection() as conn:
        conn.execute("DELETE FROM user_profile")
