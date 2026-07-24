"""
Personality Repository -- SQLite backend for adaptive personality preferences.

Stores and retrieves personality adaptation data: tone, verbosity,
warmth, formality, humor level, and other conversational style preferences.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from database.db import get_connection


# ---------------------------------------------------------------------------
# Personality Preferences
# ---------------------------------------------------------------------------

def save_preference(key: str, value: Any, confidence: float = 0.5) -> None:
    """Upsert a personality preference with confidence score."""
    k = key.lower().strip()
    now = datetime.now().isoformat(timespec="seconds")
    v = json.dumps(value, ensure_ascii=False)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO personality_preferences (key, value, confidence, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "confidence=excluded.confidence, updated_at=excluded.updated_at",
            (k, v, confidence, now),
        )


def get_preference(key: str) -> tuple[Any, float] | None:
    """Return (value, confidence) for a preference, or None."""
    k = key.lower().strip()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value, confidence FROM personality_preferences WHERE key = ?",
            (k,),
        ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0]), row[1]
    except (json.JSONDecodeError, TypeError):
        return row[0], row[1]


def get_all_preferences() -> dict[str, tuple[Any, float]]:
    """Return all personality preferences as {key: (value, confidence)}."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT key, value, confidence FROM personality_preferences"
        ).fetchall()
    result = {}
    for row in rows:
        try:
            result[row[0]] = (json.loads(row[1]), row[2])
        except (json.JSONDecodeError, TypeError):
            result[row[0]] = (row[1], row[2])
    return result


def update_confidence(key: str, delta: float) -> None:
    """Adjust confidence for a preference (clamped to 0.0-1.0)."""
    k = key.lower().strip()
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute(
            "UPDATE personality_preferences SET "
            "confidence = MIN(1.0, MAX(0.0, confidence + ?)), "
            "updated_at = ? WHERE key = ?",
            (delta, now, k),
        )


def clear_preferences() -> None:
    """Delete all personality preferences."""
    with get_connection() as conn:
        conn.execute("DELETE FROM personality_preferences")


# ---------------------------------------------------------------------------
# Conversation Context
# ---------------------------------------------------------------------------

def save_context(
    session_id: str, topic: str, summary: str | None = None,
    emotion: str = "neutral", turn_count: int = 0,
) -> int:
    """Insert or update a conversation context entry."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        # Check if context exists for this session+topic
        existing = conn.execute(
            "SELECT id FROM conversation_context "
            "WHERE session_id = ? AND topic = ?",
            (session_id, topic),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE conversation_context SET summary = ?, emotion = ?, "
                "turn_count = ?, updated_at = ? WHERE id = ?",
                (summary, emotion, turn_count, now, existing[0]),
            )
            return existing[0]
        else:
            cur = conn.execute(
                "INSERT INTO conversation_context "
                "(session_id, topic, summary, emotion, turn_count, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, topic, summary, emotion, turn_count, now, now),
            )
            return cur.lastrowid


def get_session_context(session_id: str) -> list[dict]:
    """Return all context entries for a session."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT topic, summary, emotion, turn_count, updated_at "
            "FROM conversation_context WHERE session_id = ? "
            "ORDER BY updated_at DESC",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_contexts(limit: int = 10) -> list[dict]:
    """Return most recent context entries across all sessions."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT session_id, topic, summary, emotion, turn_count, updated_at "
            "FROM conversation_context ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Active Goals
# ---------------------------------------------------------------------------

def save_goal(goal: str, context: str | None = None) -> int:
    """Create a new active goal."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO conversation_goals (goal, status, progress, context, created_at, updated_at) "
            "VALUES (?, 'active', 0.0, ?, ?, ?)",
            (goal, context, now, now),
        )
        return cur.lastrowid


def update_goal_progress(goal_id: int, progress: float, status: str | None = None) -> None:
    """Update goal progress (0.0-1.0) and optionally status."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        if status:
            conn.execute(
                "UPDATE conversation_goals SET progress = ?, status = ?, updated_at = ? WHERE id = ?",
                (progress, status, now, goal_id),
            )
        else:
            conn.execute(
                "UPDATE conversation_goals SET progress = ?, updated_at = ? WHERE id = ?",
                (progress, now, goal_id),
            )


def get_active_goals() -> list[dict]:
    """Return all active goals."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, goal, status, progress, context, created_at, updated_at "
            "FROM conversation_goals WHERE status = 'active' "
            "ORDER BY updated_at DESC",
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_goals(limit: int = 20) -> list[dict]:
    """Return recent goals of any status."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, goal, status, progress, context, created_at, updated_at "
            "FROM conversation_goals ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Session Summaries
# ---------------------------------------------------------------------------

def save_session_summary(
    session_id: str, summary: str, topics: list[str] | None = None,
    dominant_emotion: str = "neutral", turn_count: int = 0,
) -> None:
    """Save or update a session summary."""
    now = datetime.now().isoformat(timespec="seconds")
    topics_json = json.dumps(topics or [], ensure_ascii=False)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO session_summaries "
            "(session_id, summary, topics, dominant_emotion, turn_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET summary=excluded.summary, "
            "topics=excluded.topics, dominant_emotion=excluded.dominant_emotion, "
            "turn_count=excluded.turn_count",
            (session_id, summary, topics_json, dominant_emotion, turn_count, now),
        )


def get_recent_summaries(limit: int = 5) -> list[dict]:
    """Return the most recent session summaries."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT session_id, summary, topics, dominant_emotion, turn_count, created_at "
            "FROM session_summaries ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["topics"] = json.loads(d["topics"]) if d["topics"] else []
        except (json.JSONDecodeError, TypeError):
            d["topics"] = []
        result.append(d)
    return result


def get_session_summary(session_id: str) -> dict | None:
    """Return the summary for a specific session."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT session_id, summary, topics, dominant_emotion, turn_count, created_at "
            "FROM session_summaries WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    try:
        d["topics"] = json.loads(d["topics"]) if d["topics"] else []
    except (json.JSONDecodeError, TypeError):
        d["topics"] = []
    return d
