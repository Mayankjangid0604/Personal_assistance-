"""
Autonomous Presence Layer with Governor for Aisha AI Assistant (Phase 3 Step 4).

Proactive intelligence that is:
    - Memory-driven (uses semantic + episodic recall)
    - Budget-controlled (governor prevents spam)
    - Contextually aware (time, emotion, activity)
    - Non-intrusive (respects user state)

Presence Governor enforces:
    - Daily budget:     max 15 proactive messages/day
    - Hourly budget:    max 3/hour
    - Session cooldown: min 5 minutes between messages
    - Escalation tiers: 0 (silent) → 3 (fully engaged)
    - Time gating:      no messages 11pm–7am unless urgent
    - Emotional gating: no cheerful nudges when stressed

Usage::

    from presence import presence_engine

    # Check for proactive message
    msg = presence_engine.check()
    if msg:
        emit_to_user(msg)

    # Set escalation tier
    presence_engine.set_tier(2)  # normal

    # Get governor status
    status = presence_engine.get_status()
"""

from __future__ import annotations

import os
import random
import sys
import time
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Governor Configuration
# ---------------------------------------------------------------------------

DAILY_BUDGET = 15
HOURLY_BUDGET = 3
SESSION_COOLDOWN_SECONDS = 300   # 5 minutes
QUIET_HOURS_START = 23           # 11 PM
QUIET_HOURS_END = 7              # 7 AM

TIER_DESCRIPTIONS = {
    0: "silent",        # No proactive messages
    1: "minimal",       # Urgent reminders only
    2: "normal",        # Reminders + gentle nudges (default)
    3: "engaged",       # Full proactive behavior
}


# ---------------------------------------------------------------------------
# Governor State
# ---------------------------------------------------------------------------

class PresenceGovernor:
    """
    Budget-based governor that controls proactive message flow.

    Prevents spam and ensures messages are appropriate for the
    user's current context.
    """

    def __init__(self) -> None:
        self._tier: int = 2                      # Default: normal
        self._daily_count: int = 0
        self._hourly_count: int = 0
        self._last_message_time: float = 0.0
        now = datetime.now()
        self._last_hour: int = now.hour
        self._last_day: int = now.day
        self._suppressed_count: int = 0

    def set_tier(self, tier: int) -> None:
        """Set escalation tier (0–3)."""
        self._tier = max(0, min(3, tier))

    @property
    def tier(self) -> int:
        return self._tier

    def can_send(self, urgency: str = "normal") -> bool:
        """
        Check if a proactive message is allowed right now.

        Parameters:
            urgency: "low", "normal", "high", "urgent"
        """
        now = datetime.now()

        # Tier 0 blocks everything
        if self._tier == 0:
            self._suppressed_count += 1
            return False

        # Tier 1 only allows urgent
        if self._tier == 1 and urgency not in ("urgent", "high"):
            self._suppressed_count += 1
            return False

        # Quiet hours (unless urgent)
        if urgency != "urgent":
            hour = now.hour
            if hour >= QUIET_HOURS_START or hour < QUIET_HOURS_END:
                self._suppressed_count += 1
                return False

        # Session cooldown
        if time.time() - self._last_message_time < SESSION_COOLDOWN_SECONDS:
            if urgency != "urgent":
                self._suppressed_count += 1
                return False

        # Reset counters on new day/hour
        if now.day != self._last_day:
            self._daily_count = 0
            self._last_day = now.day
        if now.hour != self._last_hour:
            self._hourly_count = 0
            self._last_hour = now.hour

        # Budget checks
        if self._daily_count >= DAILY_BUDGET:
            self._suppressed_count += 1
            return False
        if self._hourly_count >= HOURLY_BUDGET:
            self._suppressed_count += 1
            return False

        return True

    def record_sent(self) -> None:
        """Record that a proactive message was sent."""
        self._daily_count += 1
        self._hourly_count += 1
        self._last_message_time = time.time()

    def get_status(self) -> dict[str, Any]:
        """Return governor status."""
        return {
            "tier": self._tier,
            "tier_description": TIER_DESCRIPTIONS.get(self._tier, "unknown"),
            "daily_count": self._daily_count,
            "daily_budget": DAILY_BUDGET,
            "hourly_count": self._hourly_count,
            "hourly_budget": HOURLY_BUDGET,
            "suppressed_count": self._suppressed_count,
            "cooldown_remaining": max(
                0,
                SESSION_COOLDOWN_SECONDS - (time.time() - self._last_message_time),
            ),
        }


# ---------------------------------------------------------------------------
# Presence Engine
# ---------------------------------------------------------------------------

