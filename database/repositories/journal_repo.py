"""
Journal Repository -- SQLite backend for the journaling system.
"""

from __future__ import annotations

from typing import Any

from database.db import get_connection


def add_entry(
    id: str, date: str, time: str, summary: str,
    emotion: str, emotion_cause: str | None, notes: str | None,
) -> None:
    """Insert a new journal entry."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO journal_entries "
            "(id, date, time, summary, emotion, emotion_cause, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (id, date, time, summary, emotion, emotion_cause, notes),
        )


def get_entries(limit: int = 10) -> list[dict[str, Any]]:
    """Return recent journal entries (newest first)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM journal_entries ORDER BY date DESC, time DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_entries() -> list[dict[str, Any]]:
    """Return all journal entries (oldest first)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM journal_entries ORDER BY date, time"
        ).fetchall()
    return [dict(r) for r in rows]


def get_entries_by_date(date: str) -> list[dict[str, Any]]:
    """Return all journal entries for a specific date."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM journal_entries WHERE date = ? ORDER BY time",
            (date,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_entry_count() -> int:
    """Return the total number of journal entries."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()
    return row[0] if row else 0


def clear_all() -> None:
    """Delete all journal entries."""
    with get_connection() as conn:
        conn.execute("DELETE FROM journal_entries")
