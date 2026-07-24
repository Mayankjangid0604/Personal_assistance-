"""
Learning Repository -- SQLite backend for interests, practice, and plans.
"""

from __future__ import annotations

import json
from typing import Any

from database.db import get_connection


# ---------------------------------------------------------------------------
# Interests
# ---------------------------------------------------------------------------

def save_interest(topic: str, count: int) -> None:
    """Upsert an interest topic count."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO learning_interests (topic, count) VALUES (?, ?) "
            "ON CONFLICT(topic) DO UPDATE SET count=excluded.count",
            (topic, count),
        )


def get_all_interests() -> dict[str, int]:
    """Return {topic: count} for all tracked interests."""
    with get_connection() as conn:
        rows = conn.execute("SELECT topic, count FROM learning_interests").fetchall()
    return {r["topic"]: r["count"] for r in rows}


def clear_interests() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM learning_interests")


# ---------------------------------------------------------------------------
# Practice Log
# ---------------------------------------------------------------------------

def add_practice_log(topic: str, count: int, time: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO learning_practice_log (topic, count, time) VALUES (?, ?, ?)",
            (topic, count, time),
        )


def get_practice_log() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT topic, count, time FROM learning_practice_log ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Learning Plans (Milestones)
# ---------------------------------------------------------------------------

def save_plan(id: str, topic: str, created: str, steps: list[dict]) -> None:
    """Upsert a learning plan. Replaces existing plan for same topic."""
    steps_json = json.dumps(steps, ensure_ascii=False)
    with get_connection() as conn:
        # Delete existing plan for this topic first (UNIQUE on topic)
        conn.execute("DELETE FROM learning_plans WHERE topic = ?", (topic,))
        conn.execute(
            "INSERT INTO learning_plans (id, topic, created, steps_json) "
            "VALUES (?, ?, ?, ?)",
            (id, topic, created, steps_json),
        )


def get_all_plans() -> list[dict[str, Any]]:
    """Return all learning plans."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, topic, created, steps_json FROM learning_plans ORDER BY created"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "topic": r["topic"],
            "created": r["created"],
            "steps": json.loads(r["steps_json"]),
        }
        for r in rows
    ]


def get_plan_by_topic(topic: str) -> dict[str, Any] | None:
    """Return a specific plan by topic, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, topic, created, steps_json FROM learning_plans WHERE topic = ?",
            (topic,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "topic": row["topic"],
        "created": row["created"],
        "steps": json.loads(row["steps_json"]),
    }


def update_plan_steps(topic: str, steps: list[dict]) -> None:
    """Update the steps for an existing plan."""
    steps_json = json.dumps(steps, ensure_ascii=False)
    with get_connection() as conn:
        conn.execute(
            "UPDATE learning_plans SET steps_json = ? WHERE topic = ?",
            (steps_json, topic),
        )


def clear_all_plans() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM learning_plans")
