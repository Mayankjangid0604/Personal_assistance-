"""
Cognitive Planning Engine for Aisha AI Assistant (Phase 3 Step 7).

Adaptive roadmap generation and goal management:
    - Long-term goal tracking with multi-step plans
    - Progress detection from conversation content
    - Dynamic plan adjustment when circumstances change
    - Contextual coaching based on activity + emotional state

Returns MemoryIntents for the CognitiveOrchestrator (no direct writes).

Usage::

    from cognitive_planner import cognitive_planner

    # Create a plan
    intent = cognitive_planner.create_plan_intent("Learn Python", steps=[...])

    # Detect progress from a conversation
    intents = cognitive_planner.detect_progress("I finished the first chapter")

    # Get active plans
    plans = cognitive_planner.get_active_plans()
"""

from __future__ import annotations

import json
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
# Progress Detection Signals
# ---------------------------------------------------------------------------

_PROGRESS_SIGNALS = [
    "finished", "completed", "done with", "learned", "understood",
    "mastered", "passed", "achieved", "got through", "figured out",
    "made progress", "moved on to", "started", "working on",
    "halfway", "almost done", "nearly finished",
]

_BLOCK_SIGNALS = [
    "stuck on", "struggling with", "can't figure out",
    "having trouble", "confused about", "lost at",
    "behind on", "falling behind",
]

_GOAL_SIGNALS = [
    "i want to learn", "my goal is", "i'm planning to",
    "i need to", "help me plan", "create a roadmap",
    "i want to achieve", "i'm working towards",
]


# ---------------------------------------------------------------------------
# Cognitive Planner
# ---------------------------------------------------------------------------

