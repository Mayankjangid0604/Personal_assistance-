"""
Safe Autonomous Automation Governor for Aisha AI Assistant (Phase 4 Step 6).

The AutomationGovernor enforces bounded autonomy for all Phase 4 automated
actions.  It is the gatekeeper between AISHA's intent to act and actual
system execution.

Design constraints (non-negotiable):
    - Daily automation budget: max 10 automated actions/day
    - Hourly budget: max 3/hour
    - Cooldown: 10 minutes between consecutive automations
    - Confidence threshold: actions only fire if confidence >= threshold
    - Environmental gating: no automations during deep work (low interruption mode)
    - Emotional gating: no non-urgent automations when user is stressed/sad

Confidence thresholds by action risk:
    safe:     0.0 (always allow if tier permits)
    moderate: 0.65
    high:     0.90 (rare; always needs confirmation too)

Automation sources (who can request actions):
    "presence"     -- presence engine (proactive nudges)
    "productivity" -- productivity engine (break suggestions)
    "workflow"     -- workflow intelligence (workflow transitions)
    "planner"      -- cognitive planner (goal reminders)
    "user"         -- explicit user request (bypass most gates)

Usage::

    from automation_governor import automation_governor

    # Check if an automation is permitted
    allowed, reason = automation_governor.can_automate(
        source="productivity",
        action="notify",
        confidence=0.8,
        emotion="neutral",
    )

    # Record that an automation was executed
    automation_governor.record_execution(source, action)

    # Get governor status
    status = automation_governor.get_status()
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

from database.db import get_connection
from human_oversight import human_oversight


# Mirrors action risk levels from agentic_executor
_RISK_LEVELS = {
    "safe": 0,
    "moderate": 1,
    "high": 2,
}

_CONFIDENCE_THRESHOLDS = {
    "safe": 0.0,
    "moderate": 0.65,
    "high": 0.90,
}

DAILY_BUDGET = 10
HOURLY_BUDGET = 3
AUTOMATION_COOLDOWN = 600   # 10 minutes

# Emotions that suppress non-urgent automations
_SUPPRESSED_EMOTIONS = {"stressed", "sad", "angry", "overwhelmed"}

# Sources trusted to bypass certain governor rules
_TRUSTED_SOURCES = {"user"}


class AutomationGovernor:
    """
    The gatekeeper for all Phase 4 autonomous automations.

    Enforces budgets, confidence thresholds, environmental gates,
    and emotional gates to ensure AISHA remains non-intrusive.
    """

    def __init__(self) -> None:
        self._daily_count: int = 0
        self._hourly_count: int = 0
        self._last_execution_time: float = 0.0
        self._last_hour: int = datetime.now().hour
        self._last_day: int = datetime.now().day
        self._suppressed_count: int = 0
        self._execution_log: list[dict] = []

        print("  [AutoGov] Automation Governor initialized (tier=%d)" % human_oversight.get_autonomy_tier())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tier(self, tier: int) -> None:
        """Set autonomy tier (0=silent, 1=notify only, 2=normal, 3=full)."""
        human_oversight.set_autonomy_tier(tier)

    @property
    def tier(self) -> int:
        return human_oversight.get_autonomy_tier()

    def can_automate(
        self,
        source: str,
        action: str,
        confidence: float = 0.5,
        emotion: str = "neutral",
        action_risk: str = "safe",
        urgency: str = "normal",
    ) -> tuple[bool, str]:
        """
        Determine if an automation is permitted right now.

        Parameters:
            source:       Who is requesting (presence, productivity, user, etc.)
            action:       Action type from agentic_executor
            confidence:   Confidence score (0.0–1.0)
            emotion:      Current user emotion
            action_risk:  'safe', 'moderate', or 'high'
            urgency:      'low', 'normal', 'high', 'urgent'

        Returns:
            (allowed: bool, reason: str)
        """
        self._reset_counters()

        # Global Interruption Check
        if human_oversight.is_paused():
            self._suppressed_count += 1
            return False, "Autonomy is globally paused (interrupted)"

        current_tier = self.tier

        # Tier 0: everything blocked
        if current_tier == 0:
            self._suppressed_count += 1
            return False, "Automation is silenced (tier=0)"

        # Tier 1: only safe actions
        if current_tier == 1 and action_risk != "safe":
            self._suppressed_count += 1
            return False, "Only safe actions allowed (tier=1)"

        # User-requested actions bypass most gates (but not tier 0 or paused)
        if source in _TRUSTED_SOURCES:
            return True, "User-requested action approved"

        # Environmental gating (deep work / low interruption)
        if urgency not in ("urgent", "high"):
            try:
                from environmental_reasoning import environment
                if environment.is_low_interruption():
                    self._suppressed_count += 1
                    return False, "Low interruption mode — automation suppressed"
            except Exception:
                pass

        # Emotional gating
        if emotion in _SUPPRESSED_EMOTIONS and urgency not in ("urgent", "high"):
            self._suppressed_count += 1
            return False, f"Emotional gating: not automating when user is {emotion}"

        # Confidence threshold
        threshold = _CONFIDENCE_THRESHOLDS.get(action_risk, 0.65)
        if confidence < threshold:
            self._suppressed_count += 1
            return False, (
                f"Confidence {confidence:.2f} below threshold {threshold:.2f} "
                f"for {action_risk} action"
            )

        # Budget checks (safe actions skip budget for tier 3)
        if action_risk != "safe" or current_tier < 3:
            if self._daily_count >= DAILY_BUDGET:
                self._suppressed_count += 1
                return False, "Daily automation budget exhausted"

            if self._hourly_count >= HOURLY_BUDGET:
                self._suppressed_count += 1
                return False, "Hourly automation budget exhausted"

        # Cooldown (only for non-safe actions)
        if action_risk != "safe":
            elapsed = time.time() - self._last_execution_time
            if elapsed < AUTOMATION_COOLDOWN and urgency not in ("urgent", "high"):
                remaining = int(AUTOMATION_COOLDOWN - elapsed)
                self._suppressed_count += 1
                return False, f"Cooldown: {remaining}s remaining"

        return True, "Approved"

    def record_execution(self, source: str, action: str, action_risk: str = "safe") -> None:
        """Record that an automation was successfully executed."""
        now = time.time()
        self._last_execution_time = now
        if action_risk != "safe":
            self._daily_count += 1
            self._hourly_count += 1

        self._execution_log.append({
            "source": source,
            "action": action,
            "risk": action_risk,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })

        # Keep log bounded
        if len(self._execution_log) > 100:
            self._execution_log = self._execution_log[-100:]

    def get_execution_log(self, limit: int = 10) -> list[dict]:
        """Return recent execution log."""
        return self._execution_log[-limit:]

    def get_status(self) -> dict[str, Any]:
        """Return full governor status."""
        return {
            "tier": self.tier,
            "daily_count": self._daily_count,
            "daily_budget": DAILY_BUDGET,
            "hourly_count": self._hourly_count,
            "hourly_budget": HOURLY_BUDGET,
            "suppressed_count": self._suppressed_count,
            "cooldown_remaining": max(
                0,
                int(AUTOMATION_COOLDOWN - (time.time() - self._last_execution_time)),
            ),
            "execution_count": len(self._execution_log),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _reset_counters(self) -> None:
        """Reset daily/hourly counters when day or hour rolls over."""
        now = datetime.now()
        if now.day != self._last_day:
            self._daily_count = 0
            self._last_day = now.day
        if now.hour != self._last_hour:
            self._hourly_count = 0
            self._last_hour = now.hour


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

automation_governor = AutomationGovernor()
