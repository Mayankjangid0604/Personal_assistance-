"""
Collaborative Reflection Engine for Aisha AI Assistant (Phase 7 Step 7).

Reflects on collaborative thinking patterns: reasoning summaries,
thinking pattern analysis, learning trajectory reflections, cognitive
blind-spot surfacing, and exploration suggestions.

Design principles:
    - Collaborative, non-authoritarian, supportive
    - Never says "you should think about X"
    - Always frames as invitation: "You might want to consider...",
      "An unexplored angle could be...", "Your thinking has been evolving toward..."
    - Meta-analysis of the user's exploration, not judgment of conclusions
    - Self-assessment of collaboration quality (did AISHA actually help?)

Usage::

    from collaborative_reflection import collaborative_reflection

    summary = collaborative_reflection.generate_reasoning_summary(session_context)
    patterns = collaborative_reflection.analyze_thinking_patterns(days=30)
    blind_spots = collaborative_reflection.surface_blind_spots("AI ethics", ["bias", "fairness"])
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Invitational language templates for blind spot suggestions
_BLIND_SPOT_TEMPLATES = [
    "You might want to consider exploring '{concept}' — it connects to what you've been looking at.",
    "An angle you haven't explored yet: '{concept}'.",
    "'{concept}' could offer a different perspective on this.",
    "There may be something interesting in '{concept}' that relates to your work.",
]

# Exploration suggestion templates
_EXPLORATION_TEMPLATES = [
    "Based on your interests, '{concept}' could be worth exploring.",
    "You've touched on several related ideas — '{concept}' ties some of them together.",
    "An adjacent area to what you've been researching: '{concept}'.",
]

# Collaboration quality dimensions
_QUALITY_DIMENSIONS = [
    "topic_depth",          # How deeply topics are explored
    "question_engagement",  # Ratio of questions to statements
    "concept_diversity",    # Breadth of topics covered
    "continuity",           # Connections across sessions
    "exploration_rate",     # How often new topics emerge
]


# ---------------------------------------------------------------------------
# Collaborative Reflection Engine
# ---------------------------------------------------------------------------

class CollaborativeReflection:
    """
    Reflects on collaborative thinking patterns and suggests
    under-explored areas.

    Uses knowledge_graph, research_intelligence, and cognitive_workspace
    for data.
    """

    def __init__(self) -> None:
        # Lazy imports to avoid circular dependencies
        self._kg = None
        self._research = None
        self._workspace = None
        print("  [CollaborativeReflection] Initialized")

    def _get_kg(self):
        if self._kg is None:
            from knowledge_graph import knowledge_graph
            self._kg = knowledge_graph
        return self._kg

    def _get_research(self):
        if self._research is None:
            from research_intelligence import research_intelligence
            self._research = research_intelligence
        return self._research

    def _get_workspace(self):
        if self._workspace is None:
            from cognitive_workspace import cognitive_workspace
            self._workspace = cognitive_workspace
        return self._workspace

    # ----- Reasoning Summary -----------------------------------------------

    def generate_reasoning_summary(
        self, session_context: dict[str, Any] | None = None,
    ) -> str:
        """
        Summarize a reasoning thread.

        Extracts key decision points, assumptions, and open questions
        from workspace nodes and research sessions.
        """
        parts: list[str] = []

        # From workspace context
        ws = self._get_workspace()
        active_ws = ws.get_active_workspaces()

        if active_ws:
            recent_ws = active_ws[0]
            ws_data = ws.get_workspace(recent_ws["id"])
            if ws_data:
                nodes = ws_data.get("nodes", [])
                ideas = [n for n in nodes if n.get("node_type") in ("idea", "insight")]
                questions = [n for n in nodes if n.get("node_type") == "question"]

                if ideas:
                    parts.append("Key ideas you've been developing:")
                    for idea in ideas[:3]:
                        parts.append(f"  • {idea['content'][:80]}")

                if questions:
                    parts.append("Open questions still on the table:")
                    for q in questions[:3]:
                        parts.append(f"  • {q['content'][:80]}")

        # From research sessions
        research = self._get_research()
        active_sessions = research.get_active_sessions()

        if active_sessions:
            recent = active_sessions[0]
            findings = recent.get("findings", [])
            if findings:
                parts.append(f"Recent research on '{recent.get('topic', 'unknown')}':")
                for f in findings[-3:]:
                    parts.append(f"  • {f.get('text', '')[:80]}")

        if not parts:
            return "No active reasoning threads at the moment."

        return "\n".join(parts)

    # ----- Thinking Pattern Analysis ---------------------------------------

    def analyze_thinking_patterns(
        self, days: int = 30,
    ) -> dict[str, Any]:
        """
        Meta-analysis of the user's thinking habits over time.

        Analyzes: topic frequency, depth distribution, question-to-finding
        ratio, and concept diversity.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        # Topic frequency from knowledge graph
        kg = self._get_kg()
        important_concepts = kg.get_important_concepts(top_k=10)
        topic_frequency = {
            c["concept"]: c["access_count"]
            for c in important_concepts
        }

        # Research depth distribution
        research = self._get_research()
        with get_connection() as conn:
            sessions = conn.execute(
                "SELECT depth_score, topic FROM research_sessions "
                "WHERE created_at > ? ORDER BY depth_score DESC",
                (cutoff,),
            ).fetchall()

        depth_distribution = {
            "deep": 0,     # depth > 0.7
            "moderate": 0, # 0.3 < depth <= 0.7
            "shallow": 0,  # depth <= 0.3
        }
        for s in sessions:
            d = s["depth_score"]
            if d > 0.7:
                depth_distribution["deep"] += 1
            elif d > 0.3:
                depth_distribution["moderate"] += 1
            else:
                depth_distribution["shallow"] += 1

        # Question-to-finding ratio from research
        total_questions = 0
        total_findings = 0
        for s in sessions:
            # We'd need to parse JSON, but just count sessions for now
            total_questions += 1  # placeholder; real count from parsed data
            total_findings += 1

        # Actual counts from active sessions
        active = research.get_active_sessions()
        for a in active:
            total_questions += len(a.get("questions", []))
            total_findings += len(a.get("findings", []))

        q_to_f_ratio = (
            round(total_questions / max(1, total_findings), 2)
        )

        # Concept diversity from knowledge graph
        clusters = kg.get_clusters(min_size=2)

        # Generate observations (invitational language)
        observations: list[str] = []
        if depth_distribution["deep"] > depth_distribution["shallow"]:
            observations.append(
                "Your research tends toward deep exploration — "
                "that's a valuable approach."
            )
        elif depth_distribution["shallow"] > 3:
            observations.append(
                "You've been exploring many topics at a surface level — "
                "picking one to go deeper on could be rewarding."
            )

        if q_to_f_ratio > 1.5:
            observations.append(
                "You ask a lot of questions relative to findings — "
                "that curiosity-driven approach often leads to insights."
            )
        elif q_to_f_ratio < 0.3 and total_findings > 0:
            observations.append(
                "You've been gathering many findings — "
                "pausing to ask 'what's still uncertain?' might open new angles."
            )

        if len(clusters) > 3:
            observations.append(
                "Your knowledge spans several distinct topic clusters — "
                "look for unexpected bridges between them."
            )

        return {
            "topic_frequency": topic_frequency,
            "depth_distribution": depth_distribution,
            "question_to_finding_ratio": q_to_f_ratio,
            "concept_clusters": len(clusters),
            "observations": observations,
            "period_days": days,
        }

    # ----- Blind Spot Detection --------------------------------------------

    def surface_blind_spots(
        self,
        topic: str,
        explored_aspects: list[str] | None = None,
    ) -> list[str]:
        """
        Identify potentially unexplored angles on a topic.

        Compares explored aspects against knowledge graph neighbors
        to find gaps.
        """
        kg = self._get_kg()
        explored = set(a.lower() for a in (explored_aspects or []))

        # Get neighbors of the topic in the knowledge graph
        neighbors = kg.get_neighbors(topic)

        # Find neighbors not yet explored
        unexplored = []
        for n in neighbors:
            concept = n["concept"]
            if concept.lower() not in explored and concept.lower() != topic.lower():
                unexplored.append(concept)

        # Generate invitational suggestions
        suggestions: list[str] = []
        import random
        for concept in unexplored[:4]:
            template = random.choice(_BLIND_SPOT_TEMPLATES)
            suggestions.append(template.format(concept=concept))

        # If no graph data, offer generic prompts
        if not suggestions:
            suggestions = [
                f"What assumptions are you making about '{topic}'?",
                f"Who might see '{topic}' differently from you?",
                f"What's the version of '{topic}' you haven't considered?",
            ]

        return suggestions[:4]  # Never overwhelm

    # ----- Exploration Suggestions -----------------------------------------

    def suggest_explorations(self, topic: str) -> list[str]:
        """
        Recommend related areas worth exploring.

        Based on knowledge graph adjacency and semantic memory.
        """
        kg = self._get_kg()
        suggestions: list[str] = []

        # Knowledge graph neighbors
        neighbors = kg.get_neighbors(topic)
        import random
        for n in neighbors[:3]:
            template = random.choice(_EXPLORATION_TEMPLATES)
            suggestions.append(template.format(concept=n["concept"]))

        # Semantic memory connections
        try:
            from semantic_memory import semantic_memory
            related = semantic_memory.recall(topic, top_k=3, min_score=0.1)
            for mem in related:
                text = mem["text"][:60]
                suggestions.append(
                    f"You mentioned something related earlier: '{text}...' — "
                    "there might be a connection worth revisiting."
                )
        except Exception:
            pass

        return suggestions[:5]

    # ----- Learning Trajectory ---------------------------------------------

    def get_learning_trajectory(
        self, topic: str | None = None,
    ) -> dict[str, Any]:
        """
        Track how the user's understanding has evolved over time.

        Looks at concept access frequency and depth changes.
        """
        kg = self._get_kg()

        if topic:
            # Topic-specific trajectory
            concept = kg.get_concept(topic)
            if not concept:
                return {
                    "topic": topic,
                    "status": "not_found",
                    "observation": f"'{topic}' hasn't appeared in your explorations yet.",
                }

            neighbors = kg.get_neighbors(topic)

            return {
                "topic": topic,
                "access_count": concept.get("access_count", 0),
                "importance": concept.get("importance", 0),
                "connections": len(neighbors),
                "connected_concepts": [n["concept"] for n in neighbors[:5]],
                "observation": (
                    f"You've engaged with '{topic}' {concept.get('access_count', 0)} times, "
                    f"and it connects to {len(neighbors)} other concepts in your knowledge."
                ),
            }

        # General trajectory
        important = kg.get_important_concepts(top_k=5)
        clusters = kg.get_clusters(min_size=2)

        observation_parts: list[str] = []
        if important:
            top_concepts = ", ".join(c["concept"] for c in important[:3])
            observation_parts.append(
                f"Your most-explored concepts are: {top_concepts}."
            )
        if clusters:
            observation_parts.append(
                f"Your knowledge organizes into {len(clusters)} "
                f"distinct topic cluster(s)."
            )

        return {
            "top_concepts": important,
            "cluster_count": len(clusters),
            "observation": " ".join(observation_parts) if observation_parts else "Your knowledge graph is still growing.",
        }

    # ----- Collaboration Quality -------------------------------------------

    def get_collaboration_quality(self) -> dict[str, Any]:
        """
        Self-assessment of how effective the collaboration has been.

        Measures depth, diversity, continuity, and engagement.
        """
        kg = self._get_kg()
        research = self._get_research()
        ws = self._get_workspace()

        # Gather metrics
        kg_status = kg.get_status()
        research_status = research.get_status()
        ws_status = ws.get_status()

        # Compute quality scores (0-1)
        topic_depth = min(1.0, research_status.get("average_depth", 0) * 2)
        concept_diversity = min(1.0, kg_status.get("total_nodes", 0) / 20)
        workspace_usage = min(1.0, ws_status.get("total_nodes", 0) / 10)
        connectivity = min(1.0, kg_status.get("total_edges", 0) / 30)

        overall = (topic_depth + concept_diversity + workspace_usage + connectivity) / 4

        return {
            "overall_score": round(overall, 3),
            "dimensions": {
                "topic_depth": round(topic_depth, 3),
                "concept_diversity": round(concept_diversity, 3),
                "workspace_usage": round(workspace_usage, 3),
                "connectivity": round(connectivity, 3),
            },
            "observation": self._quality_observation(overall),
        }

    # ----- Diagnostics -----------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return collaborative reflection diagnostic summary."""
        quality = self.get_collaboration_quality()
        return {
            "engine": "active",
            "collaboration_quality": quality["overall_score"],
            "capabilities": [
                "reasoning_summaries", "thinking_patterns",
                "blind_spot_surfacing", "exploration_suggestions",
                "learning_trajectory", "collaboration_quality",
            ],
        }

    # ----- Helpers ---------------------------------------------------------

    @staticmethod
    def _quality_observation(score: float) -> str:
        """Generate an invitational observation about collaboration quality."""
        if score > 0.7:
            return (
                "The collaboration has been productive — deep exploration "
                "across diverse topics with good conceptual connections."
            )
        elif score > 0.4:
            return (
                "There's a solid foundation of exploration here. "
                "Going deeper on a few topics or connecting more ideas "
                "could make this even richer."
            )
        elif score > 0.1:
            return (
                "The collaboration is just getting started. "
                "The more you explore, the more connections and "
                "insights will emerge."
            )
        return (
            "Start by exploring a topic that interests you — "
            "the knowledge graph will grow from there."
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

collaborative_reflection = CollaborativeReflection()
