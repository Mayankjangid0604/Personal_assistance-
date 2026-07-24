"""
Notification Repository -- SQLite backend for the notification system.
"""

from __future__ import annotations

from typing import Any

from database.db import get_connection


def add_notification(
    id: str, message: str, category: str, source: str, time: str,
) -> None:
    """Insert a new notification."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO notifications (id, message, category, source, time, read) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            (id, message, category, source, time),
        )
        # Keep at most 50
        conn.execute(
            "DELETE FROM notifications WHERE id NOT IN "
            "(SELECT id FROM notifications ORDER BY time DESC LIMIT 50)"
        )


def get_notifications(unread_only: bool = False, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent notifications (newest first)."""
    if unread_only:
        sql = "SELECT * FROM notifications WHERE read = 0 ORDER BY time DESC LIMIT ?"
    else:
        sql = "SELECT * FROM notifications ORDER BY time DESC LIMIT ?"
    with get_connection() as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
    return [
        {
            "id": r["id"],
            "message": r["message"],
            "category": r["category"],
            "source": r["source"],
            "time": r["time"],
            "read": bool(r["read"]),
        }
        for r in rows
    ]


def get_unread_count() -> int:
    """Return the number of unread notifications."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE read = 0"
        ).fetchone()
    return row[0] if row else 0


def mark_all_read() -> int:
    """Mark every notification as read. Returns count marked."""
    with get_connection() as conn:
        cur = conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")
    return cur.rowcount


def clear_all() -> int:
    """Delete all notifications. Returns count deleted."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM notifications")
    return cur.rowcount
