"""
Environmental Reasoning System for Aisha AI Assistant (Phase 4 Step 5).

Understands the user's current environmental workspace state by fusing:
    - Time-of-day awareness
    - Day-of-week patterns (weekday vs. weekend)
    - Active workflow mode (from workflow_intelligence)
    - Productivity state (from productivity_cognition)
    - Desktop activity (from desktop_awareness)

Derives a coherent "environmental mode" that AISHA uses to calibrate
her behavior, tone, and level of engagement.

Environmental Modes:
    morning_start    -- early morning, starting the day
    deep_work        -- sustained focus session (code or study)
    communication    -- messaging/call-heavy period
    creative_work    -- design, writing, creative tasks
    wind_down        -- evening wind-down
    break_time       -- detected break or media consumption
    weekend_relaxed  -- weekend, lighter mode
    late_night       -- past 11 PM, quieter mode

Usage::

    from environmental_reasoning import environment

    # Get current mode
    mode = environment.get_mode()

    # Get AISHA behavioral guidance string
    guidance = environment.get_behavioral_guidance()
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Mode Definitions
# ---------------------------------------------------------------------------

_MODE_DEFINITIONS: dict[str, dict] = {
    "morning_start": {
        "label": "Morning Start",
        "description": "The day is beginning. User may need energy and orientation.",
        "aisha_tone": "Be energetic, forward-looking, and warmly welcoming.",
        "interruption_tolerance": "normal",
    },
    "deep_work": {
        "label": "Deep Work",
        "description": "Sustained focused coding or study session.",
        "aisha_tone": "Be concise, precise, and avoid unnecessary conversation.",
        "interruption_tolerance": "low",
    },
    "communication": {
        "label": "Communication Mode",
        "description": "User is in a messaging or collaboration-heavy period.",
        "aisha_tone": "Be conversational and social. Match a lighter tone.",
        "interruption_tolerance": "high",
    },
    "creative_work": {
        "label": "Creative Work",
        "description": "User is in a design or creative session.",
        "aisha_tone": "Be inspiring and collaborative. Offer creative support.",
        "interruption_tolerance": "normal",
    },
    "wind_down": {
        "label": "Evening Wind-Down",
        "description": "Day is ending. User may want reflection or lighter topics.",
        "aisha_tone": "Be calm, warm, and reflective. Celebrate the day's work.",
        "interruption_tolerance": "low",
    },
    "break_time": {
        "label": "Break Time",
        "description": "User appears to be on a break or consuming media.",
        "aisha_tone": "Be light, casual, and non-demanding.",
        "interruption_tolerance": "normal",
    },
    "weekend_relaxed": {
        "label": "Weekend / Relaxed",
        "description": "Weekend mode — a lighter, more personal tone is appropriate.",
        "aisha_tone": "Be friendly and personal. Less task-oriented.",
        "interruption_tolerance": "normal",
    },
    "late_night": {
        "label": "Late Night",
        "description": "Past 11 PM. User may be tired or winding down.",
        "aisha_tone": "Be calm, gentle, and brief. Encourage rest if appropriate.",
        "interruption_tolerance": "low",
    },
    "general": {
        "label": "General",
        "description": "Standard working state.",
        "aisha_tone": "Be helpful, attentive, and balanced.",
        "interruption_tolerance": "normal",
    },
}


# ---------------------------------------------------------------------------
# Environmental Reasoning Engine
# ---------------------------------------------------------------------------

class EnvironmentalReasoning:
    """
    Fuses time, activity, and productivity signals into an environmental mode.

    Drives AISHA's behavioral calibration — tone, response length, and
    interruption tolerance.
    """

    def __init__(self) -> None:
        self._current_mode: str = "general"
        self._mode_start: datetime = datetime.now()
        print("  [Environment] Reasoning System initialized")

    def update(self, desktop_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Re-evaluate the environmental mode.

        Fuses all available signals into a coherent mode.
        """
        now = datetime.now()
        hour = now.hour
        is_weekend = now.weekday() >= 5

        # Pull workflow and productivity context
        workflow_name = None
        burnout_risk = "none"
        is_fragmented = False
        current_category = "other"

        if desktop_snapshot:
            current_category = desktop_snapshot.get("category", "other")
            workflow_name = desktop_snapshot.get("workflow")

        try:
            from productivity_cognition import productivity_engine
            burnout_risk = productivity_engine.get_burnout_risk()
            is_fragmented = productivity_engine.is_fragmented()
        except Exception:
            pass

        try:
            from workflow_intelligence import workflow_intelligence
            workflow_data = workflow_intelligence.get_active_workflow()
            if workflow_data:
                workflow_name = workflow_data.get("name")
        except Exception:
            pass

        # Classify mode from signals
        new_mode = self._classify_mode(
            hour=hour,
            is_weekend=is_weekend,
            workflow_name=workflow_name,
            current_category=current_category,
            burnout_risk=burnout_risk,
            is_fragmented=is_fragmented,
        )

        if new_mode != self._current_mode:
            self._current_mode = new_mode
            self._mode_start = now

        defn = _MODE_DEFINITIONS.get(new_mode, _MODE_DEFINITIONS["general"])

        return {
            "mode": self._current_mode,
            "label": defn["label"],
            "description": defn["description"],
            "aisha_tone": defn["aisha_tone"],
            "interruption_tolerance": defn["interruption_tolerance"],
            "mode_since": self._mode_start.isoformat(timespec="seconds"),
            "timestamp": now.isoformat(timespec="seconds"),
        }

    def get_mode(self) -> str:
        """Return the current environmental mode name."""
        return self._current_mode

    def get_behavioral_guidance(self) -> str:
        """
        Return AISHA's behavioral tone guidance for the current mode.

        Suitable for inclusion in LLM system prompts.
        """
        defn = _MODE_DEFINITIONS.get(self._current_mode, _MODE_DEFINITIONS["general"])
        return defn["aisha_tone"]

    def get_interruption_tolerance(self) -> str:
        """Return the interruption tolerance for the current mode: low/normal/high."""
        defn = _MODE_DEFINITIONS.get(self._current_mode, _MODE_DEFINITIONS["general"])
        return defn.get("interruption_tolerance", "normal")

    def is_low_interruption(self) -> bool:
        """Return True if current mode has low interruption tolerance."""
        return self.get_interruption_tolerance() == "low"

    def get_mode_context(self) -> dict[str, Any]:
        """Return full mode context dict."""
        defn = _MODE_DEFINITIONS.get(self._current_mode, _MODE_DEFINITIONS["general"])
        now = datetime.now()
        duration_min = round((now - self._mode_start).total_seconds() / 60, 1)
        return {
            "mode": self._current_mode,
            "label": defn["label"],
            "aisha_tone": defn["aisha_tone"],
            "interruption_tolerance": defn["interruption_tolerance"],
            "duration_min": duration_min,
        }

    def get_status(self) -> dict[str, Any]:
        """Return full environmental reasoning status."""
        return {
            "current_mode": self.get_mode_context(),
            "behavioral_guidance": self.get_behavioral_guidance(),
            "is_low_interruption": self.is_low_interruption(),
        }

    # ------------------------------------------------------------------
    # Internal Classification
    # ------------------------------------------------------------------

    def _classify_mode(
        self,
        hour: int,
        is_weekend: bool,
        workflow_name: str | None,
        current_category: str,
        burnout_risk: str,
        is_fragmented: bool,
    ) -> str:
        """Classify the environmental mode from all available signals."""

        # Late night takes absolute priority
        if hour >= 23 or hour < 5:
            return "late_night"

        # Weekend light mode (unless in obvious deep work)
        if is_weekend and workflow_name not in ("deep_coding", "deep_study", "code_debug_cycle"):
            if hour >= 9 and current_category in ("media", "gaming", "other", "browsing"):
                return "weekend_relaxed"

        # Morning start
        if 5 <= hour < 10 and current_category in ("other", "browsing", "unknown"):
            return "morning_start"

        # Evening wind-down
        if 20 <= hour < 23:
            return "wind_down"

        # Deep work sessions
        if workflow_name in ("deep_coding", "deep_study", "code_debug_cycle", "research_write_loop"):
            return "deep_work"

        # Communication-heavy
        if workflow_name == "communication_heavy" or current_category == "communication":
            return "communication"

        # Creative work
        if workflow_name == "design_work" or current_category == "design":
            return "creative_work"

        # Break / media
        if current_category in ("media", "gaming"):
            return "break_time"

        return "general"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

environment = EnvironmentalReasoning()
