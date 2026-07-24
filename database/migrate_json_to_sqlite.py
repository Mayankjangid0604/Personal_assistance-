"""
JSON -> SQLite Migration Script for Aisha AI Assistant.

Reads ALL existing JSON data files and safely inserts their contents
into the SQLite database.  Safe to run multiple times (idempotent --
skips records that already exist).

Usage::

    python database/migrate_json_to_sqlite.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure imports work
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
_BACKEND_DIR = _PROJECT_ROOT / "backend"

for p in (str(_PROJECT_ROOT), str(_THIS_DIR), str(_BACKEND_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Import DB (this also runs init_db() which creates tables)
from database.db import get_connection, DB_PATH

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> any:
    """Load a JSON file, returning None if missing/corrupt."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [WARN] Could not read {path.name}: {e}")
        return None


def _count_rows(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------------------------------------------------------------------------
# Migration functions
# ---------------------------------------------------------------------------

def migrate_memory(db_dir: Path) -> dict[str, int]:
    """Migrate memory.json -> conversations + user_profile tables."""
    data = _load_json(db_dir / "memory.json")
    if not data:
        return {"conversations": 0, "user_profile": 0}

    conv_count = 0
    profile_count = 0

    with get_connection() as conn:
        # Skip if already migrated
        if _count_rows(conn, "conversations") > 0:
            print("  [SKIP] conversations table already has data")
        else:
            convos = data.get("conversations", [])
            for entry in convos:
                if isinstance(entry, dict):
                    conn.execute(
                        "INSERT INTO conversations (user_input, role, response, timestamp) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            entry.get("user_input", ""),
                            entry.get("role", "assistant"),
                            entry.get("response", ""),
                            entry.get("timestamp", ""),
                        ),
                    )
                    conv_count += 1

        if _count_rows(conn, "user_profile") > 0:
            print("  [SKIP] user_profile table already has data")
        else:
            long_term = data.get("long_term", {})
            for key, value in long_term.items():
                conn.execute(
                    "INSERT OR IGNORE INTO user_profile (key, value, updated_at) "
                    "VALUES (?, ?, '')",
                    (key.lower().strip(), json.dumps(value, ensure_ascii=False)),
                )
                profile_count += 1

    return {"conversations": conv_count, "user_profile": profile_count}


def migrate_reminders(db_dir: Path) -> int:
    """Migrate reminders.json -> reminders table."""
    data = _load_json(db_dir / "reminders.json")
    if not data or not isinstance(data, list):
        return 0

    count = 0
    with get_connection() as conn:
        if _count_rows(conn, "reminders") > 0:
            print("  [SKIP] reminders table already has data")
            return 0
        for r in data:
            if isinstance(r, dict) and "id" in r:
                conn.execute(
                    "INSERT OR IGNORE INTO reminders (id, task, time, created_at, completed) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        r["id"],
                        r.get("task", ""),
                        r.get("time", ""),
                        r.get("created_at", ""),
                        1 if r.get("completed") else 0,
                    ),
                )
                count += 1
    return count


def migrate_notifications(db_dir: Path) -> int:
    """Migrate notifications.json -> notifications table."""
    data = _load_json(db_dir / "notifications.json")
    if not data or not isinstance(data, list):
        return 0

    count = 0
    with get_connection() as conn:
        if _count_rows(conn, "notifications") > 0:
            print("  [SKIP] notifications table already has data")
            return 0
        for n in data:
            if isinstance(n, dict) and "id" in n:
                conn.execute(
                    "INSERT OR IGNORE INTO notifications "
                    "(id, message, category, source, time, read) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        n["id"],
                        n.get("message", ""),
                        n.get("category", "general"),
                        n.get("source", "system"),
                        n.get("time", ""),
                        1 if n.get("read") else 0,
                    ),
                )
                count += 1
    return count


def migrate_journal(db_dir: Path) -> int:
    """Migrate journal.json -> journal_entries table."""
    data = _load_json(db_dir / "journal.json")
    if not data or not isinstance(data, list):
        return 0

    count = 0
    with get_connection() as conn:
        if _count_rows(conn, "journal_entries") > 0:
            print("  [SKIP] journal_entries table already has data")
            return 0
        for e in data:
            if isinstance(e, dict) and "id" in e:
                conn.execute(
                    "INSERT OR IGNORE INTO journal_entries "
                    "(id, date, time, summary, emotion, emotion_cause, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        e["id"],
                        e.get("date", ""),
                        e.get("time", ""),
                        e.get("summary", ""),
                        e.get("emotion", "neutral"),
                        e.get("emotion_cause"),
                        e.get("notes"),
                    ),
                )
                count += 1
    return count


def migrate_learning(db_dir: Path) -> dict[str, int]:
    """Migrate learning.json -> learning_interests + learning_plans tables."""
    data = _load_json(db_dir / "learning.json")
    if not data or not isinstance(data, dict):
        return {"interests": 0, "plans": 0, "practice": 0}

    int_count = 0
    plan_count = 0
    prac_count = 0

    with get_connection() as conn:
        # Interests
        interests = data.get("interests", {})
        if interests and _count_rows(conn, "learning_interests") == 0:
            for topic, count in interests.items():
                conn.execute(
                    "INSERT OR IGNORE INTO learning_interests (topic, count) VALUES (?, ?)",
                    (topic, count),
                )
                int_count += 1

        # Practice log
        practice = data.get("practice_log", [])
        if practice and _count_rows(conn, "learning_practice_log") == 0:
            for p in practice:
                conn.execute(
                    "INSERT INTO learning_practice_log (topic, count, time) VALUES (?, ?, ?)",
                    (p.get("topic", ""), p.get("count", 0), p.get("time", "")),
                )
                prac_count += 1

        # Milestones
        milestones = data.get("milestones", [])
        if milestones and _count_rows(conn, "learning_plans") == 0:
            for m in milestones:
                conn.execute(
                    "INSERT OR IGNORE INTO learning_plans (id, topic, created, steps_json) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        m.get("id", ""),
                        m.get("topic", ""),
                        m.get("created", ""),
                        json.dumps(m.get("steps", []), ensure_ascii=False),
                    ),
                )
                plan_count += 1

    return {"interests": int_count, "plans": plan_count, "practice": prac_count}


