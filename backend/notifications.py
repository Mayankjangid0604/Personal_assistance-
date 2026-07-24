"""
Notification, Journaling & Daily Summary System for Aisha AI Assistant.

Three subsystems in one module:

1. **Notifications**  -- Stores and serves timestamped notifications from
   reminders, autonomous messages, and system events.

2. **Journaling**     -- Saves structured journal entries (date, emotion,
   summary, notes) to ``database/aisha.db`` (SQLite).

3. **Daily Summary**  -- Generates a text summary of today's conversations,
   emotion trend, and goals progress on demand.

Usage::

    from notifications import (
        add_notification, get_notifications, clear_notifications,
        is_journal_command, handle_journal_command,
        is_summary_command, generate_daily_summary,
    )
"""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# SQLite Repository
# ---------------------------------------------------------------------------

import sys as _sys
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

from database.repositories import notification_repo, journal_repo




# -- Public API ------------------------------------------------------------

def add_notification(
    message: str,
    category: str = "general",
    source: str = "system",
) -> dict[str, Any]:
    """
    Create and persist a new notification.

    Parameters
    ----------
    message : str
        The notification text.
    category : str
        One of ``"reminder"``, ``"emotion"``, ``"autonomous"``, ``"general"``.
    source : str
        Human-readable origin (e.g. ``"scheduler"``, ``"autonomous"``).

    Returns
    -------
    dict
        The created notification record.
    """
    notif_id = str(uuid.uuid4())[:8]
    time_str = datetime.now().isoformat(timespec="seconds")

    notification_repo.add_notification(
        notif_id, message, category, source, time_str,
    )

    notif = {
        "id": notif_id,
        "message": message,
        "category": category,
        "source": source,
        "time": time_str,
        "read": False,
    }
    return notif


def get_notifications(
    unread_only: bool = False, limit: int = 20
) -> list[dict[str, Any]]:
    """Return recent notifications (newest first)."""
    return notification_repo.get_notifications(unread_only=unread_only, limit=limit)


def get_unread_count() -> int:
    """Return the number of unread notifications."""
    return notification_repo.get_unread_count()


def mark_all_read() -> int:
    """Mark every notification as read.  Returns count marked."""
    return notification_repo.mark_all_read()


def clear_notifications() -> int:
    """Delete all notifications.  Returns count deleted."""
    return notification_repo.clear_all()




# -- Intent detection ------------------------------------------------------

_JOURNAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(save|add|write|log)\s+(this\s+)?(as\s+)?(a\s+)?journal\b", re.IGNORECASE),
    re.compile(r"\bjournal\s+(this|entry|save)\b", re.IGNORECASE),
    re.compile(r"\bmy\s+journal\b", re.IGNORECASE),
    re.compile(r"\bshow\s+journal\b", re.IGNORECASE),
    re.compile(r"\bview\s+journal\b", re.IGNORECASE),
]


def is_journal_command(user_input: str) -> bool:
    """Return True if the input is a journal-related command."""
    return any(p.search(user_input) for p in _JOURNAL_PATTERNS)


def handle_journal_command(user_input: str, memory: Any) -> str:
    """
    Process a journal-related command.

    - ``"save this as journal"`` → creates an entry from the last conversation
    - ``"show journal"`` / ``"my journal"`` → lists recent entries
    """
    lower = user_input.lower()

    # --- Show / list journal ---
    if any(kw in lower for kw in ("show journal", "view journal", "my journal")):
        return _format_journal()

    # --- Save journal entry ---
    return _save_journal_entry(memory)


def _save_journal_entry(memory: Any) -> str:
    """Build a journal entry from the latest conversation and memory state."""
    last = memory.get_last_conversation()
    emotion = memory.get_user_info("last_emotion") or "neutral"
    emotion_cause = memory.get_user_info("last_emotion_cause")

    now = datetime.now()

    # Build a summary from the last conversation
    if last:
        summary = f"User: {last.user_input} → Aisha: {last.response[:120]}"
    else:
        summary = "No recent conversation to record."

    # Build notes
    notes_parts: list[str] = []
    name = memory.get_user_info("name")
    if name:
        notes_parts.append(f"User: {name}")
    goal = memory.get_user_info("goal")
    if goal:
        notes_parts.append(f"Goal: {goal}")
    if emotion_cause:
        notes_parts.append(f"Felt {emotion} about {emotion_cause}")

    entry = {
        "id": str(uuid.uuid4())[:8],
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "summary": summary,
        "emotion": emotion,
        "emotion_cause": emotion_cause,
        "notes": " | ".join(notes_parts) if notes_parts else "",
    }

    journal_repo.add_entry(
        entry["id"], entry["date"], entry["time"], entry["summary"],
        entry["emotion"], entry["emotion_cause"], entry["notes"],
    )

    # Also create a notification
    add_notification(
        f"Journal entry saved for {now.strftime('%d %b')}",
        category="general",
        source="journal",
    )

    return (
        f"📝 Journal entry saved!\n"
        f"  Date    : {entry['date']} at {entry['time']}\n"
        f"  Emotion : {emotion}\n"
        f"  Summary : {summary[:100]}{'...' if len(summary) > 100 else ''}"
    )


