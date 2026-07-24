"""
Distributed Bounded Cognitive Agents for Aisha AI Assistant (Phase 8 Step 2).

Defines the six specialized sandboxed reasoning agents:
  1. Project Strategy Agent
  2. Knowledge Synthesis Agent
  3. Continuity Agent
  4. Research Orchestration Agent
  5. Productivity Optimization Agent
  6. Reflective Cognition Agent

Coordinated by the DistributedAgentSystem with evidence weighting,
confidence scoring, uncertainty tracking, and conflict arbitration.
"""

from __future__ import annotations

import os
import sys
import uuid
import logging
from datetime import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection

_log = logging.getLogger("aisha.agents")


# ---------------------------------------------------------------------------
# Sandbox Gateway Context
# ---------------------------------------------------------------------------

class AgentSandboxContext:
    """
    Read-only sandbox API gateway exposed to distributed cognitive agents.
    Prevents direct memory or state mutations, ensuring safety.
    """

    def __init__(self, user_input: str, system_context: dict[str, Any] | None = None) -> None:
        self.user_input = user_input
        self._system_context = system_context or {}

    def recall_semantic(self, query: str, limit: int = 3) -> list[dict]:
        """Query semantic memory (read-only)."""
        try:
            from semantic_memory import semantic_memory
            return semantic_memory.recall(query, top_k=limit)
        except Exception:
            return []

    def get_desktop_status(self) -> dict:
        """Get current desktop activity status (read-only)."""
        try:
            from desktop_awareness import desktop_awareness
            return desktop_awareness.get_status()
        except Exception:
            return {}

    def get_active_goals(self) -> list[dict]:
        """Get active user goals (read-only)."""
        try:
            from database.repositories import personality_repo
            return personality_repo.get_active_goals()
        except Exception:
            return []

    def get_emotional_arc(self, days: int = 7) -> dict:
        """Get the user's emotional arc over the last days (read-only)."""
        try:
            from episodic_memory import episodic_memory
            return episodic_memory.get_emotional_arc(days=days)
        except Exception:
            return {"trend": "stable", "arc": []}

    def get_active_projects(self) -> list[dict]:
        """Get active projects (read-only)."""
        try:
            from project_cognition import project_cognition
            return project_cognition.get_active_projects()
        except Exception:
            return []

    def get_project(self, project_id: int) -> dict | None:
        """Get a specific project by id (read-only)."""
        try:
            from project_cognition import project_cognition
            return project_cognition.get_project(project_id)
        except Exception:
            return None

    def get_workspace_status(self) -> dict:
        """Get cognitive workspace status (read-only)."""
        try:
            from cognitive_workspace import cognitive_workspace
            return cognitive_workspace.get_status()
        except Exception:
            return {}

    def get_research_sessions(self) -> list[dict]:
        """Get active research sessions (read-only)."""
        try:
            from research_intelligence import research_intelligence
            return research_intelligence.get_active_sessions()
        except Exception:
            return []

    def get_knowledge_graph_status(self) -> dict:
        """Get knowledge graph overview (read-only)."""
        try:
            from knowledge_graph import knowledge_graph
            return knowledge_graph.get_status()
        except Exception:
            return {}

    def extract_concepts(self, text: str) -> list[str]:
        """Extract concepts from text using knowledge graph logic (read-only)."""
        try:
            from knowledge_graph import knowledge_graph
            return knowledge_graph.extract_concepts_from_text(text)
        except Exception:
            return []

    def get_reflections(self, limit: int = 5) -> list[dict]:
        """Get recent cognitive reflections (read-only)."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM cognitive_reflections ORDER BY generated_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_device_sessions(self) -> list[dict]:
        """Get device sessions for continuity (read-only)."""
        try:
            with get_connection() as conn:
                rows = conn.execute("SELECT * FROM device_sessions").fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []


# ---------------------------------------------------------------------------
# Contribution Container
# ---------------------------------------------------------------------------

@dataclass
class BoundedAgentContribution:
    """Result returned by a sandboxed agent turn."""
    agent_name: str
    confidence: float                  # Bounded confidence [0.0, 1.0]
    uncertainty: float                 # Calculated uncertainty [0.0, 1.0]
    evidence: list[dict]               # List of weighted evidence items
    reasoning: str                     # Plain text explainability summary
    context_additions: dict[str, Any] = field(default_factory=dict)
    memory_intents: list[dict] = field(default_factory=list)
    action_intents: list[dict] = field(default_factory=list) # Centralized actions to verify/execute
    prompt_fragment: str = ""


# ---------------------------------------------------------------------------
# Base Agent Class
# ---------------------------------------------------------------------------

class BoundedCognitiveAgent(ABC):
    """Abstract base class for all Phase 8 sandboxed cognitive agents."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the agent."""
        pass

    @abstractmethod
    def contribute(self, sandbox: AgentSandboxContext) -> BoundedAgentContribution:
        """
        Analyze system state through the sandbox and return a bounded contribution.
        """
        pass


