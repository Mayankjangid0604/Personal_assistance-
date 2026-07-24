"""
Multi-Agent Cognitive System for Aisha AI Assistant (Phase 3 Step 6).

Lightweight specialist modules that enrich conversation context.
Each agent reads from memory/state and returns an AgentContribution
containing context additions and MemoryIntents.

**Key rule**: Agents NEVER write to memory directly.  They return
MemoryIntents that the CognitiveOrchestrator validates and commits.

Agents:
    MemoryAgent       -- Recalls related semantic + episodic memories
    EmotionAgent      -- Analyzes emotional patterns and continuity
    PlannerAgent      -- Checks active goals and progress
    ProductivityAgent -- Leverages desktop awareness for contextual help
    ResearchAgent     -- Enriches with learned knowledge

Usage::

    from cognitive_agents import agent_system

    # Get contributions from all agents
    contributions = agent_system.gather(user_input, context)

    # Each contribution has:
    #   .context_additions: dict  -- extra context for brain pipeline
    #   .memory_intents: list     -- MemoryIntents for orchestrator
"""

from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Agent Contribution
# ---------------------------------------------------------------------------

@dataclass
class AgentContribution:
    """Result from a cognitive agent."""
    agent_name: str
    context_additions: dict[str, Any] = field(default_factory=dict)
    memory_intents: list[dict] = field(default_factory=list)
    prompt_fragment: str = ""    # Extra text for LLM system prompt


# ---------------------------------------------------------------------------
# Base Agent
# ---------------------------------------------------------------------------

class CognitiveAgent(ABC):
    """Abstract base for cognitive agents."""

    name: str = "base"

    @abstractmethod
    def contribute(
        self, user_input: str, context: dict[str, Any],
    ) -> AgentContribution:
        """Analyze input and return context enrichments + memory intents."""
        ...


# ---------------------------------------------------------------------------
# Memory Agent
# ---------------------------------------------------------------------------

class MemoryAgent(CognitiveAgent):
    """Recalls related memories to enrich conversation context."""

    name = "memory"

    def contribute(
        self, user_input: str, context: dict[str, Any],
    ) -> AgentContribution:
        from semantic_memory import semantic_memory

        recalled = semantic_memory.recall(user_input, top_k=3)
        intents = []

        # Boost accessed memories
        for mem in recalled:
            intents.append(
                semantic_memory.create_boost_intent(mem["id"], 0.03)
            )

        # Build context
        if recalled:
            memory_context = "Related memories:\n"
            for mem in recalled:
                memory_context += f"  - {mem['text'][:80]} (score: {mem['final_score']})\n"
        else:
            memory_context = ""

        return AgentContribution(
            agent_name=self.name,
            context_additions={"recalled_memories": recalled},
            memory_intents=intents,
            prompt_fragment=memory_context,
        )


# ---------------------------------------------------------------------------
# Emotion Agent
# ---------------------------------------------------------------------------

class EmotionAgent(CognitiveAgent):
    """Analyzes emotional patterns and continuity."""

    name = "emotion"

    def contribute(
        self, user_input: str, context: dict[str, Any],
    ) -> AgentContribution:
        from episodic_memory import episodic_memory

        arc = episodic_memory.get_emotional_arc(days=7)
        fragment = ""

        if arc["trend"] == "declining":
            fragment = (
                "The user has been experiencing a difficult period emotionally. "
                "Be extra supportive and empathetic."
            )
        elif arc["trend"] == "improving":
            fragment = (
                "The user's mood has been improving recently. "
                "Acknowledge their progress positively."
            )

        return AgentContribution(
            agent_name=self.name,
            context_additions={
                "emotional_arc": arc,
                "emotional_trend": arc["trend"],
            },
            prompt_fragment=fragment,
        )


# ---------------------------------------------------------------------------
# Planner Agent
# ---------------------------------------------------------------------------

