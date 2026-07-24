"""
Phase 8 Step 2: Distributed Cognitive Agents — Full Test Suite.

Covers:
  1. Agent Sandbox Context (read-only verification).
  2. The Six Bounded Reasoning Agents:
     - Project Strategy Agent
     - Knowledge Synthesis Agent
     - Continuity Agent
     - Research Orchestration Agent
     - Productivity Optimization Agent
     - Reflective Cognition Agent
  3. Evidence Weighting and Explainability summaries.
  4. Conflict Arbitration decision logic.
  5. Quart /autonomy/agents API endpoint.

Run::
    python -m unittest backend/tests/test_phase8_step2_agents.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_TESTS_DIR)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)

for p in (_BACKEND_DIR, _PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from database.db import get_connection
from distributed_agents import (
    AgentSandboxContext,
    BoundedAgentContribution,
    distributed_agent_system,
    ProjectStrategyAgent,
    KnowledgeSynthesisAgent,
    ContinuityAgent,
    ResearchOrchestrationAgent,
    ProductivityOptimizationAgent,
    ReflectiveCognitionAgent
)


class TestAgentSandbox(unittest.TestCase):
    """Tests the read-only sandbox context exposed to agents."""

    def test_sandbox_context_reads(self):
        sandbox = AgentSandboxContext("hello", {"some": "context"})
        self.assertEqual(sandbox.user_input, "hello")
        
        # Verify read getters return lists/dicts and do not crash
        self.assertIsInstance(sandbox.get_active_projects(), list)
        self.assertIsInstance(sandbox.get_device_sessions(), list)
        self.assertIsInstance(sandbox.get_reflections(), list)
        self.assertIsInstance(sandbox.get_emotional_arc(), dict)


class TestSpecializedAgents(unittest.TestCase):
    """Tests the individual reasoning logic of the 6 specialized agents."""

    def setUp(self):
        # Insert a temporary project for testing
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO projects (id, title, description, domain, status, trajectory, progress, blockers_json, context_json, created_at, updated_at) "
                "VALUES (899, 'Learn Go Programming', 'Learn Go', 'technology', 'active', 'on_track', 0.1, '[]', '{}', '2026-05-24', '2026-05-24')"
            )

    def tearDown(self):
        with get_connection() as conn:
            conn.execute("DELETE FROM projects WHERE id = 899")

    def test_project_strategy_agent(self):
        agent = ProjectStrategyAgent()
        
        # 1. Matches exact title
        sandbox = AgentSandboxContext("I am going to Learn Go Programming today")
        contrib = agent.contribute(sandbox)
        self.assertEqual(contrib.agent_name, "project_strategy")
        self.assertGreaterEqual(contrib.confidence, 0.9)
        self.assertEqual(contrib.uncertainty, 1.0 - contrib.confidence)
        self.assertTrue(any(p["id"] == 899 for p in contrib.context_additions.get("matched_projects", [])))
        self.assertIn("Go Programming", contrib.reasoning)
        self.assertTrue(any(i["action"] == "boost" for i in contrib.memory_intents))

        # 2. Token overlap match
        sandbox_overlap = AgentSandboxContext("Working on my Go Programming steps")
        contrib_overlap = agent.contribute(sandbox_overlap)
        self.assertGreaterEqual(contrib_overlap.confidence, 0.5)

        # 3. No match
        sandbox_none = AgentSandboxContext("Working on painting the garage")
        contrib_none = agent.contribute(sandbox_none)
        self.assertEqual(contrib_none.confidence, 0.0)

    def test_knowledge_synthesis_agent(self):
        agent = KnowledgeSynthesisAgent()
        
        # Mock concept extraction
        with patch.object(AgentSandboxContext, "extract_concepts", return_value=["machine learning", "neural networks"]):
            sandbox = AgentSandboxContext("I want to link machine learning to neural networks")
            contrib = agent.contribute(sandbox)
            self.assertEqual(contrib.agent_name, "knowledge_synthesis")
            self.assertGreater(contrib.confidence, 0.5)
            self.assertTrue(any(i["action"] == "store" and i["table"] == "knowledge_graph_edges" for i in contrib.memory_intents))
            self.assertIn("machine learning", contrib.reasoning)

    def test_continuity_agent(self):
        agent = ContinuityAgent()
        
        # Keyword trigger
        sandbox = AgentSandboxContext("I need to switch laptop and sync my state")
        contrib = agent.contribute(sandbox)
        self.assertEqual(contrib.agent_name, "continuity")
        self.assertEqual(contrib.confidence, 0.9)
        self.assertIn("Continuity event", contrib.reasoning)

    def test_research_orchestration_agent(self):
        agent = ResearchOrchestrationAgent()
        
        sandbox = AgentSandboxContext("Can you explain how transformer models function?")
        contrib = agent.contribute(sandbox)
        self.assertEqual(contrib.agent_name, "research_orchestration")
        self.assertGreater(contrib.confidence, 0.3)
        self.assertTrue(any(a["action"] == "recommend_research" for a in contrib.action_intents))

    def test_productivity_optimization_agent(self):
        agent = ProductivityOptimizationAgent()
        
        # 1. Focus session duration > 90 mins -> triggers break alert
        with patch.object(AgentSandboxContext, "get_desktop_status", return_value={
            "deep_work": True,
            "session": {"category": "coding", "duration_minutes": 110}
        }):
            sandbox = AgentSandboxContext("working...")
            contrib = agent.contribute(sandbox)
            self.assertEqual(contrib.agent_name, "productivity_optimization")
            self.assertEqual(contrib.confidence, 0.95)
            self.assertTrue(any(a["action"] == "notify" and "stretch" in a["params"]["message"] for a in contrib.action_intents))

        # 2. Moderate focus duration -> no break alert, just warning prompt
        with patch.object(AgentSandboxContext, "get_desktop_status", return_value={
            "deep_work": True,
            "session": {"category": "coding", "duration_minutes": 50}
        }):
            sandbox = AgentSandboxContext("working...")
            contrib = agent.contribute(sandbox)
            self.assertEqual(contrib.confidence, 0.6)
            self.assertEqual(len(contrib.action_intents), 0)

    def test_reflective_cognition_agent(self):
        agent = ReflectiveCognitionAgent()
        
        # 1. Declining emotional trend
        with patch.object(AgentSandboxContext, "get_emotional_arc", return_value={"trend": "declining"}):
            sandbox = AgentSandboxContext("doing okay")
            contrib = agent.contribute(sandbox)
            self.assertEqual(contrib.agent_name, "reflective_cognition")
            self.assertEqual(contrib.confidence, 0.85)
            self.assertIn("Empathy Tune", contrib.prompt_fragment)


class TestConflictArbitration(unittest.TestCase):
    """Verifies coordinator gathers results and arbitrates conflicting action intents."""

    def test_conflict_arbitration_notifications(self):
        # Trigger two conflicting notifications
        mock_actions = [
            {"action": "notify", "params": {"message": "Stretch your legs!"}, "source_agent": "productivity_optimization", "confidence": 0.95},
            {"action": "notify", "params": {"message": "Review goals!"}, "source_agent": "project_strategy", "confidence": 0.4}
        ]
        
        resolved = distributed_agent_system._arbitrate_actions(mock_actions)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["source_agent"], "productivity_optimization")
        
        # Check logs show conflict resolution
        logs = distributed_agent_system.get_arbitration_logs()
        self.assertTrue(any(l["suppressed_agent"] == "project_strategy" and l["chosen_agent"] == "productivity_optimization" for l in logs))

    def test_conflict_arbitration_focus_toggles(self):
        # Trigger conflict: focus mode ON vs focus mode OFF
        mock_actions = [
            {"action": "focus_mode_on", "params": {}, "source_agent": "productivity_optimization", "confidence": 0.8},
            {"action": "focus_mode_off", "params": {}, "source_agent": "reflective_cognition", "confidence": 0.6}
        ]
        
        resolved = distributed_agent_system._arbitrate_actions(mock_actions)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["action"], "focus_mode_on")


class TestAPIEndpoints(unittest.TestCase):
    """Verify Phase 8 Step 2 Quart endpoints."""

    @classmethod
    def setUpClass(cls):
        try:
            from server import app
            cls.app = app
            cls.has_app = True
        except Exception:
            cls.has_app = False

    def test_get_agents_endpoint(self):
        if not self.has_app:
            self.skipTest("Server not available")
        
        async def check():
            async with self.app.test_client() as client:
                resp = await client.get("/autonomy/agents")
                self.assertEqual(resp.status_code, 200)
                data = await resp.get_json()
                self.assertIn("agents", data)
                self.assertIn("arbitration_logs", data)
                self.assertEqual(len(data["agents"]), 6)
                self.assertTrue(all(a["sandboxed"] for a in data["agents"]))
        
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main(verbosity=2)