# ---------------------------------------------------------------------------
# Agent 1: Project Strategy Agent
# ---------------------------------------------------------------------------

class ProjectStrategyAgent(BoundedCognitiveAgent):
    """Analyzes conversation and suggests project strategic steps/milestones."""

    @property
    def name(self) -> str:
        return "project_strategy"

    def contribute(self, sandbox: AgentSandboxContext) -> BoundedAgentContribution:
        user_input = sandbox.user_input.lower()
        projects = sandbox.get_active_projects()
        
        evidence = []
        matching_projects = []
        
        for proj in projects:
            title = proj.get("title", "").lower()
            # Direct title match
            if title and title in user_input:
                evidence.append({"source": "exact_title_match", "weight": 0.9, "detail": title})
                matching_projects.append(proj)
            else:
                # Token overlap overlap
                title_words = set(title.split())
                input_words = set(user_input.split())
                overlap = title_words.intersection(input_words)
                if len(overlap) >= 2:
                    evidence.append({"source": "token_overlap", "weight": 0.5, "detail": f"words: {list(overlap)}"})
                    matching_projects.append(proj)

        confidence = 0.0
        reasoning = "No project-related cues matched."
        context_additions = {}
        memory_intents = []
        action_intents = []
        prompt_fragment = ""

        if matching_projects:
            # Aggregate evidence
            max_weight = max(e["weight"] for e in evidence)
            confidence = max_weight
            reasoning = f"Detected discussion related to active project(s): {', '.join(p['title'] for p in matching_projects)}."
            context_additions = {"matched_projects": matching_projects}
            
            # Suggest a strategic reminder or milestone check
            prompt_fragment = "Strategic Project Reminder: Keep in mind user's goals on: " + ", ".join(p['title'] for p in matching_projects)
            
            # Intent to boost projects in knowledge representation (Phase 8 strategy)
            for p in matching_projects:
                memory_intents.append({
                    "action": "boost",
                    "table": "knowledge_graph_nodes",
                    "data": {"concept": p["title"], "boost": 0.1}
                })
        
        uncertainty = max(0.0, 1.0 - confidence)

        return BoundedAgentContribution(
            agent_name=self.name,
            confidence=confidence,
            uncertainty=uncertainty,
            evidence=evidence,
            reasoning=reasoning,
            context_additions=context_additions,
            memory_intents=memory_intents,
            action_intents=action_intents,
            prompt_fragment=prompt_fragment
        )


# ---------------------------------------------------------------------------
# Agent 2: Knowledge Synthesis Agent
# ---------------------------------------------------------------------------

class KnowledgeSynthesisAgent(BoundedCognitiveAgent):
    """Scans for multi-domain concept linkages and suggests graph reinforcements."""

    @property
    def name(self) -> str:
        return "knowledge_synthesis"

    def contribute(self, sandbox: AgentSandboxContext) -> BoundedAgentContribution:
        user_input = sandbox.user_input
        concepts = sandbox.extract_concepts(user_input)
        
        evidence = []
        confidence = 0.0
        reasoning = "No concept clusters detected."
        context_additions = {}
        memory_intents = []
        prompt_fragment = ""

        if len(concepts) >= 2:
            confidence = min(0.9, 0.4 * len(concepts))
            evidence.append({"source": "multiple_concepts_extracted", "weight": confidence, "detail": concepts})
            reasoning = f"Extracted multiple concepts: {concepts}. Suggesting semantic graph connection check."
            context_additions = {"extracted_concepts": concepts}
            
            # Suggest linking the first two concepts
            memory_intents.append({
                "action": "store",
                "table": "knowledge_graph_edges",
                "data": {
                    "source": concepts[0],
                    "target": concepts[1],
                    "relationship": "related_to",
                    "weight": 0.5
                }
            })
            prompt_fragment = f"Semantic Synthesis Hint: Suggest connections between '{concepts[0]}' and '{concepts[1]}'."

        uncertainty = max(0.0, 1.0 - confidence)

        return BoundedAgentContribution(
            agent_name=self.name,
            confidence=confidence,
            uncertainty=uncertainty,
            evidence=evidence,
            reasoning=reasoning,
            context_additions=context_additions,
            memory_intents=memory_intents,
            prompt_fragment=prompt_fragment
        )