class CognitivePlanner:
    """
    Adaptive planning and goal management engine.

    Returns MemoryIntents for writes -- does NOT write directly.
    Reads from cognitive_plans table for retrieval.
    """

    def __init__(self) -> None:
        print("  [Planner] Cognitive Planner initialized")

    # ----- Plan Creation (returns MemoryIntent) ---------------------------

    def create_plan_intent(
        self,
        goal: str,
        steps: list[str] | None = None,
        context: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a MemoryIntent for a new cognitive plan.

        If steps aren't provided, generates default steps.
        """
        now = datetime.now().isoformat(timespec="seconds")

        if not steps:
            steps = self._generate_default_steps(goal)

        steps_data = [
            {"step": s, "status": "pending", "progress": 0.0}
            for s in steps
        ]

        return {
            "action": "store",
            "table": "cognitive_plans",
            "source_module": "cognitive_planner",
            "data": {
                "goal": goal,
                "steps_json": json.dumps(steps_data, ensure_ascii=False),
                "status": "active",
                "progress": 0.0,
                "adaptations": 0,
                "context": context,
                "created_at": now,
                "updated_at": now,
            },
            "importance": 0.7,
        }

    def _generate_default_steps(self, goal: str) -> list[str]:
        """Generate sensible default steps for a goal."""
        lower = goal.lower()

        if any(kw in lower for kw in ["learn", "study", "master"]):
            topic = goal.split("learn")[-1].strip() if "learn" in lower else goal
            return [
                f"Research basics of {topic}",
                f"Complete introductory material for {topic}",
                f"Practice core concepts of {topic}",
                f"Build a small project with {topic}",
                f"Review and consolidate {topic} knowledge",
            ]

        if any(kw in lower for kw in ["build", "create", "make"]):
            return [
                "Define requirements and scope",
                "Plan the architecture",
                "Implement core functionality",
                "Test and iterate",
                "Polish and ship",
            ]

        # Generic steps
        return [
            "Define what success looks like",
            "Break into manageable tasks",
            "Start with the first task",
            "Track progress regularly",
            "Review and adjust as needed",
        ]

    # ----- Progress Detection ----------------------------------------------

    def detect_progress(
        self, user_input: str, emotion: str = "neutral",
    ) -> list[dict[str, Any]]:
        """
        Detect goal progress from conversation content.

        Returns MemoryIntents for updating plan progress.
        """
        lower = user_input.lower()
        intents: list[dict] = []

        # Check for progress signals
        has_progress = any(s in lower for s in _PROGRESS_SIGNALS)
        has_block = any(s in lower for s in _BLOCK_SIGNALS)

        if not has_progress and not has_block:
            return []

        # Find active plans that might be related
        plans = self.get_active_plans()
        if not plans:
            return []

        now = datetime.now().isoformat(timespec="seconds")

        for plan in plans:
            goal_words = set(plan["goal"].lower().split())
            input_words = set(lower.split())

            # Simple relevance check: do they share topic words?
            overlap = goal_words & input_words - {
                "i", "to", "a", "the", "my", "is", "on", "in", "want",
            }
            if not overlap:
                continue

            if has_progress:
                # Increment progress
                current = plan.get("progress", 0.0)
                new_progress = min(1.0, current + 0.15)

                intents.append({
                    "action": "promote",  # reusing promote for update
                    "table": "cognitive_plans",
                    "source_module": "cognitive_planner",
                    "data": {
                        "id": plan["id"],
                        "progress": new_progress,
                        "updated_at": now,
                    },
                    "importance": 0.5,
                })

            if has_block:
                # Record adaptation needed
                intents.append({
                    "action": "boost",
                    "table": "cognitive_plans",
                    "source_module": "cognitive_planner",
                    "data": {
                        "id": plan["id"],
                        "boost": 0.0,  # no importance boost, just tracking
                        "context": f"Blocked: {user_input[:100]}",
                    },
                    "importance": 0.3,
                })

        return intents

    def detect_new_goal(self, user_input: str) -> dict[str, Any] | None:
        """
        Detect if the user is expressing a new goal.

        Returns a plan creation intent or None.
        """
        lower = user_input.lower()

        for signal in _GOAL_SIGNALS:
            if signal in lower:
                # Extract the goal text
                goal = user_input.strip()
                for prefix in _GOAL_SIGNALS:
                    if lower.startswith(prefix):
                        goal = user_input[len(prefix):].strip()
                        break

                if len(goal) > 5:
                    return self.create_plan_intent(goal)

        return None

    # ----- Retrieval (read-only) -------------------------------------------

    def get_active_plans(self) -> list[dict]:
        """Return all active cognitive plans."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, goal, steps_json, status, progress, adaptations, "
                "context, created_at, updated_at "
                "FROM cognitive_plans WHERE status = 'active' "
                "ORDER BY updated_at DESC",
            ).fetchall()

        result = []
        for row in rows:
            d = dict(row)
            try:
                d["steps"] = json.loads(d.get("steps_json", "[]"))
            except (json.JSONDecodeError, TypeError):
                d["steps"] = []
            result.append(d)
        return result

    def get_all_plans(self, limit: int = 10) -> list[dict]:
        """Return recent plans of any status."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, goal, steps_json, status, progress, adaptations, "
                "context, created_at, updated_at "
                "FROM cognitive_plans ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        result = []
        for row in rows:
            d = dict(row)
            try:
                d["steps"] = json.loads(d.get("steps_json", "[]"))
            except (json.JSONDecodeError, TypeError):
                d["steps"] = []
            result.append(d)
        return result

    def get_coaching_context(self, emotion: str = "neutral") -> str:
        """
        Generate coaching context for LLM prompts.

        Adapts coaching style based on emotional state.
        """
        plans = self.get_active_plans()
        if not plans:
            return ""

        parts = ["Active goals:"]
        for p in plans[:3]:
            progress = int(p.get("progress", 0) * 100)
            parts.append(f"  - {p['goal']} ({progress}% done)")

        # Coaching style based on emotion
        if emotion in ("stressed", "overwhelmed"):
            parts.append(
                "Coaching approach: Be gentle and encouraging. "
                "Suggest small, manageable steps."
            )
        elif emotion in ("excited", "motivated"):
            parts.append(
                "Coaching approach: Channel their energy. "
                "Suggest ambitious next steps."
            )
        elif emotion == "sad":
            parts.append(
                "Coaching approach: Acknowledge their feelings first. "
                "Goals can wait."
            )

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

cognitive_planner = CognitivePlanner()