def _format_journal() -> str:
    """Format recent journal entries for display."""
    all_entries = journal_repo.get_all_entries()
    if not all_entries:
        return "Your journal is empty. Say \"save this as journal\" to create an entry."

    total = journal_repo.get_entry_count()
    recent = journal_repo.get_entries(5)
    lines = [f"Your Journal ({total} total entries):\n"]
    for e in recent:
        lines.append(f"  [{e['date']}] Emotion: {e['emotion']}")
        lines.append(f"    {e['summary'][:80]}{'...' if len(e['summary']) > 80 else ''}")
        if e.get("notes"):
            lines.append(f"    Notes: {e['notes']}")
        lines.append("")

    return "\n".join(lines).rstrip()


def get_journal_entries(limit: int = 10) -> list[dict[str, Any]]:
    """Return recent journal entries (newest first)."""
    return journal_repo.get_entries(limit)


# ═══════════════════════════════════════════════════════════════════════════
#  3. DAILY SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

_SUMMARY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bsummar(y|ize|ise)\s+(my\s+)?day\b", re.IGNORECASE),
    re.compile(r"\bdaily\s+summary\b", re.IGNORECASE),
    re.compile(r"\bhow\s+was\s+my\s+day\b", re.IGNORECASE),
    re.compile(r"\btoday'?s?\s+summary\b", re.IGNORECASE),
]


def is_summary_command(user_input: str) -> bool:
    """Return True if the user is asking for a daily summary."""
    return any(p.search(user_input) for p in _SUMMARY_PATTERNS)


def generate_daily_summary(memory: Any) -> str:
    """
    Generate a text summary of today's activity.

    Includes:
    - Number of conversations
    - Emotion trend (most frequent emotion today)
    - Goal progress
    - Key topics discussed
    """
    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%d %b %Y")

    # --- Conversations ---
    conversations = memory.get_recent_conversations()
    conv_count = len(conversations)

    # --- Emotion trend ---
    today_journal = journal_repo.get_entries_by_date(today)
    emotion_counter: Counter[str] = Counter()

    # Collect emotions from memory conversations
    last_emotion = memory.get_user_info("last_emotion") or "neutral"
    emotion_counter[last_emotion] += 1

    # Also count from today's journal entries
    for entry in today_journal:
        if entry.get("emotion"):
            emotion_counter[entry["emotion"]] += 1

    if emotion_counter:
        dominant_emotion = emotion_counter.most_common(1)[0][0]
        emotion_text = f"{dominant_emotion} (detected {emotion_counter.most_common(1)[0][1]} time(s))"
    else:
        dominant_emotion = "neutral"
        emotion_text = "neutral"

    # --- Goals ---
    goal = memory.get_user_info("goal")
    goal_text = f'"{goal}"' if goal else "No goal set"

    # --- Key topics ---
    topics: list[str] = []
    for entry in conversations:
        text = entry.user_input[:50]
        topics.append(text)

    topics_text = ""
    if topics:
        shown = topics[-3:]  # last 3 topics
        topics_text = "\n".join(f"    • {t}" for t in shown)

    # --- Build summary ---
    lines = [
        f"📊 Daily Summary — {now_str}",
        f"{'─' * 40}",
        f"  Conversations : {conv_count}",
        f"  Emotion trend : {emotion_text}",
        f"  Goal          : {goal_text}",
        f"  Journal       : {len(today_journal)} entries today",
    ]

    if topics_text:
        lines.append(f"\n  Recent topics:")
        lines.append(topics_text)

    # --- Notification count ---
    unread = get_unread_count()
    if unread:
        lines.append(f"\n  🔔 {unread} unread notification(s)")

    lines.append(f"\n{'─' * 40}")
    lines.append("Keep going! Every conversation counts. 💜")

    # Save a notification for the summary itself
    add_notification(
        f"Daily summary generated for {now_str}",
        category="general",
        source="summary",
    )

    return "\n".join(lines)
