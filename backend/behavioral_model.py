"""
Long-Term Behavioral Modeling for Aisha AI Assistant (Phase 5 Step 2).

Tracks evolving user behavioral dimensions over weeks and months using
exponential moving averages. Detects trajectories — improving, declining,
or stable — and exposes them for reflective cognition and adaptive coaching.

Behavioral dimensions tracked:
    focus_quality       -- sustained attention capability (from productivity_cognition)
    burnout_risk_level  -- emotional load trend (0=none, 1=high)
    fragmentation       -- attention switching rate
    productivity        -- overall daily productivity score
    emotional_balance   -- proportion of positive vs. stressed emotions

Design principles:
    - Uses EMA (exponential moving average) — gradual, never reactive
    - Weekly snapshot + monthly average: no raw session data
    - Trends detected only when delta is statistically meaningful
    - Privacy: derived from aggregated categorical signals only

EventBus events:
    behavioral:positive_trend  -- measurable improvement detected
    behavioral:risk_trend      -- concerning declining trend detected

Usage::

    from behavioral_model import behavioral_model

    # Feed a productivity observation
    behavioral_model.observe(productivity_state, emotion)

    # Get current model
    model = behavioral_model.get_model()

    # Get trend summary for LLM
    summary = behavioral_model.get_trend_summary()
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


# ---------------------------------------------------------------------------
# EMA Smoothing Factors
# ---------------------------------------------------------------------------

# Weekly EMA: responds to ~7 days of data (alpha = 2 / (7+1))
_EMA_WEEK = 0.25

# Monthly EMA: responds to ~30 days of data (alpha = 2 / (30+1))
_EMA_MONTH = 0.063

# Minimum delta to call a trend meaningful
_TREND_THRESHOLD = 0.08

# Minimum observations before trends are reported
_MIN_OBSERVATIONS = 5

# Model persistence interval (write to SQLite at most every 30 minutes)
_PERSIST_INTERVAL = 1800


# ---------------------------------------------------------------------------
# Behavioral Model
# ---------------------------------------------------------------------------

class BehavioralModel:
    """
    Tracks long-term behavioral dimension trajectories using EMA.

    Persists to `behavioral_model` table. Provides trend summaries
    suitable for reflective cognition and LLM context.
    """

    # Dimensions tracked in this model
    _DIMENSIONS = [
        "focus_quality",
        "burnout_risk_level",
        "fragmentation",
        "productivity",
        "emotional_balance",
    ]

    def __init__(self) -> None:
        # In-memory state: {dimension: {week_value, month_value, observations}}
        self._state: dict[str, dict] = {
            dim: {
                "week_value": 0.5,
                "month_value": 0.5,
                "trend_direction": "stable",
                "trend_strength": 0.0,
                "observations": 0,
            }
            for dim in self._DIMENSIONS
        }

        self._last_persist_time: float = 0.0
        self._load()
        print("  [BehavioralModel] Long-Term Behavioral Model initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def observe(
        self,
        productivity_state: dict[str, Any],
        emotion: str = "neutral",
    ) -> None:
        """
        Ingest a single productivity observation and update EMA values.

        Called from `conversation_engine` after each turn (lightweight).
        """
        # Map raw values to [0,1] behavioral signals
        focus = float(productivity_state.get("focus_score", 0.5))
        burnout = self._burnout_to_float(
            productivity_state.get("burnout_risk", "none")
        )
        frag = 1.0 if productivity_state.get("is_fragmented") else 0.0
        prod = float(productivity_state.get("daily_focus_hours", 0.0))
        prod_norm = min(1.0, prod / 6.0)  # normalize: 6h = perfect productivity

        # Emotional balance: positive vs. stressed
        balance = self._emotion_to_balance(emotion)

        observations = {
            "focus_quality": focus,
            "burnout_risk_level": burnout,
            "fragmentation": frag,
            "productivity": prod_norm,
            "emotional_balance": balance,
        }

        for dim, value in observations.items():
            self._update_ema(dim, value)

        # Persist to SQLite periodically
        if time.time() - self._last_persist_time > _PERSIST_INTERVAL:
            self._persist()
            self._last_persist_time = time.time()

    def get_model(self) -> dict[str, Any]:
        """Return full behavioral model state."""
        result = {}
        for dim, state in self._state.items():
            if state["observations"] < _MIN_OBSERVATIONS:
                result[dim] = {"insufficient_data": True}
                continue
            result[dim] = {
                "week_value": round(state["week_value"], 3),
                "month_value": round(state["month_value"], 3),
                "trend_direction": state["trend_direction"],
                "trend_strength": round(state["trend_strength"], 3),
                "observations": state["observations"],
            }
        return result

    def get_trend_summary(self) -> str:
        """
        Return a concise trend summary for LLM context injection.

        Only surfaces meaningful trends (not raw numbers).
        """
        parts = []
        model = self.get_model()

        focus = model.get("focus_quality", {})
        if not focus.get("insufficient_data"):
            if focus["trend_direction"] == "improving":
                parts.append("Focus quality has been improving over recent weeks.")
            elif focus["trend_direction"] == "declining":
                parts.append("Focus quality has been declining — be gentle and supportive.")

        burnout = model.get("burnout_risk_level", {})
        if not burnout.get("insufficient_data"):
            if burnout["trend_direction"] == "improving":
                parts.append("Burnout risk has been decreasing — the user seems to be recovering well.")
            elif burnout["trend_direction"] == "declining":
                parts.append("Burnout risk has been rising over recent weeks — prioritize rest and recovery.")

        productivity = model.get("productivity", {})
        if not productivity.get("insufficient_data"):
            if productivity["trend_direction"] == "improving":
                parts.append("Productivity has been steadily improving.")

        return " ".join(parts)

    def get_positive_trends(self) -> list[str]:
        """Return list of dimension names showing positive trends."""
        return [
            dim for dim, state in self._state.items()
            if (state["trend_direction"] == "improving"
                and state["observations"] >= _MIN_OBSERVATIONS)
        ]

    def get_risk_trends(self) -> list[str]:
        """Return list of dimension names showing concerning trends."""
        return [
            dim for dim, state in self._state.items()
            if (state["trend_direction"] == "declining"
                and state["observations"] >= _MIN_OBSERVATIONS
                and state["trend_strength"] > _TREND_THRESHOLD)
        ]

    def get_status(self) -> dict[str, Any]:
        """Return full model status for API endpoint."""
        return {
            "model": self.get_model(),
            "positive_trends": self.get_positive_trends(),
            "risk_trends": self.get_risk_trends(),
            "trend_summary": self.get_trend_summary(),
        }

    # ------------------------------------------------------------------
    # EMA Updates
    # ------------------------------------------------------------------

    def _update_ema(self, dimension: str, value: float) -> None:
        """Update the weekly and monthly EMA for a dimension."""
        state = self._state[dimension]
        old_week = state["week_value"]
        old_month = state["month_value"]

        # EMA update
        new_week = _EMA_WEEK * value + (1 - _EMA_WEEK) * old_week
        new_month = _EMA_MONTH * value + (1 - _EMA_MONTH) * old_month

        state["week_value"] = new_week
        state["month_value"] = new_month
        state["observations"] += 1

        # Trend classification: compare weekly vs. monthly
        delta = new_week - new_month

        # For burnout and fragmentation, a rising delta is BAD
        if dimension in ("burnout_risk_level", "fragmentation"):
            delta = -delta

        if abs(delta) < _TREND_THRESHOLD:
            state["trend_direction"] = "stable"
        elif delta > 0:
            state["trend_direction"] = "improving"
        else:
            state["trend_direction"] = "declining"

        state["trend_strength"] = round(abs(delta), 3)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _burnout_to_float(risk: str) -> float:
        return {"none": 0.0, "low": 0.2, "moderate": 0.6, "high": 1.0}.get(risk, 0.0)

    @staticmethod
    def _emotion_to_balance(emotion: str) -> float:
        positive = {"happy", "excited", "grateful", "motivated", "content"}
        negative = {"sad", "stressed", "angry", "overwhelmed", "anxious"}
        if emotion in positive:
            return 1.0
        if emotion in negative:
            return 0.0
        return 0.5

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        """Write current model state to SQLite."""
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with get_connection() as conn:
                for dim, state in self._state.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO behavioral_model "
                        "(dimension, trend_direction, trend_strength, "
                        "week_value, month_value, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (dim, state["trend_direction"], state["trend_strength"],
                         state["week_value"], state["month_value"], now),
                    )
        except Exception:
            pass

    def _load(self) -> None:
        """Load model state from SQLite (warm start after restart)."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT dimension, trend_direction, trend_strength, "
                    "week_value, month_value FROM behavioral_model"
                ).fetchall()
            for row in rows:
                dim = row["dimension"]
                if dim in self._state:
                    self._state[dim].update({
                        "week_value": float(row["week_value"]),
                        "month_value": float(row["month_value"]),
                        "trend_direction": row["trend_direction"],
                        "trend_strength": float(row["trend_strength"]),
                        "observations": _MIN_OBSERVATIONS,  # treat as warm start
                    })
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

behavioral_model = BehavioralModel()
