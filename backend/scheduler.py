"""
Scheduling & Reminder System for Aisha AI Assistant.

Allows users to set, list, and delete reminders using natural language.
Reminders are persisted to ``database/aisha.db`` (SQLite) and checked by a
background thread that fires alerts when a reminder's time arrives.

Supported input patterns::

    "remind me to study AI at 17:00"
    "remind me to call mom in 30 minutes"
    "remind me to exercise tomorrow at 8:00"
    "set a reminder to submit assignment at 14:30"
    "show reminders"
    "list reminders"
    "delete reminder 1"
    "remove reminder 2"
    "clear all reminders"

Usage::

    from scheduler import (
        handle_reminder_input,
        is_reminder_command,
        get_triggered_reminders,
        start_reminder_checker,
    )
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# SQLite Repository
# ---------------------------------------------------------------------------

import sys as _sys
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

from database.repositories import reminder_repo

_lock = threading.Lock()


# ---------------------------------------------------------------------------
# CRUD Operations
# ---------------------------------------------------------------------------

def add_reminder(task: str, trigger_time: datetime) -> dict[str, Any]:
    """
    Create a new reminder and persist it.

    Parameters
    ----------
    task : str
        What the user wants to be reminded about.
    trigger_time : datetime
        When the reminder should fire.

    Returns
    -------
    dict
        The created reminder record.
    """
    reminder = {
        "id": str(uuid.uuid4())[:8],
        "task": task,
        "time": trigger_time.isoformat(timespec="seconds"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "completed": False,
    }

    with _lock:
        reminder_repo.add_reminder(
            reminder["id"], reminder["task"],
            reminder["time"], reminder["created_at"],
        )

    return reminder


def list_reminders() -> list[dict[str, Any]]:
    """Return all pending (not completed) reminders, sorted by time."""
    with _lock:
        pending = reminder_repo.list_pending()
    return pending


def delete_reminder(index: int) -> dict[str, Any] | None:
    """
    Delete a pending reminder by its display index (1-based).

    Returns the deleted reminder, or ``None`` if index is out of range.
    """
    pending = list_reminders()
    if index < 1 or index > len(pending):
        return None

    target = pending[index - 1]

    with _lock:
        reminder_repo.delete_by_id(target["id"])

    return target


def clear_all_reminders() -> int:
    """Delete all reminders.  Returns the count removed."""
    with _lock:
        count = reminder_repo.clear_all()
    return count


# ---------------------------------------------------------------------------
# Time Parsing from Natural Language
# ---------------------------------------------------------------------------

def _parse_time(user_input: str) -> datetime | None:
    """
    Extract a trigger time from user input.

    Supported patterns:
        "at 17:00"          → today at 17:00 (or tomorrow if already passed)
        "at 5 pm"           → today at 17:00
        "in 30 minutes"     → now + 30 min
        "in 2 hours"        → now + 2 hours
        "tomorrow at 9:00"  → tomorrow at 09:00
        "tomorrow at 9 am"  → tomorrow at 09:00

    Returns ``None`` if no pattern matches.
    """
    text = user_input.lower().strip()
    now = datetime.now()

    # --- Pattern: "in N minutes" / "in N hours" ---
    m = re.search(r"\bin\s+(\d+)\s*(minutes?|mins?|hours?|hrs?)\b", text)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("h"):
            return now + timedelta(hours=amount)
        return now + timedelta(minutes=amount)

    # --- Pattern: "tomorrow at HH:MM" or "tomorrow at H am/pm" ---
    m = re.search(
        r"\btomorrow\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text
    )
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        period = m.group(3)
        if period == "pm" and hour < 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # --- Pattern: "at HH:MM" or "at H am/pm" ---
    m = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        period = m.group(3)
        if period == "pm" and hour < 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # If time already passed today, schedule for tomorrow
        if target <= now:
            target += timedelta(days=1)
        return target

    return None


def _parse_task(user_input: str) -> str:
    """
    Extract the task description from a reminder command.

    Strips out the "remind me to" prefix, time expressions, and common
    filler words to isolate just the task.
    """
    text = user_input.strip()

    # Remove the "remind me to" / "set reminder to" prefix
    text = re.sub(
        r"^(remind\s+me\s+to|set\s+(a\s+)?reminder\s+(to|for))\s*",
        "", text, flags=re.IGNORECASE,
    )

    # Remove time expressions
    text = re.sub(r"\b(at\s+\d{1,2}(:\d{2})?\s*(am|pm)?)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(in\s+\d+\s*(minutes?|mins?|hours?|hrs?))\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\btomorrow\b", "", text, flags=re.IGNORECASE)

    # Clean whitespace
    text = re.sub(r"\s+", " ", text).strip().rstrip(".,!?")

    return text or "something"


# ---------------------------------------------------------------------------
# Intent Detection
# ---------------------------------------------------------------------------

# Patterns that indicate a reminder-related command
_REMINDER_ADD_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bremind\s+me\s+to\b", re.IGNORECASE),
    re.compile(r"\bset\s+(a\s+)?reminder\b", re.IGNORECASE),
]

_REMINDER_LIST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(show|list|view|my)\s+reminders?\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(are\s+)?my\s+reminders?\b", re.IGNORECASE),
]

_REMINDER_DELETE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(delete|remove|cancel)\s+reminder\s*(\d+)?\b", re.IGNORECASE),
    re.compile(r"\bclear\s+(all\s+)?reminders?\b", re.IGNORECASE),
]


def is_reminder_command(user_input: str) -> bool:
    """Return True if the input is any reminder-related command."""
    text = user_input.strip()
    for patterns in (_REMINDER_ADD_PATTERNS, _REMINDER_LIST_PATTERNS, _REMINDER_DELETE_PATTERNS):
        if any(p.search(text) for p in patterns):
            return True
    return False


def handle_reminder_input(user_input: str) -> str:
    """
    Process a reminder-related command and return a response string.

    Handles:
        - Adding reminders
        - Listing reminders
        - Deleting/clearing reminders

    Parameters
    ----------
    user_input : str
        The user's raw text (already confirmed as a reminder command).

    Returns
    -------
    str
        A confirmation or information response.
    """
    text = user_input.strip()

    # --- List reminders ---
    if any(p.search(text) for p in _REMINDER_LIST_PATTERNS):
        return _format_reminder_list()

    # --- Delete / clear ---
    for p in _REMINDER_DELETE_PATTERNS:
        m = p.search(text)
        if m:
            # "clear all reminders"
            if "clear" in text.lower():
                count = clear_all_reminders()
                return f"Cleared {count} reminder{'s' if count != 1 else ''}."

            # "delete reminder 2"
            groups = m.groups()
            idx_str = groups[-1] if groups else None
            if idx_str and idx_str.isdigit():
                deleted = delete_reminder(int(idx_str))
                if deleted:
                    return f"Deleted reminder: \"{deleted['task']}\""
                return f"No reminder found at position {idx_str}."

            # "delete reminder" (no number) -- show list so user can pick
            return "Which reminder? " + _format_reminder_list()

    # --- Add reminder ---
    if any(p.search(text) for p in _REMINDER_ADD_PATTERNS):
        trigger_time = _parse_time(text)
        if not trigger_time:
            return ("I couldn't understand the time. Try:\n"
                    "  • \"remind me to study at 17:00\"\n"
                    "  • \"remind me to call in 30 minutes\"\n"
                    "  • \"remind me to exercise tomorrow at 9 am\"")

        task = _parse_task(text)
        reminder = add_reminder(task, trigger_time)
        time_str = trigger_time.strftime("%I:%M %p, %d %b")

        return f"Got it! I'll remind you to \"{task}\" at {time_str}."

    return "I'm not sure what you mean. Try: \"remind me to study at 5 pm\""


def _format_reminder_list() -> str:
    """Build a formatted string of all pending reminders."""
    pending = list_reminders()
    if not pending:
        return "You have no pending reminders."

    lines = [f"You have {len(pending)} reminder{'s' if len(pending) > 1 else ''}:\n"]
    for i, r in enumerate(pending, 1):
        t = datetime.fromisoformat(r["time"]).strftime("%I:%M %p, %d %b")
        lines.append(f"  {i}. \"{r['task']}\" — {t}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Background Checker
# ---------------------------------------------------------------------------

_checker_stop = threading.Event()
_reminder_callback: Callable[[str], None] | None = None


def get_triggered_reminders() -> list[dict[str, Any]]:
    """
    Check for reminders whose time has arrived.

    Marks triggered reminders as completed and saves to disk.
    Returns the list of newly triggered reminders.
    """
    now = datetime.now()
    now_iso = now.isoformat(timespec="seconds")
    triggered = []

    with _lock:
        due = reminder_repo.get_due_reminders(now_iso)
        for r in due:
            reminder_repo.mark_completed(r["id"])
            triggered.append(r)

    return triggered


def _checker_loop(on_trigger: Callable[[str], None] | None = None):
    """
    Background loop that checks reminders every 5 seconds.

    When a reminder fires, prints the alert and optionally calls
    ``on_trigger`` (e.g. to speak the message in voice mode).
    """
    while not _checker_stop.is_set():
        try:
            triggered = get_triggered_reminders()
            for r in triggered:
                msg = f"⏰ Reminder — {r['task']}"
                print(f"\n  Aisha : {msg}")
                print()
                if on_trigger:
                    on_trigger(msg)
        except Exception:
            pass  # never crash the background thread

        _checker_stop.wait(5)


def start_reminder_checker(on_trigger: Callable[[str], None] | None = None):
    """
    Start the reminder checker as a daemon thread.

    Parameters
    ----------
    on_trigger : callable, optional
        Function called with the reminder message when one fires.
        Pass ``speak`` for voice mode.
    """
    t = threading.Thread(
        target=_checker_loop,
        args=(on_trigger,),
        daemon=True,
    )
    t.start()
    return t


def stop_reminder_checker():
    """Signal the checker thread to stop."""
    _checker_stop.set()