class PlannerAgent(CognitiveAgent):
    """Checks active goals and suggests progress updates."""

    name = "planner"

    def contribute(
        self, user_input: str, context: dict[str, Any],
    ) -> AgentContribution:
        from database.repositories import personality_repo

        goals = personality_repo.get_active_goals()
        fragment = ""

        if goals:
            active = goals[:3]
            fragment = "Active user goals:\n"
            for g in active:
                progress = int(g.get("progress", 0) * 100)
                fragment += f"  - {g['goal']} ({progress}% complete)\n"

        return AgentContribution(
            agent_name=self.name,
            context_additions={"active_goals": goals},
            prompt_fragment=fragment,
        )


# ---------------------------------------------------------------------------
# Productivity Agent
# ---------------------------------------------------------------------------

class ProductivityAgent(CognitiveAgent):
    """Leverages desktop awareness for contextual assistance."""

    name = "productivity"

    def contribute(
        self, user_input: str, context: dict[str, Any],
    ) -> AgentContribution:
        from desktop_awareness import desktop_awareness

        status = desktop_awareness.get_status()
        fragment = ""

        if status.get("deep_work"):
            session = status.get("session", {})
            category = session.get("category", "work")
            duration = session.get("duration_minutes", 0)
            fragment = (
                f"The user is in a deep {category} session "
                f"({duration:.0f} minutes). Keep responses focused and concise."
            )
        elif status.get("current_category") == "coding":
            fragment = "The user is currently coding. Prioritize technical accuracy."
        elif status.get("current_category") == "studying":
            fragment = "The user is studying. Be educational and supportive."

        return AgentContribution(
            agent_name=self.name,
            context_additions={"desktop_status": status},
            prompt_fragment=fragment,
        )


# ---------------------------------------------------------------------------
# Research Agent
# ---------------------------------------------------------------------------

class ResearchAgent(CognitiveAgent):
    """Enriches responses with learned topic knowledge."""

    name = "research"

    def contribute(
        self, user_input: str, context: dict[str, Any],
    ) -> AgentContribution:
        from context_tracker import extract_topics

        topics = extract_topics(user_input)
        fragment = ""

        if topics:
            from semantic_memory import semantic_memory
            # Find topic-related memories
            for topic in topics[:2]:
                related = semantic_memory.recall(topic, top_k=2)
                if related:
                    fragment += f"User has discussed '{topic}' before. "

        return AgentContribution(
            agent_name=self.name,
            context_additions={"detected_topics": topics},
            prompt_fragment=fragment,
        )


# ---------------------------------------------------------------------------
# Agent System (coordinator)
# ---------------------------------------------------------------------------

class AgentSystem:
    """
    Coordinates all cognitive agents.

    Calls each agent, collects contributions, and merges results.
    """

    def __init__(self) -> None:
        self.agents: list[CognitiveAgent] = [
            MemoryAgent(),
            EmotionAgent(),
            PlannerAgent(),
            ProductivityAgent(),
            ResearchAgent(),
        ]
        print(f"  [Agents] Initialized {len(self.agents)} cognitive agents")

    def gather(
        self, user_input: str, context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Gather contributions from all agents.

        Returns:
            context_additions: merged dict of all context additions
            memory_intents:    flattened list of all MemoryIntents
            system_prompt:     combined prompt fragments for LLM
        """
        context = context or {}
        all_context: dict[str, Any] = {}
        all_intents: list[dict] = []
        prompt_parts: list[str] = []

        for agent in self.agents:
            try:
                contribution = agent.contribute(user_input, context)
                all_context.update(contribution.context_additions)
                all_intents.extend(contribution.memory_intents)
                if contribution.prompt_fragment:
                    prompt_parts.append(contribution.prompt_fragment)
            except Exception as e:
                # Agent failure must not crash the pipeline
                pass

        return {
            "context_additions": all_context,
            "memory_intents": all_intents,
            "system_prompt": "\n".join(prompt_parts) if prompt_parts else "",
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

agent_system = AgentSystem()
