"""
Autonomous Behavior System for Aisha AI Assistant.

Adds proactive, initiative-taking behavior so Aisha feels like a
companion rather than a passive Q&A bot.

Triggers:
    1. **Idle check**      -- nudge the user after a period of silence.
    2. **Emotion follow-up** -- check in if the user was sad/stressed.
    3. **Goal reminder**   -- remind the user of their stated goal.

All triggers respect a global cooldown to prevent spamming.

Usage::

    from autonomous import get_autonomous_message, record_activity

    # Call on every user interaction:
    record_activity()

    # Periodically check (e.g. between input prompts):
    msg = get_autonomous_message(memory)
    if msg:
        print(f"  Aisha : {msg}")
"""

from __future__ import annotations

import random
import time
from typing import Any


# ---------------------------------------------------------------------------
# Configuration (seconds)
# ---------------------------------------------------------------------------

# How long the user must be idle before Aisha speaks up.
IDLE_MIN_SECONDS = 60
IDLE_MAX_SECONDS = 120

# Minimum gap between any two autonomous messages (prevents spam).
COOLDOWN_SECONDS = 150   # 2.5 minutes

# How long after detecting sad/stressed emotion to follow up.
EMOTION_FOLLOWUP_DELAY = 90   # 1.5 minutes


# ---------------------------------------------------------------------------
# Internal State
# ---------------------------------------------------------------------------

_last_activity_time: float = time.time()
_last_autonomous_time: float = 0.0
_idle_threshold: float = random.uniform(IDLE_MIN_SECONDS, IDLE_MAX_SECONDS)


def record_activity() -> None:
    """
    Call this every time the user sends input.

    Resets the idle timer and randomises the next idle threshold so
    Aisha doesn't always speak at exactly the same delay.
    """
    global _last_activity_time, _idle_threshold
    _last_activity_time = time.time()
    _idle_threshold = random.uniform(IDLE_MIN_SECONDS, IDLE_MAX_SECONDS)


def _seconds_idle() -> float:
    """Return how many seconds since the last user interaction."""
    return time.time() - _last_activity_time


def _cooldown_ok() -> bool:
    """Return True if enough time has passed since the last autonomous message."""
    return (time.time() - _last_autonomous_time) >= COOLDOWN_SECONDS


def _mark_sent() -> None:
    """Record that an autonomous message was just sent (resets cooldown)."""
    global _last_autonomous_time
    _last_autonomous_time = time.time()


# ---------------------------------------------------------------------------
# Idle Messages
# ---------------------------------------------------------------------------

_IDLE_MESSAGES: list[str] = [
    "Hey, are you still there? I'm here if you need anything!",
    "Still around? Feel free to ask me anything.",
    "I'm still here whenever you're ready to chat!",
    "Take your time -- I'll be right here when you need me.",
    "Just checking in! Let me know if I can help with something.",
]


def _check_idle() -> str | None:
    """Return an idle nudge if the user has been quiet too long."""
    if _seconds_idle() >= _idle_threshold:
        return random.choice(_IDLE_MESSAGES)
    return None


# ---------------------------------------------------------------------------
# Emotion Follow-Up (with cause awareness)
# ---------------------------------------------------------------------------

_EMOTION_FOLLOWUPS: dict[str, list[str]] = {
    "sad": [
        "You seemed a bit down earlier. How are you feeling now?",
        "Hey, I noticed you were feeling sad. Want to talk about it?",
        "Just checking in -- I hope you're feeling a little better now.",
    ],
    "stressed": [
        "You seemed stressed earlier. Want to take a break or talk?",
        "Hey, remember it's okay to slow down. How are you doing now?",
        "I noticed you were feeling overwhelmed. I'm here if you need me.",
    ],
    "angry": [
        "You seemed upset earlier. I hope things are calming down.",
        "Just checking in -- feeling any better now?",
        "Take a deep breath. I'm here whenever you're ready.",
    ],
}

# Templates that reference the specific cause (when available)
_EMOTION_FOLLOWUPS_WITH_CAUSE: dict[str, list[str]] = {
    "sad": [
        "You seemed down about {cause} earlier. How are you feeling now?",
        "Hey, I know {cause} was getting to you. Want to talk about it?",
        "Just checking in about {cause} -- I hope things are looking up.",
    ],
    "stressed": [
        "You were stressed about {cause} earlier -- how is it going now?",
        "Hey, is {cause} still weighing on you? I'm here if you need me.",
        "Just checking in about {cause}. Want to take a break or talk?",
    ],
    "angry": [
        "You seemed frustrated about {cause} earlier. Feeling any better?",
        "Is {cause} still bothering you? I'm here whenever you're ready.",
        "Just checking in about {cause}. I hope things are calming down.",
    ],
}