# ---------------------------------------------------------------------------
# Agent 3: Continuity Agent
# ---------------------------------------------------------------------------

class ContinuityAgent(BoundedCognitiveAgent):
    """Monitors device session handovers and highlights cross-device continuity."""

    @property
    def name(self) -> str:
        return "continuity"

    def contribute(self, sandbox: AgentSandboxContext) -> BoundedAgentContribution:
        user_input = sandbox.user_input.lower()
        sessions = sandbox.get_device_sessions()
        
        evidence = []
        confidence = 0.0
        reasoning = "No active device session transitions detected."
        context_additions = {}
        prompt_fragment = ""

        # Check for keywords
        continuity_keywords = ["continuity", "other device", "switch laptop", "sync state", "restore session", "continuity state"]
        matched_kws = [kw for kw in continuity_keywords if kw in user_input]
        
        if matched_kws:
            confidence = 0.9
            evidence.append({"source": "keyword_match", "weight": 0.9, "detail": matched_kws})
        elif sessions:
            # If there's an active session other than primary, check if we should prompt
            active_others = [s for s in sessions if s.get("device_name") != "primary" and s.get("session_end") is None]
            if active_others:
                confidence = 0.35
                evidence.append({"source": "active_other_device", "weight": 0.35, "detail": [s["device_name"] for s in active_others]})

        if confidence > 0:
            reasoning = "Continuity event detected: Suggesting restoration context or device synchronisation."
            context_additions = {"device_sessions": sessions}
            prompt_fragment = "Continuity restoration hint: Re-establish state from last active device session if requested."

        uncertainty = max(0.0, 1.0 - confidence)

        return BoundedAgentContribution(
            agent_name=self.name,
            confidence=confidence,
            uncertainty=uncertainty,
            evidence=evidence,
            reasoning=reasoning,
            context_additions=context_additions,
            prompt_fragment=prompt_fragment
        )


# ---------------------------------------------------------------------------
# Agent 4: Research Orchestration Agent
# ---------------------------------------------------------------------------

class ResearchOrchestrationAgent(BoundedCognitiveAgent):
    """Detects complex inputs and orchestrates research suggestions."""

    @property
    def name(self) -> str:
        return "research_orchestration"

    def contribute(self, sandbox: AgentSandboxContext) -> BoundedAgentContribution:
        user_input = sandbox.user_input.lower()
        
        evidence = []
        confidence = 0.0
        reasoning = "No deep research indicators found."
        context_additions = {}
        action_intents = []
        prompt_fragment = ""

        # Research patterns
        research_keywords = ["research", "explain", "arxiv", "paper about", "find details on", "literature search"]
        matched_kws = [kw for kw in research_keywords if kw in user_input]
        
        if matched_kws:
            confidence = 0.8
            evidence.append({"source": "research_keywords", "weight": 0.8, "detail": matched_kws})
        elif "?" in user_input and len(user_input.split()) > 8:
            # Long questions
            confidence = 0.4
            evidence.append({"source": "long_question", "weight": 0.4, "detail": "User asked a detailed question"})

        if confidence > 0:
            reasoning = "User requested a detailed research or explanation. Suggesting research intelligence tools."
            prompt_fragment = "Research Orchestration: Prompt user to start a detailed research session if they need peer-reviewed sources."
            
            # Suggest start research action (arbitrated at the system level)
            topic = sandbox.user_input[:40] + "..." if len(sandbox.user_input) > 40 else sandbox.user_input
            action_intents.append({
                "action": "recommend_research",
                "params": {"topic": topic}
            })

        uncertainty = max(0.0, 1.0 - confidence)

        return BoundedAgentContribution(
            agent_name=self.name,
            confidence=confidence,
            uncertainty=uncertainty,
            evidence=evidence,
            reasoning=reasoning,
            context_additions=context_additions,
            action_intents=action_intents,
            prompt_fragment=prompt_fragment
        )


# ---------------------------------------------------------------------------
# Agent 5: Productivity Optimization Agent
# ---------------------------------------------------------------------------