def migrate_power_tools(db_dir: Path) -> dict[str, int]:
    """Migrate power_tools.json -> habits, automations, routines, shortcuts, patterns."""
    data = _load_json(db_dir / "power_tools.json")
    if not data or not isinstance(data, dict):
        return {}

    counts = {}

    with get_connection() as conn:
        # Habits
        habits = data.get("habits", {})
        if habits and _count_rows(conn, "habits") == 0:
            for name, h in habits.items():
                conn.execute(
                    "INSERT OR IGNORE INTO habits "
                    "(name, streak, best_streak, total_completions, last_done, created) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        name,
                        h.get("streak", 0),
                        h.get("best_streak", 0),
                        h.get("total_completions", 0),
                        h.get("last_done"),
                        h.get("created", ""),
                    ),
                )
            counts["habits"] = len(habits)

        # Automations
        autos = data.get("automations", {})
        if autos and _count_rows(conn, "automations") == 0:
            for name, a in autos.items():
                conn.execute(
                    "INSERT OR IGNORE INTO automations (name, actions_json, created) "
                    "VALUES (?, ?, ?)",
                    (name, json.dumps(a.get("actions", [])), a.get("created", "")),
                )
            counts["automations"] = len(autos)

        # Routines
        routines = data.get("routines", {})
        if routines and _count_rows(conn, "routines") == 0:
            for name, r in routines.items():
                conn.execute(
                    "INSERT OR IGNORE INTO routines (name, steps_json, time_of_day) "
                    "VALUES (?, ?, ?)",
                    (name, json.dumps(r.get("steps", [])), r.get("time_of_day")),
                )
            counts["routines"] = len(routines)

        # Shortcuts
        shortcuts = data.get("shortcuts", {})
        if shortcuts and _count_rows(conn, "shortcuts") == 0:
            for alias, cmd in shortcuts.items():
                conn.execute(
                    "INSERT OR IGNORE INTO shortcuts (alias, command) VALUES (?, ?)",
                    (alias, cmd),
                )
            counts["shortcuts"] = len(shortcuts)

        # Patterns
        patterns = data.get("patterns", {})
        if patterns:
            peak = patterns.get("peak_hours", {})
            if peak and _count_rows(conn, "behaviour_peak_hours") == 0:
                for hour, count in peak.items():
                    conn.execute(
                        "INSERT OR IGNORE INTO behaviour_peak_hours (hour, count) VALUES (?, ?)",
                        (str(hour), count),
                    )
                counts["peak_hours"] = len(peak)

            cmds = patterns.get("common_commands", {})
            if cmds and _count_rows(conn, "behaviour_commands") == 0:
                for cmd, count in cmds.items():
                    conn.execute(
                        "INSERT OR IGNORE INTO behaviour_commands (command, count) VALUES (?, ?)",
                        (cmd, count),
                    )
                counts["commands"] = len(cmds)

            topics = patterns.get("topics_by_time", [])
            if topics and _count_rows(conn, "behaviour_topics_by_time") == 0:
                for t in topics:
                    conn.execute(
                        "INSERT INTO behaviour_topics_by_time (input, period, time) "
                        "VALUES (?, ?, ?)",
                        (t.get("input", ""), t.get("period", ""), t.get("time", "")),
                    )
                counts["topics_by_time"] = len(topics)

    return counts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_migration() -> None:
    """Execute the full JSON -> SQLite migration."""
    db_dir = _THIS_DIR

    print()
    print("=" * 65)
    print("  AISHA -- JSON -> SQLite Migration")
    print("=" * 65)
    print(f"  Database: {DB_PATH}")
    print(f"  Source  : {db_dir}")
    print()

    # Run each migration
    mem = migrate_memory(db_dir)
    print(f"  [memory.json]        {mem['conversations']} conversations, "
          f"{mem['user_profile']} profile keys")

    rem = migrate_reminders(db_dir)
    print(f"  [reminders.json]     {rem} reminders")

    notif = migrate_notifications(db_dir)
    print(f"  [notifications.json] {notif} notifications")

    jour = migrate_journal(db_dir)
    print(f"  [journal.json]       {jour} entries")

    learn = migrate_learning(db_dir)
    print(f"  [learning.json]      {learn}")

    power = migrate_power_tools(db_dir)
    print(f"  [power_tools.json]   {power}")

    # Verification
    print()
    print("  Verification:")
    with get_connection() as conn:
        tables = [
            "conversations", "user_profile", "reminders", "notifications",
            "journal_entries", "habits", "learning_interests", "learning_plans",
            "automations", "routines", "shortcuts",
            "behaviour_peak_hours", "behaviour_commands", "behaviour_topics_by_time",
        ]
        for t in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"    {t:<30} {count:>5} rows")

    print()
    print("  Migration complete!")
    print("=" * 65)


if __name__ == "__main__":
    run_migration()
