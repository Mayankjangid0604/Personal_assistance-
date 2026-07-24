"""
Habit Repository -- SQLite backend for the habit tracking system.

Also covers automations, routines, shortcuts, and behaviour patterns
from power_tools.py.
"""

from __future__ import annotations

import json
from typing import Any

from database.db import get_connection


# ---------------------------------------------------------------------------
# Habits
# ---------------------------------------------------------------------------

def save_habit(name: str, streak: int, best_streak: int,
               total_completions: int, last_done: str | None, created: str) -> None:
    """Upsert a habit."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO habits (name, streak, best_streak, total_completions, last_done, created) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET "
            "streak=excluded.streak, best_streak=excluded.best_streak, "
            "total_completions=excluded.total_completions, last_done=excluded.last_done",
            (name, streak, best_streak, total_completions, last_done, created),
        )


def get_all_habits() -> dict[str, dict[str, Any]]:
    """Return all habits as {name: {habit_data}}."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM habits ORDER BY created").fetchall()
    return {
        r["name"]: {
            "name": r["name"],
            "streak": r["streak"],
            "best_streak": r["best_streak"],
            "total_completions": r["total_completions"],
            "last_done": r["last_done"],
            "created": r["created"],
        }
        for r in rows
    }


def delete_habit(name: str) -> bool:
    """Delete a habit. Returns True if it existed."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM habits WHERE name = ?", (name,))
    return cur.rowcount > 0


def clear_all_habits() -> None:
    """Delete all habits."""
    with get_connection() as conn:
        conn.execute("DELETE FROM habits")


# ---------------------------------------------------------------------------
# Automations
# ---------------------------------------------------------------------------

def save_automation(name: str, actions: list[str], created: str) -> None:
    """Upsert an automation."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO automations (name, actions_json, created) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET actions_json=excluded.actions_json",
            (name, json.dumps(actions), created),
        )


def get_all_automations() -> dict[str, dict[str, Any]]:
    """Return all automations as {name: {actions, created}}."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM automations").fetchall()
    return {
        r["name"]: {
            "actions": json.loads(r["actions_json"]),
            "created": r["created"],
        }
        for r in rows
    }


def delete_automation(name: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM automations WHERE name = ?", (name,))
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Routines
# ---------------------------------------------------------------------------

def save_routine(name: str, steps: list[str], time_of_day: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO routines (name, steps_json, time_of_day) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET steps_json=excluded.steps_json, "
            "time_of_day=excluded.time_of_day",
            (name, json.dumps(steps), time_of_day),
        )


def get_all_routines() -> dict[str, dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM routines").fetchall()
    return {
        r["name"]: {
            "steps": json.loads(r["steps_json"]),
            "time_of_day": r["time_of_day"],
        }
        for r in rows
    }


def delete_routine(name: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM routines WHERE name = ?", (name,))
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Shortcuts
# ---------------------------------------------------------------------------

def save_shortcut(alias: str, command: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO shortcuts (alias, command) VALUES (?, ?) "
            "ON CONFLICT(alias) DO UPDATE SET command=excluded.command",
            (alias, command),
        )


def get_all_shortcuts() -> dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM shortcuts").fetchall()
    return {r["alias"]: r["command"] for r in rows}


def delete_shortcut(alias: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM shortcuts WHERE alias = ?", (alias,))
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Behaviour Patterns
# ---------------------------------------------------------------------------

def save_peak_hour(hour: str, count: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO behaviour_peak_hours (hour, count) VALUES (?, ?) "
            "ON CONFLICT(hour) DO UPDATE SET count=excluded.count",
            (hour, count),
        )


def get_peak_hours() -> dict[str, int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM behaviour_peak_hours").fetchall()
    return {r["hour"]: r["count"] for r in rows}


def save_command_count(command: str, count: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO behaviour_commands (command, count) VALUES (?, ?) "
            "ON CONFLICT(command) DO UPDATE SET count=excluded.count",
            (command, count),
        )


def get_command_counts() -> dict[str, int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM behaviour_commands").fetchall()
    return {r["command"]: r["count"] for r in rows}


def add_topic_by_time(input_text: str, period: str, time: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO behaviour_topics_by_time (input, period, time) VALUES (?, ?, ?)",
            (input_text, period, time),
        )


def get_topics_by_time(limit: int = 50) -> list[dict[str, str]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT input, period, time FROM behaviour_topics_by_time "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]
