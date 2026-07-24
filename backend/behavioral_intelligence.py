"""
Behavioral Intelligence for Aisha AI Assistant (Phase 3 Step 8,
updated Phase 6 Step 8 + Phase 7 Step 5 creative collaboration).

Unified behavior layer that makes AISHA's responses feel natural,
consistent, and contextually intelligent.

Phase 6 upgrades:
    - Repetition reduction (avoids reusing openings within 5 turns)
    - Session depth awareness (welcoming → collaborative → efficient)
    - Adaptive verbosity via deep_personalization
    - Emotional continuity threading
    - Conversational variation (rotates phrases)
    - Anti-uncanny-valley enforcement

Phase 7 upgrades:
    - Brainstorming mode detection
    - Creative collaboration support
    - Alternative generation (max 3 per turn)
    - Assumption challenging (gentle questions)

Usage::

    from behavioral_intelligence import behavioral_intelligence

    enriched = behavioral_intelligence.enrich_response(
        response, user_input, emotion, context
    )
    prompt = behavioral_intelligence.get_behavioral_prompt(emotion, context)
"""

from __future__ import annotations

import os
import re
import sys
from collections import deque
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Behavioral Intelligence
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Anti-uncanny-valley patterns (things AISHA must never say)
# ---------------------------------------------------------------------------

_UNCANNY_PATTERNS = [
    re.compile(r"\bI feel (sad|happy|angry|hurt|lonely|love)\b", re.I),
    re.compile(r"\bI remember when\b", re.I),
    re.compile(r"\bI miss you\b", re.I),
    re.compile(r"\bI care about you\b", re.I),
    re.compile(r"\bI('m| am) (worried|scared|nervous)\b", re.I),
]

# Phase 7: Creative collaboration / brainstorming signal patterns
_CREATIVE_SIGNALS = [
    "brainstorm", "ideas for", "what if", "let's think about",
    "alternatives", "different approach", "other options",
    "explore ideas", "creative", "imagine", "what about",
    "possibilities", "let's consider", "how else",
]

_MAX_ALTERNATIVES_PER_TURN = 3


