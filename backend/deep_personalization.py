"""
Deep Personalization Engine for Aisha AI Assistant (Phase 6 Step 1).

Extends personality.py with 6 new behavioral dimensions that adapt over
weeks and months — not minutes. These control conversational pacing,
response depth, emotional responsiveness, coaching intensity, interruption
tolerance, and long-term formality drift.

Learning rate: 0.008 (much slower than personality.py's 0.03)
Max monthly drift: 0.12 per dimension
Emotional responsiveness cap: 0.85 (prevents dependency bonding)

Signal sources:
    - Message length ratios (user vs. AISHA)
    - Response engagement patterns
    - Explicit feedback ("too long", "tell me more")
    - Emotional reciprocity signals
    - Session timing patterns
    - Interaction density

Usage::

    from deep_personalization import deep_personalization

    # Observe an interaction (called every turn)
    deep_personalization.observe(user_input, response, emotion, handler)

    # Get LLM prompt modifiers
    modifiers = deep_personalization.get_prompt_modifiers()

    # Get a specific dimension value
    pacing = deep_personalization.get_dimension("pacing")
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection

# ---------------------------------------------------------------------------
# Dimension Definitions
# ---------------------------------------------------------------------------

_DIMENSIONS: dict[str, dict] = {
    "pacing": {
        "default": 0.5, "min": 0.15, "max": 0.85,
        "description": "Conversational speed (0=deliberate, 1=rapid-fire)",
    },
    "detail_preference": {
        "default": 0.5, "min": 0.1, "max": 0.9,
        "description": "Preferred response depth (0=brief, 1=thorough)",
    },
    "emotional_responsiveness": {
        "default": 0.5, "min": 0.1, "max": 0.85,  # Capped at 0.85
        "description": "How much AISHA mirrors emotional tone",
    },
    "coaching_intensity": {
        "default": 0.4, "min": 0.05, "max": 0.8,
        "description": "How actively AISHA coaches (0=passive, 1=proactive)",
    },
    "interruption_preference": {
        "default": 0.5, "min": 0.1, "max": 0.9,
        "description": "Tolerance for AISHA-initiated contact",
    },
    "formality_drift": {
        "default": 0.4, "min": 0.1, "max": 0.9,
        "description": "Long-term conversational register",
    },
}

# Learning rate — very slow; adapts over weeks
_LEARN_RATE = 0.008

# Maximum drift per month (any dimension)
_MAX_MONTHLY_DRIFT = 0.12

# Minimum observations before dimension influences behavior
_MIN_OBSERVATIONS = 10

# Explicit feedback patterns
_BRIEF_SIGNALS = re.compile(
    r"\b(too long|shorter|brief|concise|tldr|tl;dr|keep it short|just tell me)\b",
    re.IGNORECASE,
)
_DETAIL_SIGNALS = re.compile(
    r"\b(tell me more|elaborate|explain more|go deeper|in detail|detailed)\b",
    re.IGNORECASE,
)
_CASUAL_SIGNALS = re.compile(
    r"\b(lol|haha|bro|dude|yo|nah|yep|gonna|wanna|xd|lmao)\b",
    re.IGNORECASE,
)
_FORMAL_SIGNALS = re.compile(
    r"\b(could you please|would you kindly|i would appreciate|thank you very much)\b",
    re.IGNORECASE,
)


class DeepPersonalization:
    """
    Long-term behavioral personalization across 6 interaction dimensions.

    Adapts gradually over weeks. Bounded, explainable, psychologically safe.
    """

    def __init__(self) -> None:
        self._state: dict[str, dict] = {}
        self._load()
        print("  [DeepPersona] Deep Personalization Engine initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def observe(
        self,
        user_input: str,
        response: str,
        emotion: str = "neutral",
        handler: str = "general",
    ) -> None:
        """
        Learn from a single interaction turn. Called every turn.

        Extracts implicit and explicit signals to nudge dimensions.
        """
        signals = self._extract_signals(user_input, response, emotion, handler)

        for dim, nudge in signals.items():
            if dim in self._state:
                self._apply_nudge(dim, nudge)

        # Persist periodically (every 20 observations)
        total_obs = sum(s["observations"] for s in self._state.values())
        if total_obs % 20 == 0:
            self._persist()

    def get_dimension(self, dimension: str) -> float:
        """Return the current value of a dimension (0.0–1.0)."""
        state = self._state.get(dimension)
        if not state or state["observations"] < _MIN_OBSERVATIONS:
            return _DIMENSIONS.get(dimension, {}).get("default", 0.5)
        return state["value"]

    def get_confidence(self, dimension: str) -> float:
        """Return confidence for a dimension (0.0–1.0)."""
        return self._state.get(dimension, {}).get("confidence", 0.1)

    def get_all_dimensions(self) -> dict[str, dict]:
        """Return all dimension values with confidence."""
        result = {}
        for dim, defn in _DIMENSIONS.items():
            state = self._state.get(dim, {})
            has_data = state.get("observations", 0) >= _MIN_OBSERVATIONS
            result[dim] = {
                "value": round(state.get("value", defn["default"]), 3) if has_data
                         else defn["default"],
                "confidence": round(state.get("confidence", 0.1), 3),
                "observations": state.get("observations", 0),
                "description": defn["description"],
            }
        return result

    def get_prompt_modifiers(self) -> str:
        """
        Return a context string for LLM prompt injection.

        Only surfaces dimensions with sufficient confidence.
        """
        parts = []

        pacing = self.get_dimension("pacing")
        detail = self.get_dimension("detail_preference")
        emo = self.get_dimension("emotional_responsiveness")
        coaching = self.get_dimension("coaching_intensity")
        formality = self.get_dimension("formality_drift")

        if self.get_confidence("detail_preference") > 0.3:
            if detail < 0.3:
                parts.append("User prefers brief, concise responses.")
            elif detail > 0.7:
                parts.append("User appreciates detailed, thorough explanations.")

        if self.get_confidence("emotional_responsiveness") > 0.3:
            if emo > 0.65:
                parts.append("User responds well to emotionally warm, empathetic tone.")
            elif emo < 0.3:
                parts.append("User prefers a more factual, less emotionally expressive tone.")

        if self.get_confidence("formality_drift") > 0.3:
            if formality < 0.3:
                parts.append("User gravitates toward casual, informal conversation.")
            elif formality > 0.7:
                parts.append("User prefers a more professional, polished tone.")

        if self.get_confidence("coaching_intensity") > 0.3:
            if coaching < 0.2:
                parts.append("User prefers minimal coaching — assist when asked.")
            elif coaching > 0.6:
                parts.append("User is receptive to proactive guidance and suggestions.")

        return " ".join(parts)

    def override_dimension(self, dimension: str, direction: str) -> dict:
        """
        Explicit user override: shift a dimension immediately.

        direction: "more" or "less"
        """
        if dimension not in self._state:
            return {"status": "error", "error": f"Unknown dimension: {dimension}"}

        shift = 0.1 if direction == "more" else -0.1
        state = self._state[dimension]
        defn = _DIMENSIONS[dimension]
        new_val = max(defn["min"], min(defn["max"], state["value"] + shift))
        state["value"] = new_val
        state["confidence"] = min(1.0, state["confidence"] + 0.1)
        self._persist()

        return {
            "status": "ok",
            "dimension": dimension,
            "new_value": round(new_val, 3),
            "direction": direction,
        }

    def get_status(self) -> dict[str, Any]:
        """Return full deep personalization status."""
        return {
            "dimensions": self.get_all_dimensions(),
            "prompt_modifiers": self.get_prompt_modifiers(),
            "learning_rate": _LEARN_RATE,
            "max_monthly_drift": _MAX_MONTHLY_DRIFT,
        }

    # ------------------------------------------------------------------
    # Signal Extraction
    # ------------------------------------------------------------------

    def _extract_signals(
        self,
        user_input: str,
        response: str,
        emotion: str,
        handler: str,
    ) -> dict[str, float]:
        """Extract implicit and explicit personalization signals."""
        signals: dict[str, float] = {}
        user_len = len(user_input)
        resp_len = len(response)

        # Pacing: short user messages → user prefers rapid exchange
        if user_len < 20:
            signals["pacing"] = 0.7
        elif user_len > 200:
            signals["pacing"] = 0.3

        # Detail preference: explicit feedback
        if _BRIEF_SIGNALS.search(user_input):
            signals["detail_preference"] = 0.15
        elif _DETAIL_SIGNALS.search(user_input):
            signals["detail_preference"] = 0.85
        else:
            # Implicit: long user messages suggest detail tolerance
            if user_len > 150:
                signals["detail_preference"] = 0.65
            elif user_len < 30:
                signals["detail_preference"] = 0.35

        # Emotional responsiveness: emotional engagement signals
        positive_emotions = {"happy", "excited", "grateful", "motivated"}
        negative_emotions = {"sad", "stressed", "angry", "overwhelmed", "anxious"}
        if emotion in positive_emotions:
            signals["emotional_responsiveness"] = 0.7
        elif emotion in negative_emotions:
            signals["emotional_responsiveness"] = 0.6  # Moderate — don't over-mirror

        # Formality drift
        if _CASUAL_SIGNALS.search(user_input):
            signals["formality_drift"] = 0.2
        elif _FORMAL_SIGNALS.search(user_input):
            signals["formality_drift"] = 0.8

        # Coaching intensity: task handler suggests user wants help
        if handler in ("reminder", "habit", "learning", "goal"):
            signals["coaching_intensity"] = 0.65

        return signals

    # ------------------------------------------------------------------
    # Adaptation
    # ------------------------------------------------------------------

    def _apply_nudge(self, dimension: str, target: float) -> None:
        """Apply a small nudge toward target value."""
        state = self._state[dimension]
        defn = _DIMENSIONS[dimension]
        old_val = state["value"]

        # EMA-style update
        new_val = old_val + _LEARN_RATE * (target - old_val)
        new_val = max(defn["min"], min(defn["max"], new_val))

        # Monthly drift check
        drift = abs(new_val - old_val) + state.get("drift_this_month", 0.0)
        if drift > _MAX_MONTHLY_DRIFT:
            return  # Refuse to drift further this month

        state["value"] = new_val
        state["observations"] += 1
        state["drift_this_month"] = drift

        # Confidence grows with observations (asymptotic)
        state["confidence"] = min(1.0, state["observations"] / 200.0)

        # Coaching intensity auto-reduces during burnout
        if dimension == "coaching_intensity":
            try:
                from productivity_cognition import productivity_engine
                if productivity_engine.get_burnout_risk() in ("moderate", "high"):
                    state["value"] = max(defn["min"], state["value"] - 0.02)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        """Write current state to SQLite."""
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with get_connection() as conn:
                for dim, state in self._state.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO deep_personalization "
                        "(dimension, value, confidence, observations, "
                        "drift_this_month, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (dim, state["value"], state["confidence"],
                         state["observations"], state.get("drift_this_month", 0.0),
                         now),
                    )
        except Exception:
            pass

    def _load(self) -> None:
        """Load state from SQLite or initialize defaults."""
        # Initialize defaults
        for dim, defn in _DIMENSIONS.items():
            self._state[dim] = {
                "value": defn["default"],
                "confidence": 0.1,
                "observations": 0,
                "drift_this_month": 0.0,
            }

        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT dimension, value, confidence, observations, "
                    "drift_this_month FROM deep_personalization"
                ).fetchall()
            for row in rows:
                dim = row["dimension"]
                if dim in self._state:
                    self._state[dim].update({
                        "value": float(row["value"]),
                        "confidence": float(row["confidence"]),
                        "observations": int(row["observations"]),
                        "drift_this_month": float(row["drift_this_month"]),
                    })
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

deep_personalization = DeepPersonalization()
