"""
Personality Adaptation Layer for Aisha AI Assistant (Phase 2 Step 5).

AISHA adapts her conversational personality over time based on:
  - User's communication style (casual/formal/mixed)
  - Preferred response length (short/normal/detailed)
  - Emotional engagement level (warm/neutral/reserved)
  - Humor receptivity
  - Formality preference
  - Time-of-day patterns

The system learns from every interaction without explicit configuration.
Preferences are persisted in SQLite with confidence scores that increase
as patterns are reinforced and decay when contradicted.

Usage::

    from personality import personality_engine

    # Get current personality profile
    profile = personality_engine.get_profile()

    # Adapt a response
    adapted = personality_engine.adapt_response("Hello!", emotion="happy")

    # Learn from interaction
    personality_engine.observe_interaction(user_input, response, emotion)
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from datetime import datetime
from typing import Any

# Ensure database package is importable
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from database.repositories import personality_repo


# ---------------------------------------------------------------------------
# Personality Dimensions
# ---------------------------------------------------------------------------

# Each dimension has a key, a range, and a default
DIMENSIONS = {
    "warmth":     {"min": 0.0, "max": 1.0, "default": 0.6},   # 0=reserved, 1=very warm
    "verbosity":  {"min": 0.0, "max": 1.0, "default": 0.5},   # 0=terse, 1=elaborate
    "formality":  {"min": 0.0, "max": 1.0, "default": 0.4},   # 0=casual, 1=formal
    "humor":      {"min": 0.0, "max": 1.0, "default": 0.3},   # 0=serious, 1=playful
    "empathy":    {"min": 0.0, "max": 1.0, "default": 0.7},   # 0=factual, 1=emotionally attuned
    "directness": {"min": 0.0, "max": 1.0, "default": 0.5},   # 0=indirect, 1=straight to the point
}


# ---------------------------------------------------------------------------
# Style Detection Signals
# ---------------------------------------------------------------------------

_CASUAL_SIGNALS = [
    "bro", "dude", "lol", "haha", "yo", "man", "sup", "bruh",
    "omg", "nah", "yep", "yea", "yeah", "nope", "k", "ok",
    "gonna", "wanna", "gotta", "kinda", "sorta", "dunno",
    "wassup", "whats up", "lmao", "xd",
]

_FORMAL_SIGNALS = [
    "sir", "ma'am", "maam", "please", "could you", "would you",
    "kindly", "thank you", "thanks", "appreciate", "if possible",
    "may i", "i would like", "i request",
]

_HUMOR_SIGNALS = [
    "lol", "haha", "lmao", "xd", "joke", "funny", "laugh",
    "rofl", "hilarious", "comedy", ":)", "😂", "😄",
]

_BRIEF_SIGNALS = [
    "short", "brief", "quick", "tldr", "concise", "keep it short",
    "just tell me", "one line", "yes or no",
]

_DETAILED_SIGNALS = [
    "explain", "elaborate", "tell me more", "in detail", "detailed",
    "go deeper", "full explanation", "teach me", "help me understand",
]


# ---------------------------------------------------------------------------
# Personality Engine
# ---------------------------------------------------------------------------

class PersonalityEngine:
    """
    Learns and adapts Aisha's conversational personality over time.

    Observations from each interaction adjust personality dimensions
    with momentum-based updates (small adjustments accumulate).
    """

    # Learning rate — how quickly preferences shift per observation
    LEARN_RATE = 0.03
    # Confidence boost per reinforcing observation
    CONFIDENCE_BOOST = 0.02
    # Confidence decay per contradicting observation
    CONFIDENCE_DECAY = 0.01

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, float]] = {}  # key -> (value, confidence)
        self._load()

    def _load(self) -> None:
        """Load personality preferences from SQLite."""
        try:
            all_prefs = personality_repo.get_all_preferences()
            for key, (value, confidence) in all_prefs.items():
                if isinstance(value, (int, float)):
                    self._cache[key] = (float(value), confidence)
            print(f"  [Personality] Loaded {len(self._cache)} preferences")
        except Exception as e:
            print(f"  [Personality] Load failed ({e}), using defaults")

    def get_dimension(self, key: str) -> float:
        """Get current value for a personality dimension."""
        if key in self._cache:
            return self._cache[key][0]
        return DIMENSIONS.get(key, {}).get("default", 0.5)

    def get_confidence(self, key: str) -> float:
        """Get confidence level for a personality dimension."""
        if key in self._cache:
            return self._cache[key][1]
        return 0.0

    def get_profile(self) -> dict[str, dict[str, float]]:
        """
        Return the full personality profile.

        Returns dict of {dimension: {"value": float, "confidence": float}}.
        """
        profile = {}
        for key, dim in DIMENSIONS.items():
            value = self.get_dimension(key)
            confidence = self.get_confidence(key)
            profile[key] = {
                "value": round(value, 3),
                "confidence": round(confidence, 3),
                "label": self._label_for(key, value),
            }
        return profile

    def _label_for(self, dimension: str, value: float) -> str:
        """Human-readable label for a dimension value."""
        labels = {
            "warmth":     {0.3: "reserved", 0.6: "friendly", 1.0: "very warm"},
            "verbosity":  {0.3: "concise", 0.6: "balanced", 1.0: "detailed"},
            "formality":  {0.3: "casual", 0.6: "balanced", 1.0: "formal"},
            "humor":      {0.3: "serious", 0.6: "lighthearted", 1.0: "playful"},
            "empathy":    {0.3: "factual", 0.6: "empathetic", 1.0: "deeply attuned"},
            "directness": {0.3: "gentle", 0.6: "balanced", 1.0: "direct"},
        }
        thresholds = labels.get(dimension, {0.3: "low", 0.6: "medium", 1.0: "high"})
        for threshold, label in sorted(thresholds.items()):
            if value <= threshold:
                return label
        return list(thresholds.values())[-1]

    # -- Learning -----------------------------------------------------------

    def observe_interaction(
        self,
        user_input: str,
        response: str,
        emotion: str = "neutral",
        handler: str = "general",
    ) -> dict[str, float]:
        """
        Learn from a single interaction, adjusting personality dimensions.

        Returns dict of {dimension: adjustment} for dimensions that changed.
        """
        lower = user_input.lower()
        adjustments = {}

        # --- Formality detection ---
        casual_count = sum(1 for s in _CASUAL_SIGNALS if s in lower)
        formal_count = sum(1 for s in _FORMAL_SIGNALS if s in lower)

        if casual_count > formal_count:
            adjustments["formality"] = -self.LEARN_RATE * min(casual_count, 3)
        elif formal_count > casual_count:
            adjustments["formality"] = self.LEARN_RATE * min(formal_count, 3)

        # --- Humor detection ---
        humor_count = sum(1 for s in _HUMOR_SIGNALS if s in lower)
        if humor_count > 0:
            adjustments["humor"] = self.LEARN_RATE * min(humor_count, 2)

        # --- Verbosity detection ---
        brief_count = sum(1 for s in _BRIEF_SIGNALS if s in lower)
        detail_count = sum(1 for s in _DETAILED_SIGNALS if s in lower)

        if brief_count > detail_count:
            adjustments["verbosity"] = -self.LEARN_RATE * min(brief_count, 2)
        elif detail_count > brief_count:
            adjustments["verbosity"] = self.LEARN_RATE * min(detail_count, 2)

        # --- Warmth from emotion ---
        if emotion in ("happy", "excited"):
            adjustments["warmth"] = self.LEARN_RATE
        elif emotion in ("sad", "stressed"):
            adjustments["empathy"] = self.LEARN_RATE

        # --- Directness from message length ---
        word_count = len(user_input.split())
        if word_count <= 3:
            adjustments["directness"] = self.LEARN_RATE * 0.5
        elif word_count >= 20:
            adjustments["directness"] = -self.LEARN_RATE * 0.5

        # --- Time-of-day warmth ---
        hour = datetime.now().hour
        if hour >= 22 or hour < 6:  # late night → warmer
            adjustments.setdefault("warmth", 0)
            adjustments["warmth"] += self.LEARN_RATE * 0.3

        # Apply adjustments
        for dim, delta in adjustments.items():
            self._adjust(dim, delta)

        return adjustments

    def _adjust(self, dimension: str, delta: float) -> None:
        """Apply a delta to a personality dimension (clamped to valid range)."""
        dim_config = DIMENSIONS.get(dimension)
        if not dim_config:
            return

        current = self.get_dimension(dimension)
        new_value = max(dim_config["min"], min(dim_config["max"], current + delta))

        # Confidence adjustment
        confidence = self.get_confidence(dimension)
        if (delta > 0 and current > 0.5) or (delta < 0 and current < 0.5):
            # Reinforcing existing direction
            confidence = min(1.0, confidence + self.CONFIDENCE_BOOST)
        else:
            confidence = max(0.0, confidence - self.CONFIDENCE_DECAY)

        self._cache[dimension] = (new_value, confidence)
        personality_repo.save_preference(dimension, new_value, confidence)

    # -- Response Adaptation ------------------------------------------------

    def adapt_response(self, response: str, emotion: str = "neutral") -> str:
        """
        Adapt a response based on the current personality profile.

        Applies warmth prefixes, verbosity trimming/expansion,
        and tone adjustments.
        """
        warmth = self.get_dimension("warmth")
        verbosity = self.get_dimension("verbosity")
        formality = self.get_dimension("formality")
        humor = self.get_dimension("humor")

        result = response

        # Warmth: add personal touches for high warmth
        if warmth > 0.7 and emotion in ("sad", "stressed"):
            warm_prefixes = [
                "I'm here for you. ",
                "I hear you. ",
                "You're not alone in this. ",
            ]
            import random
            if not any(result.startswith(p) for p in warm_prefixes):
                result = random.choice(warm_prefixes) + result

        # Verbosity: trim for low verbosity preference
        if verbosity < 0.3 and len(result) > 200:
            sentences = re.split(r'(?<=[.!?])\s+', result)
            trimmed = ""
            for s in sentences:
                if len(trimmed) + len(s) > 150:
                    break
                trimmed += (" " if trimmed else "") + s
            result = trimmed or sentences[0]

        return result

    def get_context_prompt(self) -> str:
        """
        Generate a personality context string for LLM prompts.

        This can be prepended to system prompts to guide the AI's tone.
        """
        warmth = self.get_dimension("warmth")
        verbosity = self.get_dimension("verbosity")
        formality = self.get_dimension("formality")
        humor = self.get_dimension("humor")
        empathy = self.get_dimension("empathy")

        traits = []
        if warmth > 0.6:
            traits.append("warm and caring")
        elif warmth < 0.3:
            traits.append("calm and measured")

        if formality < 0.3:
            traits.append("casual and friendly")
        elif formality > 0.7:
            traits.append("polite and professional")

        if humor > 0.5:
            traits.append("lighthearted with occasional humor")

        if empathy > 0.7:
            traits.append("emotionally attuned and supportive")

        if verbosity < 0.3:
            traits.append("concise and to-the-point")
        elif verbosity > 0.7:
            traits.append("thorough and detailed")

        if not traits:
            return ""

        return "Respond in a " + ", ".join(traits) + " manner."


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

personality_engine = PersonalityEngine()
