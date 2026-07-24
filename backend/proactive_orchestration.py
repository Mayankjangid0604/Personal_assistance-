"""
Proactive Ecosystem Orchestration for Aisha AI Assistant (Phase 6 Step 7).

Allows AISHA to intelligently prepare and suggest assistance across
workflows. All proactive events are suggestions — never automated actions.

Proactive event types:
    workflow_preparation  — Detected routine → offer workspace setup
    goal_reminder         — Active goal not updated in 3+ days
    recovery_suggestion   — Burnout risk rising + long focus session
    celebration           — Milestone reached or streak continued

Governor integration:
    - All events routed through emotional_timing.should_initiate()
    - Maximum 3 proactive events per day
    - Zero during deep work or low-interruption mode
    - User can mute proactive orchestration entirely

Design principles:
    "Suggest, never command."
    "Respect focus, protect recovery."
    "Celebrate genuinely, not performatively."

Usage::

    from proactive_orchestration import proactive_orchestration

    # Check for proactive suggestions
    suggestion = proactive_orchestration.check_proactive(context)

    # Mute/unmute proactive events
    proactive_orchestration.set_muted(True)

    # Get status
    status = proactive_orchestration.get_status()
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection

# Maximum proactive events per day
_MAX_DAILY_EVENTS = 3

# Minimum days before a goal reminder
_GOAL_STALE_DAYS = 3


class ProactiveOrchestration:
    """
    Intelligently coordinates proactive assistance across workflows.

    All suggestions are gated through emotional_timing and bounded
    by strict daily limits. User can mute entirely.
    """

    def __init__(self) -> None:
        self._muted: bool = False
        self._today_count: int = 0
        self._today_date: str = ""
        self._refresh_daily_count()
        print("  [Proactive] Ecosystem Orchestration initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_proactive(
        self, context: dict[str, Any] | None = None,
    ) -> str | None:
        """
        Check for a proactive suggestion to offer.

        Returns a suggestion string or None.
        Only returns at most one suggestion per call.
        """
        if self._muted:
            return None

        # Refresh daily counter
        self._refresh_daily_count()
        if self._today_count >= _MAX_DAILY_EVENTS:
            return None

        # Emotional timing gate
        try:
            from emotional_timing import emotional_timing
            if not emotional_timing.should_initiate():
                return None
        except ImportError:
            # Fallback: basic check
            try:
                from environmental_reasoning import environment
                if environment.is_low_interruption():
                    return None
            except Exception:
                pass

        context = context or {}

        # Priority 1: Recovery suggestion (highest safety value)
        suggestion = self._check_recovery(context)
        if suggestion:
            return self._emit(suggestion, "recovery_suggestion", context)

        # Priority 2: Celebration
        suggestion = self._check_celebration(context)
        if suggestion:
            return self._emit(suggestion, "celebration", context)

        # Priority 3: Goal reminder (stale goals)
        suggestion = self._check_goal_reminder()
        if suggestion:
            return self._emit(suggestion, "goal_reminder", context)

        # Priority 4: Workflow preparation (lowest priority)
        suggestion = self._check_workflow_preparation(context)
        if suggestion:
            return self._emit(suggestion, "workflow_preparation", context)

        return None

    def set_muted(self, muted: bool) -> dict:
        """Mute or unmute proactive orchestration."""
        self._muted = muted
        return {"status": "ok", "muted": muted}

    def get_status(self) -> dict[str, Any]:
        """Return proactive orchestration status."""
        self._refresh_daily_count()
        return {
            "muted": self._muted,
            "today_events": self._today_count,
            "max_daily_events": _MAX_DAILY_EVENTS,
            "remaining_today": max(0, _MAX_DAILY_EVENTS - self._today_count),
        }

    def get_recent_events(self, limit: int = 10) -> list[dict]:
        """Return recent proactive events."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, event_type, suggestion, was_accepted, created_at "
                    "FROM proactive_events ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def record_outcome(self, event_id: int, accepted: bool) -> dict:
        """Record whether a proactive suggestion was accepted."""
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE proactive_events SET was_accepted=? WHERE id=?",
                    (1 if accepted else 0, event_id),
                )
            # Feed back to emotional timing
            try:
                from emotional_timing import emotional_timing
                emotional_timing.record_outcome("proactive", engaged=accepted)
            except Exception:
                pass
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ------------------------------------------------------------------
    # Proactive Checks
    # ------------------------------------------------------------------

    def _check_recovery(self, context: dict) -> str | None:
        """Suggest recovery when burnout risk is rising."""
        burnout = context.get("burnout_risk", "none")
        focus_score = context.get("focus_score", 0.5)

        if burnout in ("moderate", "high") and focus_score > 0.6:
            return (
                "You've been going strong for a while. "
                "A short break might help you go further."
            )
        return None

    def _check_celebration(self, context: dict) -> str | None:
        """Celebrate when milestones or streaks are detected."""
        # Check for streak recognition
        try:
            from life_management import life_management
            streak = life_management.get_streak_recognition()
            if streak:
                # Only celebrate through emotional timing
                try:
                    from emotional_timing import emotional_timing
                    if emotional_timing.should_celebrate():
                        return streak
                except ImportError:
                    return streak
        except Exception:
            pass
        return None

    def _check_goal_reminder(self) -> str | None:
        """Remind about goals not updated in 3+ days."""
        try:
            cutoff = (
                datetime.now() - timedelta(days=_GOAL_STALE_DAYS)
            ).isoformat(timespec="seconds")
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT title, progress, updated_at FROM life_goals "
                    "WHERE status='active' AND updated_at < ? "
                    "ORDER BY updated_at ASC LIMIT 1",
                    (cutoff,),
                ).fetchone()
            if row:
                pct = int(float(row["progress"]) * 100)
                return (
                    f"You were making progress on '{row['title']}' ({pct}%). "
                    "Want to pick it up?"
                )
        except Exception:
            pass
        return None

    def _check_workflow_preparation(self, context: dict) -> str | None:
        """Suggest workspace setup based on detected routines."""
        try:
            from routine_intelligence import routine_intelligence
            routines = routine_intelligence.get_active_routines()
            if routines:
                hour = datetime.now().hour
                for r in routines:
                    typical_hour = r.get("typical_hour")
                    if typical_hour and abs(hour - typical_hour) <= 1:
                        desc = r.get("description", "your usual workflow")
                        return (
                            f"Looks like it's about time for {desc}. "
                            "Want me to set things up?"
                        )
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit(
        self, suggestion: str, event_type: str, context: dict,
    ) -> str:
        """Record a proactive event and return the suggestion."""
        self._today_count += 1
        now = datetime.now().isoformat(timespec="seconds")

        # Record to emotional timing
        try:
            from emotional_timing import emotional_timing
            emotional_timing.record_proactive_event()
        except Exception:
            pass

        # Persist event
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO proactive_events "
                    "(event_type, suggestion, context_json, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (event_type, suggestion, json.dumps(context or {}), now),
                )
        except Exception:
            pass

        return suggestion

    def _refresh_daily_count(self) -> None:
        """Refresh the daily event counter."""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._today_date:
            self._today_date = today
            try:
                with get_connection() as conn:
                    row = conn.execute(
                        "SELECT COUNT(*) as cnt FROM proactive_events "
                        "WHERE created_at >= ?",
                        (f"{today}T00:00:00",),
                    ).fetchone()
                self._today_count = row["cnt"] if row else 0
            except Exception:
                self._today_count = 0


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

proactive_orchestration = ProactiveOrchestration()