class ProductivityOptimizationAgent(BoundedCognitiveAgent):
    """Monitors deep work state, suggests break times, and gates interruptions."""

    @property
    def name(self) -> str:
        return "productivity_optimization"

    def contribute(self, sandbox: AgentSandboxContext) -> BoundedAgentContribution:
        status = sandbox.get_desktop_status()
        
        evidence = []
        confidence = 0.0
        reasoning = "Desktop status indicates normal workload."
        context_additions = {}
        action_intents = []
        prompt_fragment = ""

        if status.get("deep_work"):
            session = status.get("session", {})
            duration = session.get("duration_minutes", 0)
            
            if duration > 90:
                confidence = 0.95
                evidence.append({"source": "excessive_deep_work", "weight": 0.95, "detail": f"Duration: {duration:.0f} mins"})
                reasoning = f"User has been in deep work for {duration:.0f} minutes without a break. Burnout risk is high."
                prompt_fragment = "Productivity break reminder: Suggest a short break."
                
                # Recommend break notification action
                action_intents.append({
                    "action": "notify",
                    "params": {
                        "title": "Burnout Prevention Break",
                        "message": "You've been focused for over 90 minutes. Time to stretch your legs!"
                    }
                })
            elif duration > 45:
                confidence = 0.6
                evidence.append({"source": "moderate_deep_work", "weight": 0.6, "detail": f"Duration: {duration:.0f} mins"})
                reasoning = f"User is focused ({duration:.0f} mins). Avoid non-urgent interruptions."
                prompt_fragment = "User is focused. Respond concisely."

        uncertainty = max(0.0, 1.0 - confidence)

        return BoundedAgentContribution(
            agent_name=self.name,
            confidence=confidence,
            uncertainty=uncertainty,
            evidence=evidence,
            reasoning=reasoning,
            context_additions=context_additions,
            action_intents=action_intents,
            prompt_fragment=prompt_fragment
        )


# ---------------------------------------------------------------------------
# Agent 6: Reflective Cognition Agent
# ---------------------------------------------------------------------------

class ReflectiveCognitionAgent(BoundedCognitiveAgent):
    """Monitors user emotional trends and suggests blind spots reflections."""

    @property
    def name(self) -> str:
        return "reflective_cognition"

    def contribute(self, sandbox: AgentSandboxContext) -> BoundedAgentContribution:
        arc = sandbox.get_emotional_arc()
        reflections = sandbox.get_reflections()
        
        evidence = []
        confidence = 0.0
        reasoning = "Emotional trajectory is stable."
        context_additions = {}
        prompt_fragment = ""

        trend = arc.get("trend", "stable")
        
        if trend == "declining":
            confidence = 0.85
            evidence.append({"source": "declining_mood_trend", "weight": 0.85, "detail": "Mood trend is declining over 7 days"})
            reasoning = "User emotional arc shows signs of stress/decline. Suggest empathy tuning."
            prompt_fragment = "Empathy Tune: Prioritize emotional support and stress reduction tips."
        elif reflections:
            # Suggest surfacing a past reflection
            confidence = 0.3
            evidence.append({"source": "has_past_reflections", "weight": 0.3, "detail": f"Count: {len(reflections)}"})
            reasoning = "Past reflection insights are available."

        uncertainty = max(0.0, 1.0 - confidence)

        return BoundedAgentContribution(
            agent_name=self.name,
            confidence=confidence,
            uncertainty=uncertainty,
            evidence=evidence,
            reasoning=reasoning,
            context_additions=context_additions,
            prompt_fragment=prompt_fragment
        )


# ---------------------------------------------------------------------------
# Coordinator: Distributed Agent System
# ---------------------------------------------------------------------------

