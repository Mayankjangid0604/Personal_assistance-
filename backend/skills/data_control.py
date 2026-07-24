"""
Data Control Skill — Priority 2.

Handles delete/export data commands with two-step confirmation.
Data is stored in SQLite (database/aisha.db).
"""

from __future__ import annotations

import re
from pathlib import Path

from skills.base import BaseSkill, SkillContext
from core.skill_registry import registry

import sys as _sys
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

from database.db import get_connection

_SQLITE_TABLES: list[tuple[str, str]] = [
    ("conversations",           "Conversations (short-term memory)"),
    ("user_profile",            "User profile (long-term memory)"),
    ("reminders",               "Reminders"),
    ("notifications",           "Notifications"),
    ("journal_entries",         "Journal entries"),
    ("habits",                  "Habits"),
    ("automations",             "Automations"),
    ("routines",                "Routines"),
    ("shortcuts",               "Shortcuts"),
    ("learning_interests",      "Learning interests"),
    ("learning_practice_log",   "Practice log"),
    ("learning_plans",          "Learning plans"),
    ("behaviour_peak_hours",    "Peak hours"),
    ("behaviour_commands",      "Common commands"),
    ("behaviour_topics_by_time","Topics by time"),
]

_pending_delete: bool = False

_DEL = [re.compile(p, re.I) for p in [
    r"\bdelete\s+(?:my\s+)?(?:all\s+)?data\b",
    r"\bclear\s+(?:my\s+)?(?:all\s+)?data\b",
    r"\berase\s+(?:my\s+)?(?:all\s+)?data\b",
    r"\breset\s+(?:my\s+)?(?:all\s+)?data\b",
]]
_EXPORT = [re.compile(p, re.I) for p in [
    r"\bexport\s+(?:my\s+)?data\b",
    r"\bdownload\s+(?:my\s+)?data\b",
    r"\bshow\s+(?:my\s+)?(?:all\s+)?data\b",
]]
_YES = [re.compile(p, re.I) for p in [r"^\s*yes\s*$", r"^\s*yeah\s*$", r"^\s*yep\s*$", r"^\s*confirm\s*$", r"^\s*do it\s*$"]]
_NO  = [re.compile(p, re.I) for p in [r"^\s*no\s*$", r"^\s*nah\s*$", r"^\s*nope\s*$", r"^\s*cancel\s*$", r"^\s*never\s?mind\s*$"]]


class DataControlSkill(BaseSkill):
    name = "data_control"
    priority = 2

    def can_handle(self, user_input: str, context: SkillContext) -> bool:
        global _pending_delete
        text = user_input.strip()
        if any(p.search(text) for p in _DEL): return True
        if any(p.search(text) for p in _EXPORT): return True
        if _pending_delete:
            if any(p.search(text) for p in _YES) or any(p.search(text) for p in _NO):
                return True
        return False

    def handle(self, user_input: str, context: SkillContext) -> str:
        global _pending_delete
        text = user_input.strip()

        if _pending_delete:
            _pending_delete = False
            if any(p.search(text) for p in _YES):
                return self._execute_delete(context)
            return "Data deletion cancelled. Your data is safe."

        if any(p.search(text) for p in _DEL):
            _pending_delete = True
            table_names = ", ".join(label for _, label in _SQLITE_TABLES)
            return (
                "This will permanently delete ALL your data:\n"
                f"  ({table_names})\n\n"
                "Are you sure? (yes/no)"
            )

        if any(p.search(text) for p in _EXPORT):
            return self._execute_export()

        return "I didn't understand that data command."

    def _execute_delete(self, context: SkillContext) -> str:
        """Clear all SQLite tables and reset in-memory caches."""
        cleared = []
        with get_connection() as conn:
            for table, label in _SQLITE_TABLES:
                try:
                    conn.execute(f"DELETE FROM {table}")
                    cleared.append(label)
                except Exception:
                    pass

        # Clear in-memory caches
        if context.memory:
            context.memory.clear_short_term()
            context.memory.clear_long_term()

        # Reset power_tools in-memory cache
        try:
            from power_tools import _data as pt_data
            pt_data["habits"].clear()
            pt_data["automations"].clear()
            pt_data["routines"].clear()
            pt_data["shortcuts"].clear()
            pt_data["patterns"]["peak_hours"].clear()
            pt_data["patterns"]["common_commands"].clear()
            pt_data["patterns"]["topics_by_time"].clear()
        except Exception:
            pass

        # Reset learning in-memory cache
        try:
            from learning import _data as learn_data
            learn_data["interests"].clear()
            learn_data["practice_log"].clear()
            learn_data["milestones"].clear()
        except Exception:
            pass

        if cleared:
            return (
                f"All your data has been cleared.\n"
                f"  Cleared: {len(cleared)} data categories\n"
                "You're starting fresh. Your privacy matters."
            )
        return "No data found to clear."

    def _execute_export(self) -> str:
        """Build a data export summary from SQLite tables."""
        sections = []
        total_rows = 0

        with get_connection() as conn:
            for table, label in _SQLITE_TABLES:
                try:
                    row = conn.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()
                    count = row[0] if row else 0
                    total_rows += count
                    sections.append(
                        f"  {label:<32} {count:>5} rows"
                    )
                except Exception:
                    sections.append(f"  {label:<32} [error]")

        return (
            f"Your Data Export ({total_rows:,} total rows):\n"
            + "\n".join(sections)
        )


registry.register(DataControlSkill())