def _check_emotion_followup(memory: Any) -> str | None:
    """
    Return a follow-up message if the user's last emotion was negative
    and enough time has passed since it was recorded.

    Uses the stored ``last_emotion_cause`` to make the follow-up specific
    when available.
    """
    last_emotion = memory.get_user_info("last_emotion")
    if not last_emotion or last_emotion not in _EMOTION_FOLLOWUPS:
        return None

    # Only follow up if the user has been idle for a bit
    # (don't interrupt an active conversation)
    if _seconds_idle() < EMOTION_FOLLOWUP_DELAY:
        return None

    # Check if we know the cause
    cause = memory.get_user_info("last_emotion_cause")
    if cause and last_emotion in _EMOTION_FOLLOWUPS_WITH_CAUSE:
        template = random.choice(_EMOTION_FOLLOWUPS_WITH_CAUSE[last_emotion])
        return template.format(cause=cause)

    return random.choice(_EMOTION_FOLLOWUPS[last_emotion])


# ---------------------------------------------------------------------------
# Goal Reminder
# ---------------------------------------------------------------------------

_GOAL_REMINDERS: list[str] = [
    "By the way, you mentioned you wanted to {goal}. Want to continue?",
    "Remember your goal to {goal}? I can help you with that right now!",
    "Hey, just a gentle reminder -- you wanted to {goal}. Shall we work on it?",
    "Whenever you're ready, I can help you {goal}. Just say the word!",
]


def _check_goal_reminder(memory: Any) -> str | None:
    """
    Return a goal reminder if the user has a stored goal and has
    been idle long enough.
    """
    goal = memory.get_user_info("goal")
    if not goal:
        return None

    # Only remind during idle periods
    if _seconds_idle() < IDLE_MIN_SECONDS:
        return None

    template = random.choice(_GOAL_REMINDERS)
    return template.format(goal=goal)


# ---------------------------------------------------------------------------
# Self-Care Proactive Messages
# ---------------------------------------------------------------------------

_SELF_CARE_PROACTIVE: list[str] = [
    "I've noticed you've been going through a lot lately. Remember to take care of yourself.",
    "You've been stressed for a while now. A short break could really help.",
    "Hey, you matter too. Have you had water and a proper meal today?",
    "I can tell things have been tough. It's okay to step away for a bit.",
    "Real talk: you've been carrying a lot. Be kind to yourself today.",
]


def _check_self_care_proactive(memory: Any) -> str | None:
    """
    Proactively suggest self-care if the user has been in a declining
    emotional state over multiple interactions.
    """
    history = memory.get_user_info("emotion_history") or []
    if len(history) < 3:
        return None

    # Check if 3+ of last 5 are negative
    negative = {"sad", "stressed", "angry"}
    recent = [e["emotion"] for e in history[-5:]]
    neg_count = sum(1 for e in recent if e in negative)

    if neg_count < 3:
        return None

    # Only suggest during idle
    if _seconds_idle() < EMOTION_FOLLOWUP_DELAY:
        return None

    cause = memory.get_user_info("last_emotion_cause")
    base = random.choice(_SELF_CARE_PROACTIVE)

    if cause:
        base += f" I know {cause} has been on your mind."

    return base


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def get_autonomous_message(memory: Any) -> str | None:
    """
    Check all autonomous triggers and return a message if one fires.

    Priority order:
        1. Emotion follow-up (most important -- user wellbeing)
        2. Self-care (declining emotional trend)
        3. Idle check (basic presence detection)
        4. Goal reminder (motivational nudge)

    Returns ``None`` if no trigger fires or cooldown hasn't elapsed.

    Parameters
    ----------
    memory : Memory
        The shared Memory instance (from ``brain.aisha_memory``).

    Returns
    -------
    str or None
        An autonomous message, or ``None`` if nothing to say.
    """
    # Respect global cooldown -- never spam
    if not _cooldown_ok():
        return None

    # Priority 1: Emotion follow-up
    msg = _check_emotion_followup(memory)
    if msg:
        _mark_sent()
        record_activity()
        return msg

    # Priority 2: Self-care (when trend is declining)
    msg = _check_self_care_proactive(memory)
    if msg:
        _mark_sent()
        record_activity()
        return msg

    # Priority 3: Idle nudge
    msg = _check_idle()
    if msg:
        _mark_sent()
        record_activity()
        return msg

    # Priority 4: Goal reminder (only when idle)
    msg = _check_goal_reminder(memory)
    if msg:
        _mark_sent()
        record_activity()
        return msg

    return None
