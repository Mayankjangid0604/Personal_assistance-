"""
Productivity Cognition Engine for Aisha AI Assistant (Phase 4 Step 4).

Intelligently supports user productivity and focus by analyzing:
    - Workload intensity (task switching rate, session duration)
    - Focus quality (sustained vs. fragmented attention)
    - Burnout risk (prolonged high-intensity work with no breaks)
    - Break patterns (when the user last rested)
    - Adaptive scheduling hints (optimal work/break windows)

Privacy-first:
    - Only uses categorical app data + timing metadata
    - No content analysis, no file monitoring
    - User controls all notification thresholds

Design principle:
    "Suggest gently. Never nag. Respect deep work."

EventBus events:
    productivity:burnout_risk    -- user showing signs of fatigue
    productivity:break_suggested -- gentle break suggestion
    productivity:focus_score     -- periodic focus quality score

Usage::

    from productivity_cognition import productivity_engine

    # Update with each desktop poll
    state = productivity_engine.update(desktop_snapshot)

    # Get productivity context for LLM
    context = productivity_engine.get_context_summary()

    # Check if a break should be suggested
    suggestion = productivity_engine.check_break_suggestion()
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Minimum continuous focused work before a break is suggested (seconds)
FOCUS_SESSION_BEFORE_BREAK = 90 * 60   # 90 minutes

# Minimum time since last break to suggest another one (seconds)
BREAK_COOLDOWN = 30 * 60               # 30 minutes

# Rapid app switches per 10-min window to flag as fragmented
FRAGMENTATION_THRESHOLD = 15

# Focus quality scoring weights
_FOCUS_WEIGHTS = {
    "coding":       1.0,
    "studying":     1.0,
    "design":       0.9,
    "browsing":     0.4,   # Could be research or distraction
    "communication": 0.2,
    "media":        0.0,
    "gaming":       0.0,
    "other":        0.3,
}

# Burnout risk thresholds
BURNOUT_RISK_SESSION_HOURS = 3.5       # Deep work sessions longer than this → risk
BURNOUT_RISK_DAILY_HOURS = 8.0         # Total productive hours in a day → risk


# ---------------------------------------------------------------------------
# Productivity Cognition Engine
# ---------------------------------------------------------------------------

class ProductivityEngine:
    """
    Monitors and intelligently supports user productivity.

    Maintains session metrics, computes focus quality scores, and
    generates non-intrusive productivity insights.
    """

    def __init__(self) -> None:
        self._session_start: float = time.time()
        self._focus_session_start: float | None = None
        self._last_break_at: float | None = None
        self._last_break_suggested: float = 0.0

        # Rolling metrics
        self._category_history: list[tuple[float, str]] = []  # (ts, category)
        self._switch_count: int = 0
        self._last_category: str | None = None

        # Daily accumulators
        self._daily_focus_seconds: float = 0.0
        self._daily_reset_day: int = datetime.now().day

        # Computed scores
        self._focus_score: float = 0.5
        self._burnout_risk: str = "none"   # none, low, moderate, high

        print("  [Productivity] Cognition Engine initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, desktop_snapshot: dict[str, Any]) -> dict[str, Any]:
        """
        Process a new desktop snapshot and update productivity metrics.

        Returns current productivity state.
        """
        now = time.time()
        category = desktop_snapshot.get("category", "other")

        # Daily reset
        today = datetime.now().day
        if today != self._daily_reset_day:
            self._daily_focus_seconds = 0.0
            self._daily_reset_day = today

        # Track category history (keep 60 entries ≈ last 10 minutes at 10s poll)
        self._category_history.append((now, category))
        if len(self._category_history) > 60:
            self._category_history = self._category_history[-60:]

        # Track app switching
        if self._last_category and category != self._last_category:
            self._switch_count += 1
        self._last_category = category

        # Focus session tracking
        is_focused = category in ("coding", "studying", "design")
        if is_focused:
            if self._focus_session_start is None:
                self._focus_session_start = now
            self._daily_focus_seconds += 10  # approximation (poll cadence)
        else:
            if self._focus_session_start is not None:
                session_len = now - self._focus_session_start
                if session_len > 300:  # Only count sessions > 5 min
                    self._last_break_at = now
                self._focus_session_start = None

        # Compute metrics
        self._focus_score = self._compute_focus_score()
        self._burnout_risk = self._compute_burnout_risk(now)

        return {
            "focus_score": round(self._focus_score, 2),
            "burnout_risk": self._burnout_risk,
            "switch_count": self._switch_count,
            "daily_focus_hours": round(self._daily_focus_seconds / 3600, 1),
            "in_focus_session": self._focus_session_start is not None,
            "focus_session_min": round(
                (now - self._focus_session_start) / 60, 1
            ) if self._focus_session_start else 0.0,
        }

    def check_break_suggestion(self) -> str | None:
        """
        Return a break suggestion message if appropriate, or None.

        Never suggests breaks during the first few minutes of work,
        and respects a minimum cooldown between suggestions.
        """
        now = time.time()

        # Cooldown between suggestions
        if now - self._last_break_suggested < BREAK_COOLDOWN:
            return None

        # Check focus session length
        if self._focus_session_start is None:
            return None

        session_len = now - self._focus_session_start
        if session_len < FOCUS_SESSION_BEFORE_BREAK:
            return None

        self._last_break_suggested = now
        session_min = int(session_len / 60)

        suggestions = [
            f"You've been focused for {session_min} minutes. A short break could help you stay sharp.",
            f"Impressive focus session ({session_min} min)! Even a 5-minute walk can boost creativity.",
            f"You've been deep in work for {session_min} minutes. "
            "Your brain will thank you for a brief pause.",
        ]

        import random
        return random.choice(suggestions)

    def get_focus_score(self) -> float:
        """Return the current focus quality score (0.0–1.0)."""
        return self._focus_score

    def get_burnout_risk(self) -> str:
        """Return the current burnout risk level: none/low/moderate/high."""
        return self._burnout_risk

    def get_context_summary(self) -> str:
        """
        Return a concise productivity context string for LLM prompts.

        Only returns content when there's something meaningful to convey.
        """
        parts = []

        if self._focus_score >= 0.75:
            parts.append("User is in high-quality focused work.")
        elif self._focus_score < 0.3:
            parts.append("User's attention appears fragmented — keep responses brief.")

        if self._burnout_risk == "high":
            parts.append("Burnout risk detected. Be supportive and encourage rest.")
        elif self._burnout_risk == "moderate":
            parts.append("Extended work session. Gently acknowledge effort if relevant.")

        if self._focus_session_start and (time.time() - self._focus_session_start) > 3600:
            hours = round((time.time() - self._focus_session_start) / 3600, 1)
            parts.append(f"User has been focused for {hours}h.")

        return " ".join(parts)

    def is_fragmented(self) -> bool:
        """Return True if user's recent attention is highly fragmented."""
        recent = [
            c for t, c in self._category_history
            if time.time() - t < 600  # Last 10 minutes
        ]
        distinct = len(set(recent))
        return distinct >= 5 and len(recent) >= 10

    def get_status(self) -> dict[str, Any]:
        """Return full productivity engine status."""
        now = time.time()
        return {
            "focus_score": round(self._focus_score, 2),
            "burnout_risk": self._burnout_risk,
            "daily_focus_hours": round(self._daily_focus_seconds / 3600, 1),
            "in_focus_session": self._focus_session_start is not None,
            "focus_session_min": round(
                (now - self._focus_session_start) / 60, 1
            ) if self._focus_session_start else 0.0,
            "is_fragmented": self.is_fragmented(),
            "switch_count": self._switch_count,
            "context_summary": self.get_context_summary(),
        }

    # ------------------------------------------------------------------
    # Internal Computation
    # ------------------------------------------------------------------

    def _compute_focus_score(self) -> float:
        """
        Compute focus quality from recent category history.

        Score = weighted average of productive time, penalized by fragmentation.
        """
        if not self._category_history:
            return 0.5

        recent = [c for _, c in self._category_history[-20:]]
        if not recent:
            return 0.5

        weighted = sum(_FOCUS_WEIGHTS.get(c, 0.3) for c in recent) / len(recent)

        # Fragmentation penalty
        distinct = len(set(recent))
        frag_penalty = max(0.0, (distinct - 2) * 0.06)

        return max(0.0, min(1.0, weighted - frag_penalty))

    def _compute_burnout_risk(self, now: float) -> str:
        """Compute burnout risk based on session duration and daily hours."""
        # Check extended focus session
        if self._focus_session_start:
            session_hours = (now - self._focus_session_start) / 3600
            if session_hours >= BURNOUT_RISK_SESSION_HOURS:
                return "high"
            if session_hours >= BURNOUT_RISK_SESSION_HOURS * 0.7:
                return "moderate"

        # Check daily accumulation
        daily_hours = self._daily_focus_seconds / 3600
        if daily_hours >= BURNOUT_RISK_DAILY_HOURS:
            return "moderate"

        return "none"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

productivity_engine = ProductivityEngine()
