"""
Power Tools for Aisha AI Assistant.

Six subsystems that upgrade Aisha into a full productivity companion:

1. **Automation Workflows**  -- "When I say X, do Y" multi-step macros.
2. **Habit Tracking**        -- Daily habits with streak counters.
3. **Routine Builder**       -- Named morning/evening/custom routines.
4. **Voice Shortcuts**       -- Single-phrase aliases for complex commands.
5. **Advanced Context Memory** -- Exposes last 10-20 conversations to LLM.
6. **Behaviour Patterns**    -- Learns user patterns from history.

Persistent storage: ``database/aisha.db`` (SQLite via habit_repo)

Supported commands::

    # Automations
    "when I say start work, open chrome and open vscode"
    "run start work"
    "show automations"
    "delete automation start work"

    # Habits
    "add habit drink water"
    "complete habit drink water"
    "show habits"

    # Routines
    "create morning routine: meditate, exercise, shower"
    "show routines"
    "run morning routine"

    # Shortcuts
    "shortcut: focus mode = open vscode and set timer 25 minutes"
    "run focus mode"
    "show shortcuts"

    # Patterns
    "show my patterns"
"""

from __future__ import annotations

import random
import re
import uuid
from collections import Counter
from datetime import datetime, date
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# SQLite Repository
# ---------------------------------------------------------------------------

import sys as _sys
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

from database.repositories import habit_repo

# In-memory cache (kept in sync with SQLite on every write)
_data: dict[str, Any] = {
    "automations": {},      # name -> {actions: [...], created: ...}
    "habits": {},           # name -> {streak: N, last_done: date_str, ...}
    "routines": {},         # name -> {steps: [...], time_of_day: ...}
    "shortcuts": {},        # alias -> expanded_command
    "patterns": {           # auto-learned user patterns
        "peak_hours": {},   # hour -> message_count
        "common_commands": {},
        "topics_by_time": [],
    },
}


def _load() -> None:
    """Load data from SQLite into in-memory cache."""
    try:
        _data["habits"] = habit_repo.get_all_habits()
        _data["automations"] = habit_repo.get_all_automations()
        _data["routines"] = habit_repo.get_all_routines()
        _data["shortcuts"] = habit_repo.get_all_shortcuts()
        _data["patterns"]["peak_hours"] = habit_repo.get_peak_hours()
        _data["patterns"]["common_commands"] = habit_repo.get_command_counts()

        # Convert topics_by_time list from repo
        topics_raw = habit_repo.get_topics_by_time(50)
        _data["patterns"]["topics_by_time"] = topics_raw

        print(f"  [PowerTools] Loaded from SQLite "
              f"({len(_data['habits'])} habits, "
              f"{len(_data['automations'])} automations, "
              f"{len(_data['routines'])} routines, "
              f"{len(_data['shortcuts'])} shortcuts)")
    except Exception as e:
        print(f"  [PowerTools] DB load failed ({e}), starting with empty data.")


_load()


# ═══════════════════════════════════════════════════════════════════════════
#  1. AUTOMATION WORKFLOWS
# ═══════════════════════════════════════════════════════════════════════════

def _add_automation(name: str, actions: list[str]) -> str:
    created = datetime.now().isoformat(timespec="seconds")
    _data["automations"][name.lower()] = {
        "actions": actions,
        "created": created,
    }
    habit_repo.save_automation(name.lower(), actions, created)
    action_list = "\n".join(f"    {i}. {a}" for i, a in enumerate(actions, 1))
    return (
        f"Automation \"{name}\" saved with {len(actions)} actions:\n"
        f"{action_list}\n"
        f"Say \"run {name}\" to execute it."
    )


def _run_automation(name: str) -> str:
    key = name.lower()
    auto = _data["automations"].get(key)
    if not auto:
        return f"No automation called \"{name}\". Say \"show automations\" to see all."

    # We return a list of task commands to be processed by the brain
    results: list[str] = []
    for action in auto["actions"]:
        results.append(f"  -> {action}")

    return (
        f"Running automation \"{name}\":\n"
        + "\n".join(results) + "\n"
        f"({len(auto['actions'])} actions queued)"
    )