class DistributedAgentSystem:
    """
    Coordinates the distributed sandboxed agents.
    Performs conflict arbitration and collects explainability summaries.
    """

    def __init__(self) -> None:
        self.agents: list[BoundedCognitiveAgent] = [
            ProjectStrategyAgent(),
            KnowledgeSynthesisAgent(),
            ContinuityAgent(),
            ResearchOrchestrationAgent(),
            ProductivityOptimizationAgent(),
            ReflectiveCognitionAgent()
        ]
        self._arbitration_log: list[dict] = []
        print(f"  [DistributedAgents] Coordinated system active ({len(self.agents)} agents)")

    def gather(
        self, user_input: str, system_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Gather contributions from all distributed agents, runs sandboxes,
        and applies conflict arbitration on action requests.
        """
        sandbox = AgentSandboxContext(user_input, system_context)
        
        contributions: list[BoundedAgentContribution] = []
        
        # 1. Gather Bounded Contributions
        for agent in self.agents:
            try:
                contrib = agent.contribute(sandbox)
                contributions.append(contrib)
            except Exception as e:
                # Bounded agents must not crash the turn pipeline
                _log.error("Agent %s failed: %s", agent.name, e)

        # 2. Merge Context, Memory Intents, Prompt Fragments
        merged_context: dict[str, Any] = {}
        merged_intents: list[dict] = []
        prompt_parts: list[str] = []
        explainability_traces: dict[str, dict] = {}
        all_actions: list[dict] = []

        for c in contributions:
            merged_context.update(c.context_additions)
            merged_intents.extend(c.memory_intents)
            if c.prompt_fragment:
                prompt_parts.append(c.prompt_fragment)
            
            # Save explainability trace
            explainability_traces[c.agent_name] = {
                "confidence": c.confidence,
                "uncertainty": c.uncertainty,
                "evidence": c.evidence,
                "reasoning": c.reasoning
            }

            # Gather requested actions
            for act in c.action_intents:
                act["source_agent"] = c.agent_name
                act["confidence"] = c.confidence
                all_actions.append(act)

        # 3. Conflict Arbitration
        arbitrated_actions = self._arbitrate_actions(all_actions)

        return {
            "context_additions": merged_context,
            "memory_intents": merged_intents,
            "action_intents": arbitrated_actions,
            "system_prompt": "\n".join(prompt_parts) if prompt_parts else "",
            "explainability": explainability_traces,
        }

    def _arbitrate_actions(self, actions: list[dict]) -> list[dict]:
        """
        Arbitrate conflicting action requests based on confidence,
        evidence weight, and baseline priority mappings.
        """
        if not actions:
            return []

        resolved = []
        # Action classification groupings
        notify_actions = [a for a in actions if a["action"] == "notify"]
        other_actions = [a for a in actions if a["action"] != "notify"]

        # Conflict resolution for notify actions (only allow the highest confidence one)
        if notify_actions:
            # Sort by confidence DESC
            notify_actions.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
            chosen = notify_actions[0]
            resolved.append(chosen)
            
            # Log suppressed
            for supp in notify_actions[1:]:
                log_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "event": "action_conflict_suppression",
                    "suppressed_agent": supp["source_agent"],
                    "chosen_agent": chosen["source_agent"],
                    "reason": f"Notification conflict: suppressed due to lower confidence ({supp['confidence']:.2f} < {chosen['confidence']:.2f})"
                }
                self._arbitration_log.append(log_entry)
                _log.info("Arbitration: %s", log_entry["reason"])

        # Check for conflicts in other actions (e.g. focus_mode_on vs focus_mode_off)
        focus_ons = [a for a in other_actions if a["action"] == "focus_mode_on"]
        focus_offs = [a for a in other_actions if a["action"] == "focus_mode_off"]

        if focus_ons and focus_offs:
            # Sort both by confidence
            focus_ons.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
            focus_offs.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
            
            on_val = focus_ons[0]
            off_val = focus_offs[0]
            
            if on_val["confidence"] >= off_val["confidence"]:
                resolved.append(on_val)
                log_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "event": "action_conflict_suppression",
                    "suppressed_agent": off_val["source_agent"],
                    "chosen_agent": on_val["source_agent"],
                    "reason": f"Focus mode conflict: ON selected (confidence {on_val['confidence']:.2f} >= {off_val['confidence']:.2f})"
                }
                self._arbitration_log.append(log_entry)
            else:
                resolved.append(off_val)
                log_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "event": "action_conflict_suppression",
                    "suppressed_agent": on_val["source_agent"],
                    "chosen_agent": off_val["source_agent"],
                    "reason": f"Focus mode conflict: OFF selected (confidence {off_val['confidence']:.2f} > {on_val['confidence']:.2f})"
                }
                self._arbitration_log.append(log_entry)
        else:
            # Add all other non-conflicting actions
            resolved.extend(other_actions)

        return resolved

    def get_arbitration_logs(self) -> list[dict]:
        """Return history of conflict arbitration decisions."""
        return self._arbitration_log


# Singleton Export
distributed_agent_system = DistributedAgentSystem()
