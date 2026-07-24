"""Reflective Cognition Engine for Aisha AI Assistant (Phase 5 Step 3,
updated Phase 6 Step 4 with LLM-powered insights,
updated Phase 7 Step 7 with collaborative thinking insights).

Generates high-level, non-judgmental cognitive insights by synthesizing
signals from routine_intelligence, behavioral_model, cognitive_planner,
episodic_memory, project_cognition, cognitive_workspace, and knowledge_graph.

Phase 7 new insight types:
    reasoning_summary    -- recognizes thinking patterns across projects
    thinking_pattern     -- cross-domain thinking observation
    learning_trajectory  -- knowledge depth evolution
    blind_spot           -- areas that haven't come up (not "missing")
    exploration_suggestion -- curiosity-driven exploration nudge

Insights feel like:
    "I've noticed you tend to explore [X] when working on [Y] —
     there might be a connection worth exploring."

NOT like:
    "You are neglecting area Z. You should study it."

Usage::

    from reflective_cognition import reflective_cognition

    insight = reflective_cognition.get_ready_insight()
    llm_insight = reflective_cognition.generate_llm_reflection()
    collab_insight = reflective_cognition.generate_collaborative_reflection()
"""

from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timedelta
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection


# ---------------------------------------------------------------------------
# Insight Templates
# ---------------------------------------------------------------------------

_GROWTH_TEMPLATES = [
    "You've had some genuinely strong focus sessions lately — that kind of sustained attention is worth recognizing.",
    "Your work rhythm has been improving over recent weeks. The consistency is showing.",
    "I've noticed you've been making steady progress on your goals. That's real.",
    "There's a clear upward trend in how deeply you've been engaging with your work.",
    "Your focus windows have been getting longer — that's meaningful growth.",
]

_PATTERN_TEMPLATES = [
    "You tend to do your best thinking in the {time_label}. It might be worth protecting that time.",
    "I've noticed a recurring pattern of deep work followed by lighter days. That's a healthy rhythm.",
    "Your most productive sessions seem to happen around {hour}:00. That's a good window to know about.",
    "There's a consistent thread in how you approach complex work — you tend to front-load the hard parts.",
    "Your energy and focus seem to follow a weekly rhythm that's worth being aware of.",
]

_NUDGE_TEMPLATES = [
    "You've been working hard lately. A slightly lighter session might actually help you go further.",
    "Sometimes the most productive thing is a genuine rest. You've earned one.",
    "It might be worth checking in on one of your goals — you've been making progress.",
    "If there's something you've been meaning to start, today might be a good moment.",
    "A brief reflection on what's going well can sometimes reframe a challenging stretch.",
]

# Phase 7: Collaborative Thinking Insight Templates
_REASONING_TEMPLATES = [
    "Across your recent projects, you tend to break problems down into smaller parts first. That's a consistent strength.",
    "I've noticed you often start with exploration before committing to an approach — that's a thoughtful pattern.",
    "Your problem-solving style seems to involve gathering context first, then iterating. It's a solid approach.",
]

_THINKING_PATTERN_TEMPLATES = [
    "I notice you often explore {domain_a} when working on {domain_b} — there might be useful connections there.",
    "Your workspaces suggest you think across domains — {domain_a} and {domain_b} seem to inform each other.",
    "There's an interesting pattern: ideas from {domain_a} keep appearing in your {domain_b} work.",
]

_LEARNING_TRAJECTORY_TEMPLATES = [
    "Your understanding of {topic} has been deepening over the past month — the quality of your questions has evolved.",
    "Looking at your research sessions, your exploration of {topic} has gotten more specific and nuanced.",
    "You've built up a good foundation in {topic} — your recent notes show real depth.",
]

_BLIND_SPOT_TEMPLATES = [
    "One area that hasn't come up in your {project} work is {gap}. It might be worth a look if it's relevant.",
    "I notice {gap} hasn't been part of your {project} exploration yet. No pressure — just noting it.",
    "There's an adjacent area ({gap}) that might connect to what you're working on in {project}.",
]

_EXPLORATION_TEMPLATES = [
    "Based on your interest in {interest}, you might find {suggestion} worth exploring.",
    "Given what you've been researching, {suggestion} could be an interesting next thread to pull.",
    "Your work on {interest} touches on {suggestion} — that might be a fruitful direction.",
]


# ---------------------------------------------------------------------------
# Reflective Cognition Engine
# ---------------------------------------------------------------------------