def _list_automations() -> str:
    autos = _data["automations"]
    if not autos:
        return "No automations yet. Try: \"when I say start work, open chrome and open vscode\""

    lines = [f"Your Automations ({len(autos)}):\n"]
    for name, info in autos.items():
        count = len(info["actions"])
        lines.append(f"  \"{name}\" -- {count} action{'s' if count != 1 else ''}")

    lines.append("\nSay \"run [name]\" to execute one.")
    return "\n".join(lines)


def _delete_automation(name: str) -> str:
    key = name.lower()
    if key in _data["automations"]:
        del _data["automations"][key]
        habit_repo.delete_automation(key)
        return f"Automation \"{name}\" deleted."
    return f"No automation called \"{name}\"."


# ═══════════════════════════════════════════════════════════════════════════
#  2. HABIT TRACKING
# ═══════════════════════════════════════════════════════════════════════════

def _add_habit(name: str) -> str:
    key = name.lower().strip()
    if key in _data["habits"]:
        return f"Habit \"{name}\" already exists."

    created = datetime.now().isoformat(timespec="seconds")
    _data["habits"][key] = {
        "name": name.strip(),
        "streak": 0,
        "best_streak": 0,
        "total_completions": 0,
        "last_done": None,
        "created": created,
    }
    habit_repo.save_habit(key, 0, 0, 0, None, created)
    return f"Habit \"{name}\" added! Say \"complete habit {name}\" when you do it."


def _complete_habit(name: str) -> str:
    key = name.lower().strip()
    habit = _data["habits"].get(key)
    if not habit:
        return f"No habit called \"{name}\". Say \"add habit {name}\" first."

    today = date.today().isoformat()
    if habit["last_done"] == today:
        return f"You already completed \"{habit['name']}\" today! Great job!"

    yesterday = date.today().toordinal() - 1
    last = habit["last_done"]

    # Check if streak continues
    if last:
        try:
            last_ord = date.fromisoformat(last).toordinal()
            if last_ord == yesterday:
                habit["streak"] += 1
            else:
                habit["streak"] = 1
        except ValueError:
            habit["streak"] = 1
    else:
        habit["streak"] = 1

    habit["last_done"] = today
    habit["total_completions"] += 1
    habit["best_streak"] = max(habit["best_streak"], habit["streak"])
    habit_repo.save_habit(
        key, habit["streak"], habit["best_streak"],
        habit["total_completions"], today, habit["created"],
    )

    streak_msg = ""
    if habit["streak"] >= 7:
        streak_msg = " You're on fire!"
    elif habit["streak"] >= 3:
        streak_msg = " Keep it up!"

    return (
        f"\"{habit['name']}\" completed! "
        f"Streak: {habit['streak']} day{'s' if habit['streak'] != 1 else ''}.{streak_msg}"
    )


def _show_habits() -> str:
    habits = _data["habits"]
    if not habits:
        return "No habits yet. Say \"add habit drink water\" to start tracking."

    today = date.today().isoformat()
    lines = [f"Your Habits ({len(habits)}):\n"]

    for key, h in habits.items():
        done = "done" if h["last_done"] == today else "    "
        streak_bar = "🔥" * min(h["streak"], 7) if h["streak"] > 0 else "---"
        lines.append(
            f"  [{done}] {h['name']:<20} "
            f"Streak: {h['streak']:>2}d  "
            f"Best: {h['best_streak']:>2}d  "
            f"{streak_bar}"
        )

    lines.append("\nSay \"complete habit [name]\" to mark one done.")
    return "\n".join(lines)


def _delete_habit(name: str) -> str:
    key = name.lower().strip()
    if key in _data["habits"]:
        del _data["habits"][key]
        habit_repo.delete_habit(key)
        return f"Habit \"{name}\" deleted."
    return f"No habit called \"{name}\"."


