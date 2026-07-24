"""
Reminder Repository -- SQLite backend for the scheduling system.
"""

from __future__ import annotations

from typing import Any

from database.db import get_connection


def add_reminder(id: str, task: str, time: str, created_at: str) -> None:
    """Insert a new reminder."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO reminders (id, task, time, created_at, completed) "
            "VALUES (?, ?, ?, ?, 0)",
            (id, task, time, created_at),
        )


def list_pending() -> list[dict[str, Any]]:
    """Return all pending (not completed) reminders, sorted by time."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, task, time, created_at, completed "
            "FROM reminders WHERE completed = 0 ORDER BY time"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "task": r["task"],
            "time": r["time"],
            "created_at": r["created_at"],
            "completed": bool(r["completed"]),
        }
        for r in rows
    ]


def delete_by_id(reminder_id: str) -> bool:
    """Delete a reminder by its ID. Returns True if it existed."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    return cur.rowcount > 0


def clear_all() -> int:
    """Delete all reminders. Returns count deleted."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM reminders")
    return cur.rowcount


def mark_completed(reminder_id: str) -> None:
    """Mark a reminder as completed."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE reminders SET completed = 1 WHERE id = ?", (reminder_id,)
        )


def get_due_reminders(now_iso: str) -> list[dict[str, Any]]:
    """Return all pending reminders whose time <= now."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, task, time, created_at "
            "FROM reminders WHERE completed = 0 AND time <= ?",
            (now_iso,),
        ).fetchall()
    return [dict(r) for r in rows]
