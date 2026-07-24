"""
Phase 8 Steps 3-8: Bounded Autonomous Cognitive Ecosystem — Full Test Suite.

Covers:
  - Step 3: Project Evolution (forecasting, blocker slips, trajectory).
  - Step 4: Long-Horizon Planning (multi-stage roadmap, delay propagation, revisions).
  - Step 5: Self-Organizing Knowledge (edge decay, concept merges, SQL rollbacks).
  - Step 6: Predictive Workspace Orchestration (context preloads, continuity).
  - Step 7: Explainable Autonomy System (attributions, logs, trace scoring).
  - Step 8: Ecosystem Coordination (REST Quart API endpoints).

Run::
    python -m unittest backend/tests/test_phase8_steps3_8.py
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
from human_oversight import human_oversight
from project_evolution import project_evolution
from planning_engine import planning_engine
from knowledge_organization import knowledge_organizer
from workspace_orchestration import workspace_orchestrator
from explainable_autonomy import explainability_engine


class TestProjectEvolution(unittest.TestCase):
    """Verify predictive project evolution, milestone forecasting, and trajectory slipping."""

    def setUp(self):
        # Setup test project
        now = datetime.now().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM project_milestones WHERE project_id = 801")
            conn.execute("DELETE FROM projects WHERE id = 801")
            conn.execute(
                "INSERT INTO projects (id, title, description, domain, status, trajectory, progress, blockers_json, context_json, created_at, updated_at) "
                "VALUES (801, 'Test Project', 'desc', 'software', 'active', 'on_track', 0.2, '[]', '{}', ?, ?)",
                (now, now)
            )
            conn.execute(
                "INSERT INTO project_milestones (id, project_id, title, status, progress, order_idx, created_at) "
                "VALUES (811, 801, 'Milestone 1', 'pending', 0.5, 0, ?)",
                (now,)
            )

    def tearDown(self):
        with get_connection() as conn:
            conn.execute("DELETE FROM project_milestones WHERE project_id = 801")
            conn.execute("DELETE FROM projects WHERE id = 801")

    def test_milestone_forecasting(self):
        res = project_evolution.forecast_milestones(801)
        self.assertEqual(res["project_id"], 801)
        self.assertGreater(res["velocity_per_day"], 0.0)
        self.assertEqual(len(res["forecasts"]), 1)
        self.assertIn("forecasted_completion", res["forecasts"][0])

    def test_blocker_slips_trajectory(self):
        # Update project to add blocker
        with get_connection() as conn:
            conn.execute("UPDATE projects SET blockers_json = '[\"lacking resources\"]' WHERE id = 801")
        
        res = project_evolution.forecast_milestones(801)
        # Check trajectory changed to blocked
        with get_connection() as conn:
            row = conn.execute("SELECT trajectory FROM projects WHERE id = 801").fetchone()
            self.assertEqual(row["trajectory"], "blocked")

    def test_continuity_synthesis(self):
        res = project_evolution.synthesize_session_continuity()
        self.assertIn("handover_context", res)


class TestPlanningEngine(unittest.TestCase):
    """Verify strategic roadmap multi-stage planning and delay simulations."""

    def setUp(self):
        self.plan_id = None

    def tearDown(self):
        if self.plan_id:
            with get_connection() as conn:
                conn.execute("DELETE FROM cognitive_plans WHERE id = ?", (self.plan_id,))

    def test_plan_create_and_revisions(self):
        stages = [
            {"name": "Stage 1", "dependencies": [], "duration_days": 5, "progress": 0.0, "status": "active"},
            {"name": "Stage 2", "dependencies": ["Stage 1"], "duration_days": 10, "progress": 0.0, "status": "pending"}
        ]
        res = planning_engine.create_plan("Build Compiler", stages, "Context info")
        self.assertEqual(res["status"], "success")
        self.plan_id = res["plan_id"]
        self.assertIsNotNone(self.plan_id)

        # 1. Simulate Delay
        delay_res = planning_engine.simulate_delay(self.plan_id, 0, 5)
        self.assertEqual(delay_res["plan_id"], self.plan_id)
        self.assertEqual(delay_res["total_project_delay_days"], 5)
        self.assertIn("Stage 2", delay_res["stage_slips"])

        # 2. Revise stage progress
        rev_res = planning_engine.revise_plan(self.plan_id, 0, 1.0, "completed")
        self.assertEqual(rev_res["status"], "success")
        self.assertEqual(rev_res["overall_progress"], 0.5)
        self.assertEqual(rev_res["adaptations"], 1)


class TestSelfOrganizingKnowledge(unittest.TestCase):
    """Verify graph consolidations, singular/plural concept merging, and precise undo rollbacks."""

    def setUp(self):
        # Insert test nodes
        with get_connection() as conn:
            # Query IDs first to delete all dependent edges safely
            rows = conn.execute("SELECT id FROM knowledge_graph_nodes WHERE concept IN ('networks', 'network')").fetchall()
            node_ids = {row["id"] for row in rows} | {555, 556}
            id_list = ",".join(map(str, node_ids))
            
            conn.execute(f"DELETE FROM knowledge_graph_edges WHERE id = 557 OR source_id IN ({id_list}) OR target_id IN ({id_list})")
            conn.execute(f"DELETE FROM knowledge_graph_nodes WHERE id IN ({id_list})")
            
            conn.execute("INSERT INTO knowledge_graph_nodes (id, concept, domain, importance, access_count, context_json, created_at, last_accessed) VALUES (555, 'networks', 'tech', 0.5, 2, '{}', '2026-05-24', '2026-05-24')")
            conn.execute("INSERT INTO knowledge_graph_nodes (id, concept, domain, importance, access_count, context_json, created_at, last_accessed) VALUES (556, 'network', 'tech', 0.5, 3, '{}', '2026-05-24', '2026-05-24')")
            conn.execute("INSERT INTO knowledge_graph_edges (id, source_id, target_id, relationship, weight, evidence_count, created_at, last_reinforced) VALUES (557, 555, 556, 'related_to', 0.8, 1, '2026-05-24', '2026-05-24')")

    def tearDown(self):
        with get_connection() as conn:
            rows = conn.execute("SELECT id FROM knowledge_graph_nodes WHERE concept IN ('networks', 'network')").fetchall()
            node_ids = {row["id"] for row in rows} | {555, 556}
            id_list = ",".join(map(str, node_ids))
            
            conn.execute(f"DELETE FROM knowledge_graph_edges WHERE id = 557 OR source_id IN ({id_list}) OR target_id IN ({id_list})")
            conn.execute(f"DELETE FROM knowledge_graph_nodes WHERE id IN ({id_list})")
            # Clean action logs
            conn.execute("DELETE FROM autonomy_audit_log WHERE action LIKE '%merge_concepts%' OR action LIKE '%decay_edges%'")
            conn.execute("DELETE FROM rollback_registry WHERE undo_action = 'execute_sql'")

    def test_edge_decay_and_rollback(self):
        # 1. Decay edges
        res = knowledge_organizer.decay_edges(decay_amount=0.1)
        self.assertEqual(res["status"], "success")
        
        # Verify decayed weight
        with get_connection() as conn:
            row = conn.execute("SELECT weight FROM knowledge_graph_edges WHERE id = 557").fetchone()
            self.assertAlmostEqual(row["weight"], 0.7, places=2)

        # 2. Rollback decay
        action_id = res["action_id"]
        roll_res = human_oversight.rollback(action_id)
        self.assertEqual(roll_res["status"], "rolled_back")

        # Verify weight is restored
        with get_connection() as conn:
            row = conn.execute("SELECT weight FROM knowledge_graph_edges WHERE id = 557").fetchone()
            self.assertAlmostEqual(row["weight"], 0.8, places=2)

    def test_concept_merging_and_rollback(self):
        # 1. Merge duplicate plural into singular
        res = knowledge_organizer.merge_duplicate_concepts()
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["merges"], [("networks", "network")])

        # Plural node 555 should be deleted
        with get_connection() as conn:
            plural_row = conn.execute("SELECT id FROM knowledge_graph_nodes WHERE id = 555").fetchone()
            self.assertIsNone(plural_row)
            
            # Singular access count should be boosted (3 + 2 = 5)
            singular_row = conn.execute("SELECT access_count FROM knowledge_graph_nodes WHERE id = 556").fetchone()
            self.assertEqual(singular_row["access_count"], 5)

        # 2. Rollback merge
        action_id = res["action_id"]
        roll_res = human_oversight.rollback(action_id)
        self.assertEqual(roll_res["status"], "rolled_back")

        # Plural node 555 should exist again
        with get_connection() as conn:
            plural_row = conn.execute("SELECT id, access_count FROM knowledge_graph_nodes WHERE id = 555").fetchone()
            self.assertIsNotNone(plural_row)
            
            # Singular access count should be restored back to 3
            singular_row = conn.execute("SELECT access_count FROM knowledge_graph_nodes WHERE id = 556").fetchone()
            self.assertEqual(singular_row["access_count"], 3)


class TestWorkspaceOrchestration(unittest.TestCase):
    """Verify predictive workspace loading preloads and respects governor rules."""

    def setUp(self):
        with get_connection() as conn:
            conn.execute("DELETE FROM workspace_nodes WHERE workspace_id = 601")
            conn.execute("DELETE FROM cognitive_workspaces WHERE id = 601")
            conn.execute(
                "INSERT INTO cognitive_workspaces (id, title, description, workspace_type, status, summary, created_at, updated_at) "
                "VALUES (601, 'Test Workspace', 'desc', 'software', 'active', 'summary', '2026-05-24', '2026-05-24')"
            )
            conn.execute(
                "INSERT INTO workspace_nodes (id, workspace_id, content, node_type, importance, tags_json, created_at, updated_at) "
                "VALUES (611, 601, 'Python Code Node', 'note', 0.8, '[]', '2026-05-24', '2026-05-24')"
            )

    def tearDown(self):
        with get_connection() as conn:
            conn.execute("DELETE FROM workspace_nodes WHERE workspace_id = 601")
            conn.execute("DELETE FROM cognitive_workspaces WHERE id = 601")
            conn.execute("DELETE FROM autonomy_audit_log WHERE action = 'preload_workspace'")

    def test_predict_and_preload(self):
        with patch("desktop_awareness.desktop_awareness.get_status", return_value={"current_category": "coding"}):
            res = workspace_orchestrator.predict_and_preload()
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["workspace_id"], 601)
            self.assertEqual(res["nodes_preloaded"], 1)


class TestExplainableAutonomy(unittest.TestCase):
    """Verify decision traces, scoring logs, and explainability trace summaries."""

    def setUp(self):
        self.action_id = "test-exp-123"
        with get_connection() as conn:
            conn.execute("DELETE FROM autonomy_audit_log WHERE action_id = ?", (self.action_id,))
        human_oversight.log_action(
            action_id=self.action_id,
            action="notify",
            params={"message": "break nudge"},
            attribution="productivity_optimization",
            reasoning="User focused too long",
            confidence=0.98,
            risk_level="safe",
            status="executed",
            detail="Nudged successfully"
        )

    def tearDown(self):
        with get_connection() as conn:
            conn.execute("DELETE FROM autonomy_audit_log WHERE action_id = ?", (self.action_id,))

    def test_explain_action(self):
        res = explainability_engine.explain_action(self.action_id)
        self.assertEqual(res["action_id"], self.action_id)
        self.assertEqual(res["attribution"], "productivity_optimization")
        self.assertIn("productivity_optimization", res["natural_language_explanation"])
        self.assertIn("98%", res["natural_language_explanation"])

    def test_get_decision_traces(self):
        traces = explainability_engine.get_decision_traces(limit=5)
        self.assertTrue(any(t["action_id"] == self.action_id for t in traces))
        match = [t for t in traces if t["action_id"] == self.action_id][0]
        self.assertEqual(match["uncertainty"], 0.02)


class TestEcosystemCoordinationEndpoints(unittest.TestCase):
    """Verify Phase 8 REST endpoints added in Steps 3-8."""

    @classmethod
    def setUpClass(cls):
        try:
            from server import app
            cls.app = app
            cls.has_app = True
        except Exception:
            cls.has_app = False

    def setUp(self):
        if not self.has_app:
            self.skipTest("Server not available")
        self.action_id = "api-exp-999"
        with get_connection() as conn:
            conn.execute("DELETE FROM autonomy_audit_log WHERE action_id = ?", (self.action_id,))
            conn.execute("DELETE FROM project_milestones WHERE project_id = 901")
            conn.execute("DELETE FROM projects WHERE id = 901")
        human_oversight.log_action(
            action_id=self.action_id,
            action="notify",
            params={},
            attribution="test",
            reasoning="api explanation check",
            confidence=0.95,
            risk_level="safe",
            status="executed"
        )
        
        # Setup active project
        now = datetime.now().isoformat()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO projects (id, title, description, domain, status, trajectory, progress, blockers_json, context_json, created_at, updated_at) "
                "VALUES (901, 'API Project', 'desc', 'software', 'active', 'on_track', 0.2, '[]', '{}', ?, ?)",
                (now, now)
            )
            conn.execute(
                "INSERT INTO project_milestones (id, project_id, title, status, progress, order_idx, created_at) "
                "VALUES (911, 901, 'API Milestone 1', 'pending', 0.5, 0, ?)",
                (now,)
            )

    def tearDown(self):
        with get_connection() as conn:
            conn.execute("DELETE FROM autonomy_audit_log WHERE action_id = ?", (self.action_id,))
            conn.execute("DELETE FROM project_milestones WHERE project_id = 901")
            conn.execute("DELETE FROM projects WHERE id = 901")
            conn.execute("DELETE FROM autonomy_audit_log WHERE action = 'decay_edges'")

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_get_explain(self):
        async def check():
            async with self.app.test_client() as client:
                resp = await client.get(f"/autonomy/explain/{self.action_id}")
                self.assertEqual(resp.status_code, 200)
                data = await resp.get_json()
                self.assertEqual(data["action_id"], self.action_id)
                self.assertIn("natural_language_explanation", data)
        self.run_async(check())

    def test_get_traces(self):
        async def check():
            async with self.app.test_client() as client:
                resp = await client.get("/autonomy/traces?limit=5")
                self.assertEqual(resp.status_code, 200)
                data = await resp.get_json()
                self.assertIn("traces", data)
                self.assertIsInstance(data["traces"], list)
        self.run_async(check())

    def test_get_project_forecast(self):
        async def check():
            async with self.app.test_client() as client:
                resp = await client.get("/autonomy/project/forecast?project_id=901")
                self.assertEqual(resp.status_code, 200)
                data = await resp.get_json()
                self.assertEqual(data["project_id"], 901)
                self.assertIn("forecasts", data)
        self.run_async(check())

    def test_post_graph_organize(self):
        async def check():
            async with self.app.test_client() as client:
                resp = await client.post("/autonomy/graph/organize")
                self.assertEqual(resp.status_code, 200)
                data = await resp.get_json()
                self.assertEqual(data["status"], "success")
                self.assertIn("decay", data)
                self.assertIn("merge", data)
        self.run_async(check())


if __name__ == "__main__":
    unittest.main(verbosity=2)