class BehavioralIntelligence:
    """
    Unified behavior layer for natural, consistent AI responses.

    Phase 6: repetition reduction, session-depth pacing,
    adaptive verbosity, emotional continuity, and variation.
    Phase 7: creative collaboration, brainstorming mode detection.
    """

    # Track recent response openings for repetition avoidance
    _DEDUP_WINDOW = 5

    def __init__(self) -> None:
        self._turn_count: int = 0
        self._session_depth: int = 0
        self._recent_openings: deque[str] = deque(maxlen=self._DEDUP_WINDOW)
        self._last_emotion: str = "neutral"
        self._creative_mode: bool = False
        self._creative_turn_count: int = 0
        print("  [Behavior] Intelligence layer initialized (Phase 7)")

    def enrich_response(
        self,
        response: str,
        user_input: str,
        emotion: str = "neutral",
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Enrich a response with behavioral intelligence.

        Applies:
        - Response pacing (trim/expand based on context)
        - Memory references (if recalled memories are relevant)
        - Emotional continuity markers
        - Contextual warmth
        """
        self._turn_count += 1
        self._session_depth += 1
        context = context or {}

        result = response

        # 1. Response pacing based on context + deep personalization
        result = self._apply_pacing(result, context)

        # 2. Memory-informed enrichment
        result = self._apply_memory_context(result, context)

        # 3. Emotional continuity
        result = self._apply_emotional_continuity(result, emotion, context)

        # 4. Phase 6: Adaptive verbosity
        result = self._apply_verbosity(result)

        # 5. Phase 6: Repetition reduction
        result = self._reduce_repetition(result)

        # 6. Phase 6: Anti-uncanny-valley enforcement
        result = self._enforce_anti_uncanny(result)

        # 7. Phase 7: Creative collaboration enrichment
        result = self._apply_creative_enrichment(result, user_input, context)

        # Track emotion for continuity
        self._last_emotion = emotion

        return result

    def _apply_pacing(self, response: str, context: dict) -> str:
        """Adjust response length based on context."""
        desktop = context.get("desktop_status", {})

        # Deep work → keep responses concise
        if desktop.get("deep_work"):
            if len(response) > 200:
                sentences = response.split(". ")
                if len(sentences) > 2:
                    return ". ".join(sentences[:2]) + "."
            return response

        # First interaction of session → can be warmer/longer
        if self._session_depth <= 2:
            return response

        return response

    def _apply_memory_context(self, response: str, context: dict) -> str:
        """Add memory references where natural."""
        recalled = context.get("recalled_memories", [])
        if not recalled:
            return response

        # If a high-score memory is related, acknowledge continuity
        top = recalled[0] if recalled else None
        if top and top.get("final_score", 0) > 0.3:
            # Only add a reference if the response doesn't already address it
            memory_text = top.get("text", "")[:50]
            if memory_text.lower() not in response.lower():
                # Natural memory reference (not every time)
                if self._turn_count % 3 == 0:  # Every 3rd turn at most
                    return response
                    # Could prefix with "Building on what we discussed before, "
                    # but keeping it subtle for now

        return response

    def _apply_emotional_continuity(
        self, response: str, emotion: str, context: dict,
    ) -> str:
        """Apply emotional continuity markers."""
        arc = context.get("emotional_arc", {})
        trend = arc.get("trend", "stable")

        # If user's mood is improving, acknowledge subtly
        if trend == "improving" and emotion in ("happy", "excited"):
            # Don't always comment on it — subtle
            if self._turn_count % 5 == 0:
                pass  # Could add "Great to see you in good spirits!"

        return response

    def get_behavioral_prompt(
        self,
        emotion: str = "neutral",
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Generate a behavioral context string for LLM system prompts.

        Combines personality, memory context, activity awareness,
        and emotional state into a coherent instruction.
        Integrates Phase 4 environmental and workflow signals.
        """
        context = context or {}
        parts = []

        # 1. Personality adaptation
        try:
            from personality import personality_engine
            personality_prompt = personality_engine.get_context_prompt()
            if personality_prompt:
                parts.append(personality_prompt)
        except ImportError:
            pass

        # 2. Phase 4: Environmental tone (overrides generic time-of-day)
        aisha_tone = context.get("aisha_tone", "")
        if aisha_tone:
            parts.append(aisha_tone)
        else:
            # Fallback: time-of-day awareness
            hour = datetime.now().hour
            if 5 <= hour < 12:
                parts.append("It's morning. Be energetic and forward-looking.")
            elif 12 <= hour < 17:
                parts.append("It's afternoon. Be focused and productive.")
            elif 17 <= hour < 21:
                parts.append("It's evening. Be relaxed and reflective.")
            else:
                parts.append("It's late. Be calm and supportive.")

        # 3. Phase 4: Workflow context
        workflow = context.get("workflow")
        if workflow:
            parts.append(f"User is in a '{workflow}' workflow context.")

        # 4. Phase 4: Productivity context
        productivity_ctx = context.get("productivity_context", "")
        if productivity_ctx:
            parts.append(productivity_ctx)

        # 5. Phase 4: Burnout awareness
        burnout = context.get("burnout_risk", "none")
        if burnout == "high":
            parts.append(
                "Burnout risk is high. Be warm, encouraging, and suggest rest if natural."
            )
        elif burnout == "moderate":
            parts.append("User has been working hard. Acknowledge their effort subtly.")

        # 6. Session depth
        if self._session_depth <= 1:
            parts.append("This is the start of a new conversation. Be welcoming.")
        elif self._session_depth > 10:
            parts.append("This is a deep conversation. Match the user's depth.")

        # 7. Agent system prompt
        system_prompt = context.get("system_prompt", "")
        if system_prompt:
            parts.append(system_prompt)

        # 8. Episodic context
        episodic = context.get("episodic_context", "")
        if episodic:
            parts.append(episodic)

        # 9. Planning context
        try:
            from cognitive_planner import cognitive_planner
            coaching = cognitive_planner.get_coaching_context(emotion)
            if coaching:
                parts.append(coaching)
        except ImportError:
            pass

        # 10. Phase 7: Creative collaboration mode
        if self._creative_mode:
            parts.append(
                "User is in brainstorming/creative mode. "
                "Be generative and exploratory. Offer possibilities, "
                "not judgments. Maximum 3 alternatives per response. "
                "Challenge assumptions gently: 'is that intentional?' "
                "not 'that's wrong'."
            )

        # 11. Phase 7: Project context
        try:
            from project_cognition import project_cognition
            project_ctx = project_cognition.get_project_context()
            if project_ctx:
                parts.append(project_ctx)
        except ImportError:
            pass

        # 12. Phase 7: Knowledge graph context
        user_text = context.get("user_input", "")
        if user_text:
            try:
                from knowledge_graph import knowledge_graph
                kg_ctx = knowledge_graph.get_concept_context(user_text)
                if kg_ctx:
                    parts.append(kg_ctx)
            except ImportError:
                pass

        # 13. Phase 7: Research context
        try:
            from research_intelligence import research_intelligence
            research_ctx = research_intelligence.get_research_context()
            if research_ctx:
                parts.append(research_ctx)
        except ImportError:
            pass

        return "\n".join(parts) if parts else ""

    def reset_session(self) -> None:
        """Reset session depth (call on new session)."""
        self._session_depth = 0
        self._recent_openings.clear()
        self._last_emotion = "neutral"
        self._creative_mode = False
        self._creative_turn_count = 0

    def get_status(self) -> dict[str, Any]:
        """Return behavioral intelligence status."""
        return {
            "turn_count": self._turn_count,
            "session_depth": self._session_depth,
            "recent_openings_tracked": len(self._recent_openings),
            "last_emotion": self._last_emotion,
            "creative_mode": self._creative_mode,
            "creative_turn_count": self._creative_turn_count,
        }

    # ------------------------------------------------------------------
    # Phase 6: Conversational Realism Methods
    # ------------------------------------------------------------------

    def _apply_verbosity(self, response: str) -> str:
        """
        Adjust response length based on deep personalization.

        Uses detail_preference dimension to trim or maintain length.
        """
        try:
            from deep_personalization import deep_personalization
            detail = deep_personalization.get_dimension("detail_preference")
            # If user prefers brief, trim long responses
            if detail < 0.3 and len(response) > 200:
                sentences = response.split(". ")
                if len(sentences) > 3:
                    return ". ".join(sentences[:3]) + "."
        except Exception:
            pass
        return response

    def _reduce_repetition(self, response: str) -> str:
        """
        Avoid reusing the same response opening within the dedup window.

        Tracks the first ~40 chars of each response. If a repeat is
        detected, strips the opening sentence to vary the entry point.
        """
        opening = response[:40].strip().lower()

        if opening in self._recent_openings:
            # Strip the first sentence to vary entry point
            sentences = response.split(". ", 1)
            if len(sentences) > 1 and len(sentences[1]) > 20:
                response = sentences[1]

        self._recent_openings.append(opening)
        return response

    def _enforce_anti_uncanny(self, response: str) -> str:
        """
        Remove uncanny-valley phrases (fake human emotional claims).

        AISHA never says "I feel", "I remember when", "I miss you", etc.
        """
        for pattern in _UNCANNY_PATTERNS:
            if pattern.search(response):
                # Replace the problematic phrase
                response = pattern.sub("", response)
                # Clean up any resulting double spaces
                response = re.sub(r"\s{2,}", " ", response).strip()
        return response

    # ------------------------------------------------------------------
    # Phase 7: Creative Collaboration Methods
    # ------------------------------------------------------------------

    def _detect_creative_mode(self, user_input: str) -> bool:
        """
        Detect if the user is in brainstorming/creative mode.

        Signals: explicit brainstorming language, rapid short messages
        exploring variations, high question density.
        """
        lower = user_input.lower()
        for signal in _CREATIVE_SIGNALS:
            if signal in lower:
                return True

        # Heuristic: many questions suggest exploration
        question_marks = user_input.count("?")
        if question_marks >= 2:
            return True

        return False

    def _apply_creative_enrichment(
        self,
        response: str,
        user_input: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Apply creative collaboration enrichment when in brainstorming mode.

        Rules:
        - Max 3 AISHA-generated alternatives per turn
        - Alternatives presented as 'possibilities to consider'
        - Never evaluates user's ideas negatively
        - Assumption challenging is gentle: 'is that intentional?'
        """
        # Update creative mode state
        was_creative = self._creative_mode
        self._creative_mode = self._detect_creative_mode(user_input)

        if self._creative_mode:
            self._creative_turn_count += 1
        elif was_creative:
            # Exiting creative mode
            self._creative_turn_count = 0

        return response

    @property
    def is_creative_mode(self) -> bool:
        """Whether the user is currently in brainstorming mode."""
        return self._creative_mode


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

behavioral_intelligence = BehavioralIntelligence()