class ReflectiveCognition:
    """
    Synthesizes behavioral signals into human-centered reflective insights.

    Reads from: routine_intelligence, behavioral_model, cognitive_planner,
    episodic_memory (via SQLite).
    Writes to: cognitive_reflections table.
    """

    # Minimum hours between surfacing insights to the user
    INSIGHT_COOLDOWN_HOURS = 48
    # Phase 7: Collaborative insights have longer cooldown
    COLLAB_INSIGHT_COOLDOWN_HOURS = 72

    def __init__(self) -> None:
        self._last_shown_at: datetime | None = None
        self._last_collab_shown_at: datetime | None = None
        self._load_last_shown()
        print("  [Reflection] Reflective Cognition Engine initialized (Phase 7)")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_ready_insight(self) -> str | None:
        """
        Return a ready insight if one is due, or None.

        Respects the 48-hour cooldown, deep work mode,
        and emotional timing gates (Phase 6).
        """
        # Cooldown check
        if not self._is_cooldown_elapsed():
            return None

        # Emotional timing gate (Phase 6)
        try:
            from emotional_timing import emotional_timing
            if not emotional_timing.should_reflect():
                return None
        except ImportError:
            # Fallback: environmental gate only
            try:
                from environmental_reasoning import environment
                if environment.is_low_interruption():
                    return None
            except Exception:
                pass

        # Try LLM-generated insight first (Phase 6)
        llm_insight = self.generate_llm_reflection()
        if llm_insight:
            self._last_shown_at = datetime.now()
            return llm_insight

        # Try cached insight
        cached = self._get_cached_insight()
        if cached:
            self._mark_shown(cached["id"])
            self._last_shown_at = datetime.now()
            return cached["content"]

        # Generate a template-based one
        reflection = self.generate_reflection()
        if reflection:
            self._last_shown_at = datetime.now()
            return reflection

        return None

    def generate_reflection(self) -> str | None:
        """
        Generate a fresh reflective insight from available behavioral signals.

        Picks the most relevant insight type based on current signals.
        Stores to cognitive_reflections table.
        """
        insight_type, content = self._synthesize()
        if not content:
            return None

        now = datetime.now().isoformat(timespec="seconds")
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO cognitive_reflections "
                    "(insight_type, content, context_json, generated_at, "
                    "relevance_score, shown_count, last_shown_at) "
                    "VALUES (?, ?, ?, ?, ?, 1, ?)",
                    (insight_type, content, "{}", now, 0.6, now),
                )
        except Exception:
            pass

        return content

    def generate_llm_reflection(self) -> str | None:
        """
        Generate a nuanced, personalized insight using the LLM.

        Gathers behavioral signals, constructs a safety-guardrailed prompt,
        routes through llm_router, and rejects manipulation markers.
        Falls back to None (caller uses template fallback).
        """
        signals = self._gather_signals()
        if not signals:
            return None

        # Build reflection context
        context_parts = []
        if signals.get("has_positive_trend"):
            context_parts.append("User has been showing positive focus/productivity trends recently.")
        if signals.get("burnout_elevated"):
            context_parts.append("User's burnout risk is currently elevated.")
        focus_windows = signals.get("focus_windows", [])
        if focus_windows:
            w = focus_windows[0]
            context_parts.append(f"User tends to focus best around {w.get('hour', 9):02d}:00.")
        if signals.get("plan_progress"):
            context_parts.append(f"User is making progress on: {signals['plan_progress']}.")

        # Add deep personalization context
        try:
            from deep_personalization import deep_personalization
            modifiers = deep_personalization.get_prompt_modifiers()
            if modifiers:
                context_parts.append(f"Personalization context: {modifiers}")
        except Exception:
            pass

        if not context_parts:
            return None

        context_str = " ".join(context_parts)

        # Safety-guardrailed system prompt
        system_prompt = (
            "You are generating a brief, supportive reflective insight for a user "
            "based on their behavioral patterns. "
            "NEVER: guilt, pressure, diagnose, simulate therapy, create dependency, "
            "use clinical language, mention scores or metrics, or be preachy. "
            "ALWAYS: be subtle, warm, supportive, respectful of autonomy. "
            "Maximum length: 2 sentences. "
            "Write in second person ('you'). Be conversational, not formal."
        )

        user_prompt = (
            f"Based on these observations: {context_str}\n\n"
            "Generate a brief, warm reflective insight. Do not mention numbers, "
            "scores, or clinical terms. Just be supportive and observational."
        )

        try:
            from llm_router import llm_router
            response = llm_router.generate_ai_response(
                user_prompt,
                system_prompt=system_prompt,
            )
            if response and isinstance(response, str):
                # Manipulation rejection
                if self._contains_manipulation(response):
                    return None
                # Store in llm_reflections table
                self._store_llm_reflection(response, context_str)
                return response.strip()
        except Exception:
            pass

        return None

    def _contains_manipulation(self, text: str) -> bool:
        """Reject responses containing manipulation markers."""
        import re
        markers = [
            r"you (must|should|need to|have to)",
            r"i (feel|care|love|worry|am hurt)",
            r"you('re| are) (failing|disappointing|letting)",
            r"don'?t you think you (should|need)",
            r"i'?m (worried|concerned) about you",
            r"you owe",
            r"guilt",
            r"disappoint",
        ]
        lower = text.lower()
        for marker in markers:
            if re.search(marker, lower):
                return True
        return False

    def _store_llm_reflection(self, text: str, context: str) -> None:
        """Store an LLM-generated reflection in the llm_reflections table."""
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO llm_reflections "
                    "(reflection_text, context_summary, quality_score, "
                    "engagement_score, shown_count, generated_at, last_shown_at) "
                    "VALUES (?, ?, 0.7, 0.0, 1, ?, ?)",
                    (text, context, now, now),
                )
        except Exception:
            pass

    def get_context_string(self) -> str:
        """
        Return a ready insight string for LLM behavioral prompt enrichment.

        Only called if an insight is due — avoids adding noise to every turn.
        """
        return self.get_ready_insight() or ""

    def get_pending_insights(self, limit: int = 5) -> list[dict]:
        """Return stored insights not yet shown."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, insight_type, content, generated_at, shown_count "
                    "FROM cognitive_reflections "
                    "WHERE shown_count = 0 "
                    "ORDER BY relevance_score DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_all_insights(self, limit: int = 10) -> list[dict]:
        """Return all stored insights."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, insight_type, content, generated_at, shown_count "
                    "FROM cognitive_reflections "
                    "ORDER BY generated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_status(self) -> dict[str, Any]:
        """Return reflective cognition status."""
        return {
            "last_shown_at": (
                self._last_shown_at.isoformat(timespec="seconds")
                if self._last_shown_at else None
            ),
            "cooldown_elapsed": self._is_cooldown_elapsed(),
            "pending_insights": len(self.get_pending_insights()),
            "total_insights": len(self.get_all_insights()),
        }

    # ------------------------------------------------------------------
    # Insight Synthesis
    # ------------------------------------------------------------------

    def _synthesize(self) -> tuple[str, str]:
        """
        Synthesize the most relevant insight from available signals.

        Returns (insight_type, content) or ("", "") if nothing meaningful.
        """
        signals = self._gather_signals()

        # Priority 1: Growth recognition (most positive, always welcome)
        if signals.get("has_positive_trend"):
            return "growth", random.choice(_GROWTH_TEMPLATES)

        # Priority 2: Pattern insight (if a strong routine is detected)
        focus_windows = signals.get("focus_windows", [])
        if focus_windows:
            w = focus_windows[0]
            hour = w.get("hour", 9)
            time_label = self._hour_to_label(hour)
            template = random.choice(_PATTERN_TEMPLATES)
            content = template.format(
                time_label=time_label,
                hour=f"{hour:02d}",
            )
            return "pattern", content

        # Priority 3: Gentle nudge (only if burnout risk is elevated)
        if signals.get("burnout_elevated"):
            return "gentle_nudge", random.choice(_NUDGE_TEMPLATES)

        # Priority 4: Goal progress insight
        if signals.get("plan_progress"):
            goal = signals["plan_progress"]
            content = (
                f"You've been making real progress on '{goal}'. "
                "The consistency is what makes the difference."
            )
            return "growth", content

        return "", ""

    def _gather_signals(self) -> dict[str, Any]:
        """Gather signals from all behavioral sources."""
        signals: dict[str, Any] = {}

        # Behavioral model trends
        try:
            from behavioral_model import behavioral_model
            positive = behavioral_model.get_positive_trends()
            risks = behavioral_model.get_risk_trends()
            signals["has_positive_trend"] = len(positive) >= 1
            signals["has_risk_trend"] = len(risks) >= 1
        except Exception:
            pass

        # Routine focus windows
        try:
            from routine_intelligence import routine_intelligence
            windows = routine_intelligence.get_focus_windows()
            signals["focus_windows"] = [
                w for w in windows if w.get("confidence", 0) >= 0.70
            ]
        except Exception:
            pass

        # Burnout from productivity engine
        try:
            from productivity_cognition import productivity_engine
            burnout = productivity_engine.get_burnout_risk()
            signals["burnout_elevated"] = burnout in ("moderate", "high")
        except Exception:
            pass

        # Goal progress
        try:
            from cognitive_planner import cognitive_planner
            plans = cognitive_planner.get_active_plans()
            in_progress = [
                p["goal"] for p in plans
                if 0.1 < p.get("progress", 0) < 0.9
            ]
            if in_progress:
                signals["plan_progress"] = in_progress[0]
        except Exception:
            pass

        return signals

    # ------------------------------------------------------------------
    # Phase 7: Collaborative Thinking Reflections
    # ------------------------------------------------------------------

    def generate_collaborative_reflection(self) -> str | None:
        """
        Generate a collaborative thinking insight from Phase 7 sources.

        Types: reasoning_summary, thinking_pattern, learning_trajectory,
        blind_spot, exploration_suggestion.

        Has a 72h cooldown (longer than behavioral insights).
        """
        # Cooldown check
        if self._last_collab_shown_at:
            elapsed = datetime.now() - self._last_collab_shown_at
            if elapsed < timedelta(hours=self.COLLAB_INSIGHT_COOLDOWN_HOURS):
                return None

        import random

        # Try each insight type in priority order
        insight = None

        # 1. Thinking patterns (cross-domain)
        try:
            from knowledge_graph import knowledge_graph
            status = knowledge_graph.get_status()
            domains = status.get("domains", {})
            domain_list = list(domains.keys())

            if len(domain_list) >= 2:
                d_a, d_b = random.sample(domain_list, 2)
                template = random.choice(_THINKING_PATTERN_TEMPLATES)
                insight = template.format(domain_a=d_a, domain_b=d_b)
        except Exception:
            pass

        # 2. Learning trajectory
        if not insight:
            try:
                from research_intelligence import research_intelligence
                sessions = research_intelligence.get_active_sessions()
                if sessions:
                    session = sessions[0]
                    if len(session.get("findings", [])) >= 3:
                        template = random.choice(_LEARNING_TRAJECTORY_TEMPLATES)
                        insight = template.format(topic=session["topic"])
            except Exception:
                pass

        # 3. Reasoning summary
        if not insight:
            try:
                from project_cognition import project_cognition
                projects = project_cognition.get_active_projects()
                if len(projects) >= 2:
                    insight = random.choice(_REASONING_TEMPLATES)
            except Exception:
                pass

        # 4. Exploration suggestion
        if not insight:
            try:
                from knowledge_graph import knowledge_graph
                kg_status = knowledge_graph.get_status()
                if kg_status.get("node_count", 0) >= 5:
                    from research_intelligence import research_intelligence
                    sessions = research_intelligence.get_active_sessions()
                    if sessions:
                        topic = sessions[0]["topic"]
                        related = knowledge_graph.get_related_concepts(topic, depth=2)
                        if related:
                            suggestion = related[-1]["concept"]
                            template = random.choice(_EXPLORATION_TEMPLATES)
                            insight = template.format(
                                interest=topic, suggestion=suggestion
                            )
            except Exception:
                pass

        if insight:
            self._last_collab_shown_at = datetime.now()
            # Store the insight
            self._store_insight("collaborative", insight, 0.6)

        return insight

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hour_to_label(hour: int) -> str:
        if 5 <= hour < 12:
            return "morning"
        if 12 <= hour < 17:
            return "afternoon"
        if 17 <= hour < 21:
            return "evening"
        return "late night"

    def _is_cooldown_elapsed(self) -> bool:
        if self._last_shown_at is None:
            return True
        elapsed = datetime.now() - self._last_shown_at
        return elapsed >= timedelta(hours=self.INSIGHT_COOLDOWN_HOURS)

    def _get_cached_insight(self) -> dict | None:
        """Get an unshown insight from the DB."""
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT id, content FROM cognitive_reflections "
                    "WHERE shown_count = 0 "
                    "ORDER BY relevance_score DESC LIMIT 1"
                ).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def _mark_shown(self, insight_id: int) -> None:
        """Mark an insight as shown."""
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE cognitive_reflections "
                    "SET shown_count = shown_count + 1, last_shown_at = ? "
                    "WHERE id = ?",
                    (now, insight_id),
                )
        except Exception:
            pass

    def _load_last_shown(self) -> None:
        """Load last shown timestamp from DB."""
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT last_shown_at FROM cognitive_reflections "
                    "WHERE shown_count > 0 AND last_shown_at IS NOT NULL "
                    "ORDER BY last_shown_at DESC LIMIT 1"
                ).fetchone()
            if row and row["last_shown_at"]:
                self._last_shown_at = datetime.fromisoformat(row["last_shown_at"])
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

reflective_cognition = ReflectiveCognition()
