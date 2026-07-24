"""
Emotional Timing Intelligence for Aisha AI Assistant (Phase 6 Step 2).

A gating layer that determines WHETHER and WHEN AISHA should offer
particular types of content. Prevents tone-deaf interruptions and
learns the user's silence preferences over time.

Gates:
    should_reflect()    — Is this a good moment for a reflective insight?
    should_nudge()      — Is this a good moment for a coaching nudge?
    should_initiate()   — Is this a good moment for proactive contact?
    should_celebrate()  — Is this a good moment to recognize progress?

Silence learning:
    Tracks when user ignores proactive offers (no engagement within 5 min).
    Over time, learns optimal quiet hours and reduces interruption during them.

Design principles:
    - No content is suppressed permanently — only delayed
    - Deep work is always protected
    - Emotional overload always triggers cooldown
    - User can always override ("don't bother me" / "I'm free to chat")

Usage::

    from emotional_timing import emotional_timing

    # Check if now is appropriate for a reflection
    if emotional_timing.should_reflect():
        insight = reflective_cognition.get_ready_insight()

    # Record outcome (user engaged or ignored)
    emotional_timing.record_outcome("reflection", engaged=True)
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection

# ---------------------------------------------------------------------------
# Gate Thresholds
# ---------------------------------------------------------------------------

# Maximum messages per hour before considering "high density" (don't interrupt)
_HIGH_DENSITY_THRESHOLD = 12

# Minimum minutes since last proactive event
_PROACTIVE_COOLDOWN_MIN = 30

# Hours considered "quiet" by default until overridden by learning
_DEFAULT_QUIET_HOURS = set()  # None by default — learned from behavior

# Maximum ignored offers before a hour slot is marked "quiet"
_IGNORE_THRESHOLD = 3


class EmotionalTiming:
    """
    Determines whether AISHA should offer content at this moment.

    Fuses environmental mode, emotional state, interaction density,
    and learned silence preferences into gating decisions.
    """

    def __init__(self) -> None:
        self._last_proactive_at: datetime | None = None
        self._message_times: list[datetime] = []  # Recent message timestamps
        self._quiet_hours: set[int] = set()  # Learned quiet hours
        self._ignore_counts: dict[int, int] = defaultdict(int)  # hour → ignore count
        self._override_available: bool = False  # User said "I'm free"
        self._override_mute: bool = False  # User said "don't bother me"
        self._load_quiet_hours()
        print("  [Timing] Emotional Timing Intelligence initialized")

    # ------------------------------------------------------------------
    # Gate Methods
    # ------------------------------------------------------------------

    def should_reflect(self, emotion: str = "neutral") -> bool:
        """Should AISHA offer a reflective insight right now?"""
        if self._override_mute:
            return False

        # Never during emotional overload
        if self._is_emotional_overload(emotion):
            return False

        # Never during deep work
        if self._is_low_interruption():
            return False

        # Not during high conversation density
        if self._is_high_density():
            return False

        # Not during learned quiet hours
        if self._is_quiet_hour():
            return False

        return True

    def should_nudge(self, emotion: str = "neutral") -> bool:
        """Should AISHA offer a coaching nudge right now?"""
        if self._override_mute:
            return False

        # Never during overload or burnout
        if self._is_emotional_overload(emotion):
            return False

        # Not during deep work
        if self._is_low_interruption():
            return False

        # Check burnout — don't nag when exhausted
        try:
            from productivity_cognition import productivity_engine
            if productivity_engine.get_burnout_risk() in ("moderate", "high"):
                return False
        except Exception:
            pass

        return True

    def should_initiate(self) -> bool:
        """Should AISHA initiate proactive contact right now?"""
        if self._override_mute:
            return False

        if self._override_available:
            return True

        # Never during deep work
        if self._is_low_interruption():
            return False

        # Cooldown since last proactive event
        if self._last_proactive_at:
            elapsed = (datetime.now() - self._last_proactive_at).total_seconds() / 60
            if elapsed < _PROACTIVE_COOLDOWN_MIN:
                return False

        # Not during quiet hours
        if self._is_quiet_hour():
            return False

        # Not during high density
        if self._is_high_density():
            return False

        return True

    def should_celebrate(self, emotion: str = "neutral") -> bool:
        """Should AISHA celebrate a milestone right now?"""
        # Celebrations are almost always appropriate, except during overload
        if self._override_mute:
            return False
        if self._is_emotional_overload(emotion):
            return False
        return True

    # ------------------------------------------------------------------
    # Interaction Tracking
    # ------------------------------------------------------------------

    def record_message(self) -> None:
        """Record that a message was sent (for density tracking)."""
        now = datetime.now()
        self._message_times.append(now)
        # Keep only last hour
        cutoff = now - timedelta(hours=1)
        self._message_times = [t for t in self._message_times if t > cutoff]

    def record_proactive_event(self) -> None:
        """Record that a proactive event was offered."""
        self._last_proactive_at = datetime.now()

    def record_outcome(self, event_type: str, engaged: bool) -> None:
        """
        Record whether the user engaged with an offered event.

        Used for silence learning: repeated ignoring → learn quiet hour.
        """
        now = datetime.now()
        hour = now.hour

        if not engaged:
            self._ignore_counts[hour] += 1
            if self._ignore_counts[hour] >= _IGNORE_THRESHOLD:
                self._quiet_hours.add(hour)
                self._persist_quiet_hours()

        # Log to database
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO emotional_timing_log "
                    "(event_type, was_appropriate, context_json, observed_at) "
                    "VALUES (?, ?, ?, ?)",
                    (event_type, 1 if engaged else 0,
                     f'{{"hour": {hour}}}',
                     now.isoformat(timespec="seconds")),
                )
        except Exception:
            pass

    def update(self, emotion: str = "neutral", context: dict | None = None) -> None:
        """Update timing state (called every turn)."""
        self.record_message()

    # ------------------------------------------------------------------
    # User Overrides
    # ------------------------------------------------------------------

    def set_available(self) -> None:
        """User says 'I'm free to chat' — temporarily override quiet gates."""
        self._override_available = True
        self._override_mute = False

    def set_mute(self) -> None:
        """User says 'don't bother me' — suppress all proactive content."""
        self._override_mute = True
        self._override_available = False

    def clear_overrides(self) -> None:
        """Clear manual overrides (called at session boundary)."""
        self._override_available = False
        self._override_mute = False

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return emotional timing gate status."""
        return {
            "should_reflect": self.should_reflect(),
            "should_nudge": self.should_nudge(),
            "should_initiate": self.should_initiate(),
            "should_celebrate": self.should_celebrate(),
            "is_quiet_hour": self._is_quiet_hour(),
            "is_high_density": self._is_high_density(),
            "is_low_interruption": self._is_low_interruption(),
            "messages_last_hour": len(self._message_times),
            "quiet_hours": sorted(self._quiet_hours),
            "override_mute": self._override_mute,
            "override_available": self._override_available,
        }

    # ------------------------------------------------------------------
    # Internal Checks
    # ------------------------------------------------------------------

    def _is_emotional_overload(self, emotion: str) -> bool:
        """Check if user is in emotional overload."""
        overload_emotions = {"overwhelmed", "angry", "anxious", "stressed"}
        return emotion in overload_emotions

    def _is_low_interruption(self) -> bool:
        """Check if environmental mode has low interruption tolerance."""
        try:
            from environmental_reasoning import environment
            return environment.is_low_interruption()
        except Exception:
            return False

    def _is_high_density(self) -> bool:
        """Check if conversation density is high (user is actively chatting)."""
        return len(self._message_times) >= _HIGH_DENSITY_THRESHOLD

    def _is_quiet_hour(self) -> bool:
        """Check if the current hour is a learned quiet hour."""
        return datetime.now().hour in self._quiet_hours

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_quiet_hours(self) -> None:
        """Save learned quiet hours to the timing log."""
        import json
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO emotional_timing_log "
                    "(event_type, was_appropriate, context_json, observed_at) "
                    "VALUES (?, ?, ?, ?)",
                    ("quiet_hours_update", 1,
                     json.dumps({"quiet_hours": sorted(self._quiet_hours)}),
                     now),
                )
        except Exception:
            pass

    def _load_quiet_hours(self) -> None:
        """Load learned quiet hours from the database."""
        import json
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT context_json FROM emotional_timing_log "
                    "WHERE event_type = 'quiet_hours_update' "
                    "ORDER BY observed_at DESC LIMIT 1"
                ).fetchone()
            if row and row["context_json"]:
                data = json.loads(row["context_json"])
                self._quiet_hours = set(data.get("quiet_hours", []))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

emotional_timing = EmotionalTiming()