class PresenceEngine:
    """
    Proactive presence layer.  Generates contextual suggestions and
    check-ins using semantic + episodic memory.
    """

    def __init__(self) -> None:
        self.governor = PresenceGovernor()
        self._last_activity: float = time.time()
        self._last_emotion: str = "neutral"
        self._deep_work: bool = False
        print("  [Presence] Engine initialized (tier=%d)" % self.governor.tier)

    def record_activity(self, emotion: str = "neutral") -> None:
        """Record user activity (call on every interaction)."""
        self._last_activity = time.time()
        self._last_emotion = emotion

    def set_deep_work(self, active: bool) -> None:
        """Set deep work mode (suppresses non-urgent messages)."""
        self._deep_work = active

    def set_tier(self, tier: int) -> None:
        """Set escalation tier."""
        self.governor.set_tier(tier)

    def check(self) -> dict[str, Any] | None:
        """
        Check if a proactive message should be sent.

        Returns a message dict or None if nothing to say.
        Message dict: {text, category, urgency}
        """
        # Deep work suppression
        if self._deep_work:
            return None

        # Emotional gating: don't be cheerful when user is stressed
        if self._last_emotion in ("stressed", "sad", "angry"):
            return self._check_emotional(self._last_emotion)

        # Idle check
        idle_seconds = time.time() - self._last_activity
        if idle_seconds > 600:  # 10 minutes
            return self._check_idle(idle_seconds)

        # Pattern-based check
        return self._check_patterns()

    def _check_emotional(self, emotion: str) -> dict | None:
        """Generate an emotional check-in if appropriate."""
        if not self.governor.can_send("normal"):
            return None

        messages = {
            "stressed": [
                "Hey, I noticed things have been stressful. Want to talk about it?",
                "Remember, it's okay to take a break. You've been working hard.",
                "Would it help to walk through what's on your mind?",
            ],
            "sad": [
                "I'm here if you want to talk. No pressure.",
                "Sometimes just naming what's bothering you helps. I'm listening.",
                "You've gotten through tough times before. I'm here for you.",
            ],
            "angry": [
                "I can tell something's frustrating. Want to vent?",
                "Take your time. I'm here when you're ready.",
            ],
        }

        options = messages.get(emotion, [])
        if not options:
            return None

        msg = {
            "text": random.choice(options),
            "category": "emotional_checkin",
            "urgency": "normal",
        }
        self.governor.record_sent()
        return msg

    def _check_idle(self, idle_seconds: float) -> dict | None:
        """Generate an idle nudge if appropriate."""
        if not self.governor.can_send("low"):
            return None

        minutes = int(idle_seconds / 60)

        messages = [
            "You've been quiet for a bit. Everything okay?",
            f"It's been about {minutes} minutes. Need anything?",
            "Still here if you need me. No rush.",
        ]

        msg = {
            "text": random.choice(messages),
            "category": "idle_nudge",
            "urgency": "low",
        }
        self.governor.record_sent()
        return msg

    def _check_patterns(self) -> dict | None:
        """Check for pattern-based proactive messages."""
        hour = datetime.now().hour

        # Morning greeting (8-9 AM)
        if 8 <= hour <= 9:
            if not self.governor.can_send("low"):
                return None

            # Only if no recent activity
            idle = time.time() - self._last_activity
            if idle > 1800:  # 30 minutes idle
                msg = {
                    "text": "Good morning! Ready to start the day?",
                    "category": "routine_greeting",
                    "urgency": "low",
                }
                self.governor.record_sent()
                return msg

        return None

    def get_memory_driven_suggestion(self) -> dict | None:
        """
        Generate a suggestion using semantic + episodic memory.

        Called by the orchestrator during consolidation or idle periods.
        """
        if not self.governor.can_send("normal"):
            return None

        try:
            from episodic_memory import episodic_memory

            arc = episodic_memory.get_emotional_arc(days=7)
            if arc["trend"] == "declining":
                msg = {
                    "text": "I've noticed you've been having a tough week. "
                            "Would you like to talk about what's going on?",
                    "category": "memory_driven",
                    "urgency": "normal",
                }
                self.governor.record_sent()
                return msg

            patterns = episodic_memory.get_patterns(category="stress_cycle", limit=1)
            if patterns:
                msg = {
                    "text": "I've noticed a stress pattern recently. "
                            "Last time, talking it out seemed to help. Want to try that?",
                    "category": "pattern_driven",
                    "urgency": "normal",
                }
                self.governor.record_sent()
                return msg

        except Exception:
            pass

        return None

    def get_status(self) -> dict[str, Any]:
        """Return full presence engine status."""
        return {
            "governor": self.governor.get_status(),
            "last_activity_ago": round(time.time() - self._last_activity, 1),
            "last_emotion": self._last_emotion,
            "deep_work": self._deep_work,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

presence_engine = PresenceEngine()