# ═══════════════════════════════════════════════════════════════════════════
#  3. ROUTINE BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def _create_routine(name: str, steps: list[str]) -> str:
    key = name.lower().strip()
    _data["routines"][key] = {
        "name": name.strip(),
        "steps": steps,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    habit_repo.save_routine(key, steps)

    step_list = "\n".join(f"    {i}. {s}" for i, s in enumerate(steps, 1))
    return (
        f"Routine \"{name}\" saved with {len(steps)} steps:\n"
        f"{step_list}\n"
        f"Say \"run {name} routine\" to start it."
    )


def _run_routine(name: str) -> str:
    key = name.lower().strip()
    routine = _data["routines"].get(key)
    if not routine:
        return f"No routine called \"{name}\". Say \"show routines\" to see all."

    lines = [f"Starting \"{routine['name']}\" routine:\n"]
    for i, step in enumerate(routine["steps"], 1):
        lines.append(f"  [ ] {i}. {step}")

    lines.append("\nCheck off each step as you go. You've got this!")
    return "\n".join(lines)


def _show_routines() -> str:
    routines = _data["routines"]
    if not routines:
        return (
            "No routines yet. Try:\n"
            "  \"create morning routine: meditate, exercise, shower\""
        )

    lines = [f"Your Routines ({len(routines)}):\n"]
    for key, r in routines.items():
        lines.append(f"  {r['name']:<20} {len(r['steps'])} steps")

    lines.append("\nSay \"run [name] routine\" to start one.")
    return "\n".join(lines)


def _delete_routine(name: str) -> str:
    key = name.lower().strip()
    if key in _data["routines"]:
        del _data["routines"][key]
        habit_repo.delete_routine(key)
        return f"Routine \"{name}\" deleted."
    return f"No routine called \"{name}\"."


# ═══════════════════════════════════════════════════════════════════════════
#  4. VOICE SHORTCUTS
# ═══════════════════════════════════════════════════════════════════════════

def _add_shortcut(alias: str, command: str) -> str:
    key = alias.lower().strip()
    _data["shortcuts"][key] = command.strip()
    habit_repo.save_shortcut(key, command.strip())
    return (
        f"Shortcut saved: \"{alias}\" = \"{command}\"\n"
        f"Say \"run {alias}\" to use it."
    )


def _run_shortcut(alias: str) -> str | None:
    """Return the expanded command, or None if no shortcut exists."""
    key = alias.lower().strip()
    return _data["shortcuts"].get(key)


def _show_shortcuts() -> str:
    shortcuts = _data["shortcuts"]
    if not shortcuts:
        return (
            "No shortcuts yet. Try:\n"
            "  \"shortcut: focus mode = open vscode and set timer 25 minutes\""
        )

    lines = [f"Your Shortcuts ({len(shortcuts)}):\n"]
    for alias, cmd in shortcuts.items():
        lines.append(f"  \"{alias}\" -> \"{cmd}\"")

    lines.append("\nSay \"run [name]\" to use one.")
    return "\n".join(lines)


def _delete_shortcut(alias: str) -> str:
    key = alias.lower().strip()
    if key in _data["shortcuts"]:
        del _data["shortcuts"][key]
        habit_repo.delete_shortcut(key)
        return f"Shortcut \"{alias}\" deleted."
    return f"No shortcut called \"{alias}\"."


# ═══════════════════════════════════════════════════════════════════════════
#  5. ADVANCED CONTEXT MEMORY
# ═══════════════════════════════════════════════════════════════════════════

def get_extended_context(memory: Any, limit: int = 10) -> list[dict[str, str]]:
    """
    Return the last *limit* conversations for richer LLM context.
    Default 10 (upgraded from 3).
    """
    recent = memory.get_recent_conversations()
    return [
        {"user": e.user_input, "aisha": e.response}
        for e in recent[-limit:]
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  6. BEHAVIOUR PATTERNS (auto-learned)
# ═══════════════════════════════════════════════════════════════════════════

def record_behaviour(user_input: str) -> None:
    """
    Called on every message to learn usage patterns.
    Tracks: peak hours, common commands, and topics by time.
    """
    now = datetime.now()
    hour = str(now.hour)

    # Track peak hours
    peaks = _data["patterns"].setdefault("peak_hours", {})
    peaks[hour] = peaks.get(hour, 0) + 1

    # Track common short commands (< 6 words)
    words = user_input.strip().split()
    if len(words) <= 5:
        cmds = _data["patterns"].setdefault("common_commands", {})
        key = user_input.strip().lower()
        cmds[key] = cmds.get(key, 0) + 1
        # Keep only top 30
        if len(cmds) > 30:
            top = dict(Counter(cmds).most_common(30))
            _data["patterns"]["common_commands"] = top

    # Track topics by time of day
    period = "morning" if 5 <= now.hour < 12 else (
        "afternoon" if 12 <= now.hour < 17 else (
        "evening" if 17 <= now.hour < 21 else "night"))

    topics_log = _data["patterns"].setdefault("topics_by_time", [])
    topics_log.append({
        "input": user_input[:80],
        "period": period,
        "time": now.isoformat(timespec="seconds"),
    })
    # Keep last 50
    if len(topics_log) > 50:
        _data["patterns"]["topics_by_time"] = topics_log[-50:]

    # Persist to SQLite
    habit_repo.save_peak_hour(hour, peaks[hour])
    if len(words) <= 5:
        cmd_key = user_input.strip().lower()
        habit_repo.save_command_count(cmd_key, cmds[cmd_key])
    habit_repo.add_topic_by_time(user_input[:80], period,
                                  now.isoformat(timespec="seconds"))


def get_user_patterns() -> dict[str, Any]:
    """Return the learned behaviour patterns."""
    return _data.get("patterns", {})


def _format_patterns() -> str:
    """Format user patterns for display."""
    patterns = _data.get("patterns", {})

    lines = ["Your Usage Patterns:\n"]

    # Peak hours
    peaks = patterns.get("peak_hours", {})
    if peaks:
        top_hours = Counter(peaks).most_common(3)
        peak_strs = []
        for h, c in top_hours:
            h_int = int(h)
            ampm = f"{h_int % 12 or 12}{'am' if h_int < 12 else 'pm'}"
            peak_strs.append(f"{ampm} ({c} msgs)")
        lines.append(f"  Most active: {', '.join(peak_strs)}")

    # Common commands
    cmds = patterns.get("common_commands", {})
    if cmds:
        top_cmds = Counter(cmds).most_common(5)
        lines.append(f"\n  Frequent commands:")
        for cmd, count in top_cmds:
            lines.append(f"    \"{cmd}\" ({count}x)")

    # Time-of-day preference
    topics = patterns.get("topics_by_time", [])
    if topics:
        period_counts = Counter(t["period"] for t in topics)
        fav = period_counts.most_common(1)[0]
        lines.append(f"\n  You're most active in the {fav[0]}.")

    if len(lines) == 1:
        return "No patterns learned yet. Keep chatting and I'll learn your habits!"

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  INTENT DETECTION & ROUTING
# ═══════════════════════════════════════════════════════════════════════════

# --- Automation patterns ---
_AUTO_CREATE = re.compile(
    r"\bwhen\s+i\s+say\s+['\"]?(.+?)['\"]?\s*,\s*(.+)", re.IGNORECASE
)
_AUTO_RUN = re.compile(r"\brun\s+(.+)", re.IGNORECASE)
_AUTO_SHOW = re.compile(r"\b(?:show|list|view)\s+automations?\b", re.IGNORECASE)
_AUTO_DEL = re.compile(r"\bdelete\s+automation\s+(.+)", re.IGNORECASE)

# --- Habit patterns ---
_HABIT_ADD = re.compile(r"\badd\s+habit\s+(.+)", re.IGNORECASE)
_HABIT_DONE = re.compile(r"\bcomplete\s+habit\s+(.+)", re.IGNORECASE)
_HABIT_SHOW = re.compile(r"\b(?:show|list|view|my)\s+habits?\b", re.IGNORECASE)
_HABIT_DEL = re.compile(r"\b(?:delete|remove)\s+habit\s+(.+)", re.IGNORECASE)

# --- Routine patterns ---
_ROUTINE_CREATE = re.compile(
    r"\bcreate\s+(.+?)\s+routine\s*:\s*(.+)", re.IGNORECASE
)
_ROUTINE_RUN = re.compile(r"\brun\s+(.+?)\s+routine\b", re.IGNORECASE)
_ROUTINE_SHOW = re.compile(r"\b(?:show|list|view|my)\s+routines?\b", re.IGNORECASE)
_ROUTINE_DEL = re.compile(r"\bdelete\s+routine\s+(.+)", re.IGNORECASE)

# --- Shortcut patterns ---
_SHORTCUT_ADD = re.compile(
    r"\bshortcut\s*:\s*(.+?)\s*=\s*(.+)", re.IGNORECASE
)
_SHORTCUT_SHOW = re.compile(r"\b(?:show|list|view|my)\s+shortcuts?\b", re.IGNORECASE)
_SHORTCUT_DEL = re.compile(r"\bdelete\s+shortcut\s+(.+)", re.IGNORECASE)

# --- Pattern display ---
_PATTERN_SHOW = re.compile(
    r"\b(?:show|view|my)\s+(?:usage\s+)?patterns?\b", re.IGNORECASE
)


def is_power_command(user_input: str) -> bool:
    """Return True if the input matches any power tools command."""
    text = user_input.strip()
    patterns = [
        _AUTO_CREATE, _AUTO_SHOW, _AUTO_DEL,
        _HABIT_ADD, _HABIT_DONE, _HABIT_SHOW, _HABIT_DEL,
        _ROUTINE_CREATE, _ROUTINE_RUN, _ROUTINE_SHOW, _ROUTINE_DEL,
        _SHORTCUT_ADD, _SHORTCUT_SHOW, _SHORTCUT_DEL,
        _PATTERN_SHOW,
    ]
    if any(p.search(text) for p in patterns):
        return True

    # Special: "run X" matches if X is a known automation/shortcut/routine
    m = _AUTO_RUN.search(text)
    if m:
        target = m.group(1).strip().lower().rstrip(".,!?")
        # Check if it's a routine (strip "routine" suffix)
        rname = re.sub(r"\s+routine$", "", target)
        if (target in _data["automations"] or
            target in _data["shortcuts"] or
            rname in _data["routines"]):
            return True

    return False


def handle_power_command(user_input: str) -> str:
    """Route a power tools command to the right handler."""
    text = user_input.strip()

    # --- Automation: create ---
    m = _AUTO_CREATE.search(text)
    if m:
        name = m.group(1).strip().rstrip(".,!?")
        action_str = m.group(2).strip()
        actions = [a.strip() for a in re.split(r"\s+and\s+", action_str) if a.strip()]
        return _add_automation(name, actions)

    # --- Show automations ---
    if _AUTO_SHOW.search(text):
        return _list_automations()

    # --- Delete automation ---
    m = _AUTO_DEL.search(text)
    if m:
        return _delete_automation(m.group(1).strip().rstrip(".,!?"))

    # --- Habit: add ---
    m = _HABIT_ADD.search(text)
    if m:
        return _add_habit(m.group(1).strip().rstrip(".,!?"))

    # --- Habit: complete ---
    m = _HABIT_DONE.search(text)
    if m:
        return _complete_habit(m.group(1).strip().rstrip(".,!?"))

    # --- Show habits ---
    if _HABIT_SHOW.search(text):
        return _show_habits()

    # --- Delete habit ---
    m = _HABIT_DEL.search(text)
    if m:
        return _delete_habit(m.group(1).strip().rstrip(".,!?"))

    # --- Routine: create ---
    m = _ROUTINE_CREATE.search(text)
    if m:
        name = m.group(1).strip()
        steps_str = m.group(2).strip()
        steps = [s.strip() for s in re.split(r"\s*,\s*", steps_str) if s.strip()]
        return _create_routine(name, steps)

    # --- Routine: run ---
    m = _ROUTINE_RUN.search(text)
    if m:
        return _run_routine(m.group(1).strip().rstrip(".,!?"))

    # --- Show routines ---
    if _ROUTINE_SHOW.search(text):
        return _show_routines()

    # --- Delete routine ---
    m = _ROUTINE_DEL.search(text)
    if m:
        return _delete_routine(m.group(1).strip().rstrip(".,!?"))

    # --- Shortcut: create ---
    m = _SHORTCUT_ADD.search(text)
    if m:
        return _add_shortcut(m.group(1).strip(), m.group(2).strip())

    # --- Show shortcuts ---
    if _SHORTCUT_SHOW.search(text):
        return _show_shortcuts()

    # --- Delete shortcut ---
    m = _SHORTCUT_DEL.search(text)
    if m:
        return _delete_shortcut(m.group(1).strip().rstrip(".,!?"))

    # --- Show patterns ---
    if _PATTERN_SHOW.search(text):
        return _format_patterns()

    # --- Run (automation / shortcut / routine) ---
    m = _AUTO_RUN.search(text)
    if m:
        target = m.group(1).strip().lower().rstrip(".,!?")
        if target in _data["automations"]:
            return _run_automation(target)
        if target in _data["shortcuts"]:
            expanded = _data["shortcuts"][target]
            return f"Running shortcut \"{target}\":\n  -> {expanded}"
        rname = re.sub(r"\s+routine$", "", target)
        if rname in _data["routines"]:
            return _run_routine(rname)
        return f"No automation, shortcut, or routine called \"{target}\"."

    return "I didn't understand that. Try \"show automations\" or \"add habit drink water\"."
