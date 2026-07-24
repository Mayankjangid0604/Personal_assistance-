"""
Adaptive Life Management for Aisha AI Assistant (Phase 5 Step 7,
updated Phase 6 Step 5 with adaptive coaching).

Burnout-aware goal scheduling and long-term roadmap support.
Extends cognitive_planner with recovery-aware pacing, milestone
recognition, and gentle coaching nudges.

AISHA assists — never controls.
- Goals are tracked, not enforced
- Pacing adjusts quietly when burnout risk is elevated
- Milestones are recognized warmly, not clinically
- At most ONE coaching message surfaces per session
- Coaching gated through emotional_timing.should_nudge()
- Coaching intensity adapts via deep_personalization
- Streak recognition for multi-day consistency
- Rhythm-aware suggestions aligned with focus windows

Design principles:
    "Support long-term growth without pressure."
    "Recognize progress without demanding it."
    "Adjust pacing without lecturing."

Usage::

    from life_management import life_management

    # Create a life goal
    life_management.create_goal("Learn Rust", target_date="2026-12-31")

    # Get coaching nudge for this session (at most one)
    nudge = life_management.get_session_nudge()

    # Update goal progress
    life_management.update_progress(goal_id, progress)

    # Get all active life goals
    goals = life_management.get_active_goals()
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


_MILESTONE_THRESHOLDS = [0.25, 0.50, 0.75, 1.0]
_MILESTONE_LABELS = {
    0.25: "quarter of the way",
    0.50: "halfway",
    0.75: "three-quarters",
    1.0: "all the way",
}

_BURNOUT_PACING_MESSAGES = {
    "moderate": (
        "Given how much you've been working lately, it's fine to take this goal "
        "at a gentler pace. Progress doesn't have to be urgent."
    ),
    "high": (
        "You've been pushing hard. Your long-term goals will still be there after "
        "you've had some recovery time. Rest is part of the process."
    ),
}

_MILESTONE_MESSAGES = {
    0.25: "You've made it a quarter of the way — that's a real start.",
    0.50: "Halfway there. That's meaningful progress worth acknowledging.",
    0.75: "Three-quarters done. You're in the final stretch.",
    1.0: "You did it. Goal complete.",
}


class LifeManagement:
    """
    Burnout-aware life goal management and gentle progress coaching.

    Reads from cognitive_plans and life_goals tables.
    Provides session-level nudges (at most one per session).
    """

    def __init__(self) -> None:
        self._session_nudge_given: bool = False
        print("  [LifeMgmt] Adaptive Life Management initialized")

    # ------------------------------------------------------------------
    # Goal Management
    # ------------------------------------------------------------------

    def create_goal(
        self,
        title: str,
        description: str = "",
        target_date: str | None = None,
    ) -> dict[str, Any]:
        """Create a new life goal."""
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with get_connection() as conn:
                cursor = conn.execute(
                    "INSERT INTO life_goals "
                    "(title, description, target_date, status, progress, "
                    "burnout_adjusted, checkpoint_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'active', 0.0, 0, '[]', ?, ?)",
                    (title, description, target_date, now, now),
                )
            return {
                "status": "created",
                "id": cursor.lastrowid,
                "title": title,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def update_progress(self, goal_id: int, progress: float) -> dict[str, Any]:
        """Update goal progress (0.0–1.0). Detects and records milestones."""
        progress = max(0.0, min(1.0, progress))
        now = datetime.now().isoformat(timespec="seconds")

        # Check for milestone crossings
        goal = self._get_goal(goal_id)
        milestone_msg = None
        if goal:
            old_progress = goal.get("progress", 0.0)
            milestone_msg = self._check_milestone(old_progress, progress, goal["title"])

        try:
            status = "completed" if progress >= 1.0 else "active"
            with get_connection() as conn:
                conn.execute(
                    "UPDATE life_goals SET progress=?, status=?, updated_at=? WHERE id=?",
                    (progress, status, now, goal_id),
                )
        except Exception as e:
            return {"status": "error", "error": str(e)}

        result: dict[str, Any] = {
            "status": "updated",
            "id": goal_id,
            "progress": progress,
        }
        if milestone_msg:
            result["milestone"] = milestone_msg
        return result

    def get_active_goals(self) -> list[dict]:
        """Return all active life goals."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, title, description, target_date, status, "
                    "progress, burnout_adjusted, checkpoint_json, "
                    "created_at, updated_at "
                    "FROM life_goals WHERE status = 'active' "
                    "ORDER BY updated_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_all_goals(self, limit: int = 10) -> list[dict]:
        """Return recent goals of any status."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, title, description, status, progress, "
                    "created_at, updated_at FROM life_goals "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Session Coaching
    # ------------------------------------------------------------------

    def get_session_nudge(self, emotion: str = "neutral") -> str | None:
        """
        Return a coaching nudge for this session, or None.

        At most one nudge per session. Respects burnout state.
        Never surfaces during deep work or low-interruption mode.
        Gated through emotional_timing (Phase 6).
        Coaching intensity adapts via deep_personalization.
        """
        if self._session_nudge_given:
            return None

        # Phase 6: Emotional timing gate
        try:
            from emotional_timing import emotional_timing
            if not emotional_timing.should_nudge(emotion):
                return None
        except ImportError:
            # Fallback: environmental gate only
            try:
                from environmental_reasoning import environment
                if environment.is_low_interruption():
                    return None
            except Exception:
                pass

        # Phase 6: Coaching intensity check
        try:
            from deep_personalization import deep_personalization
            intensity = deep_personalization.get_dimension("coaching_intensity")
            import random
            # Low intensity → skip most nudges (probabilistic)
            if intensity < 0.3 and random.random() > intensity:
                return None
        except Exception:
            pass

        nudge = self._compute_nudge(emotion)
        if nudge:
            self._session_nudge_given = True
        return nudge

    def reset_session(self) -> None:
        """Reset session coaching state (call at session start)."""
        self._session_nudge_given = False

    def get_status(self) -> dict[str, Any]:
        """Return life management status."""
        goals = self.get_active_goals()
        return {
            "active_goals": len(goals),
            "goals": [
                {
                    "id": g["id"],
                    "title": g["title"],
                    "progress": g["progress"],
                    "target_date": g.get("target_date"),
                }
                for g in goals
            ],
            "session_nudge_given": self._session_nudge_given,
        }

    # ------------------------------------------------------------------
    # Internal Computation
    # ------------------------------------------------------------------

    def _compute_nudge(self, emotion: str) -> str | None:
        """Compute the most relevant coaching nudge."""
        # Check burnout state first (always takes priority)
        try:
            from productivity_cognition import productivity_engine
            burnout = productivity_engine.get_burnout_risk()
            if burnout in _BURNOUT_PACING_MESSAGES:
                return _BURNOUT_PACING_MESSAGES[burnout]
        except Exception:
            pass

        # Check for near-milestone goals
        goals = self.get_active_goals()
        for goal in goals:
            progress = goal.get("progress", 0.0)
            title = goal.get("title", "your goal")
            for threshold in _MILESTONE_THRESHOLDS:
                if abs(progress - threshold) < 0.08:
                    label = _MILESTONE_LABELS[threshold]
                    return (
                        f"You're {label} through '{title}'. "
                        "Steady progress adds up."
                    )

        # Generic encouragement if goals exist and user is neutral/positive
        if goals and emotion in ("neutral", "happy", "motivated", "excited"):
            most_active = goals[0]
            pct = int(most_active.get("progress", 0) * 100)
            if pct > 0:
                return (
                    f"'{most_active['title']}' is at {pct}% — "
                    "you're making real headway."
                )
        return None

    def get_streak_recognition(self) -> str | None:
        """
        Recognize multi-day consistency without demanding it (Phase 6).

        Checks if user has updated any goal for 3+ consecutive days.
        """
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT DISTINCT DATE(updated_at) as d FROM life_goals "
                    "WHERE status='active' AND progress > 0 "
                    "ORDER BY d DESC LIMIT 7"
                ).fetchall()
            if len(rows) < 3:
                return None
            dates = [r["d"] for r in rows]
            # Check consecutive days
            consecutive = 1
            for i in range(1, len(dates)):
                prev = datetime.strptime(dates[i - 1], "%Y-%m-%d")
                curr = datetime.strptime(dates[i], "%Y-%m-%d")
                if (prev - curr).days == 1:
                    consecutive += 1
                else:
                    break
            if consecutive >= 3:
                return f"{consecutive} days in a row — that's real consistency."
        except Exception:
            pass
        return None

    def get_rhythm_suggestion(self) -> str | None:
        """
        Suggest goal work aligned with detected focus windows (Phase 6).

        Uses routine_intelligence to find the user's natural focus time.
        """
        goals = self.get_active_goals()
        if not goals:
            return None

        try:
            from routine_intelligence import routine_intelligence
            windows = routine_intelligence.get_focus_windows()
            if windows:
                best = windows[0]
                hour = best.get("hour", 9)
                time_label = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
                goal = goals[0]
                return (
                    f"Your focus tends to peak in the {time_label}. "
                    f"That might be a good time for '{goal['title']}'."
                )
        except Exception:
            pass
        return None


    def _check_milestone(
        self, old_progress: float, new_progress: float, title: str
    ) -> str | None:
        """Return a milestone message if a threshold was crossed."""
        for threshold in _MILESTONE_THRESHOLDS:
            if old_progress < threshold <= new_progress:
                return _MILESTONE_MESSAGES.get(threshold, "Great progress!")
        return None

    def _get_goal(self, goal_id: int) -> dict | None:
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT id, title, progress FROM life_goals WHERE id = ?",
                    (goal_id,),
                ).fetchone()
            return dict(row) if row else None
        except Exception:
            return None


life_management = LifeManagement()
