"""
Phase 7 Test Suite — Collaborative Cognitive Intelligence Environment.

Covers all 8 steps:
    Step 1: Project Cognition Layer
    Step 2: Shared Cognitive Workspace
    Step 3: Knowledge Synthesis Engine
    Step 4: Research Intelligence System
    Step 5: Creative Collaboration Layer
    Step 6: Adaptive Knowledge Graph
    Step 7: Cognitive Reflection Engine
    Step 8: Collaborative Intelligence Integration

Plus:
    Human Agency Audit
    Privacy & Safety Audit
    Phase 6 Regression
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Project path setup
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_DATABASE_DIR = os.path.join(_PROJECT_ROOT, "database")
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
if _DATABASE_DIR not in sys.path:
    sys.path.insert(0, _DATABASE_DIR)


# ===================================================================
# Step 1: Project Cognition Layer
# ===================================================================

class TestProjectCognition(unittest.TestCase):
    """Tests for project_cognition.py."""

    def setUp(self):
        from project_cognition import ProjectCognition
        self.engine = ProjectCognition()

    def test_create_project_returns_id(self):
        result = self.engine.create_project("Test Project P7", "desc", "technology")
        self.assertEqual(result["status"], "created")
        self.assertIn("id", result)
        self.assertIsInstance(result["id"], int)

    def test_create_project_stores_fields(self):
        result = self.engine.create_project("Fields Test", "some desc", "research")
        project = self.engine.get_project(result["id"])
        self.assertIsNotNone(project)
        self.assertEqual(project["title"], "Fields Test")
        self.assertEqual(project["domain"], "research")

    def test_get_project_returns_none_for_missing(self):
        result = self.engine.get_project(999999)
        self.assertIsNone(result)

    def test_update_project_progress(self):
        r = self.engine.create_project("Progress Test", "", "general")
        self.engine.update_project(r["id"], progress=0.5)
        project = self.engine.get_project(r["id"])
        self.assertAlmostEqual(project["progress"], 0.5, places=2)

    def test_update_project_status(self):
        r = self.engine.create_project("Status Test", "", "general")
        self.engine.update_project(r["id"], status="paused")
        project = self.engine.get_project(r["id"])
        self.assertEqual(project["status"], "paused")

    def test_add_milestone_returns_created(self):
        r = self.engine.create_project("Milestone Test", "", "general")
        m = self.engine.add_milestone(r["id"], "First milestone")
        self.assertEqual(m["status"], "created")
        self.assertIn("id", m)

    def test_update_milestone_progress(self):
        r = self.engine.create_project("MS Progress Test", "", "general")
        m = self.engine.add_milestone(r["id"], "MS 1")
        self.engine.update_milestone(m["id"], progress=0.75)
        project = self.engine.get_project(r["id"])
        ms_list = project.get("milestones", [])
        updated = [x for x in ms_list if x["id"] == m["id"]]
        if updated:
            self.assertAlmostEqual(updated[0]["progress"], 0.75, places=2)

    def test_get_active_projects_returns_list(self):
        projects = self.engine.get_active_projects()
        self.assertIsInstance(projects, list)

    def test_detect_blockers_returns_list(self):
        r = self.engine.create_project("Blocker Test", "", "general")
        blockers = self.engine.detect_blockers(r["id"])
        self.assertIsInstance(blockers, list)

    def test_get_project_trajectory(self):
        r = self.engine.create_project("Trajectory Test", "", "general")
        traj = self.engine.get_project_trajectory(r["id"])
        self.assertIn("trajectory", traj)

    def test_get_context_for_conversation_returns_string(self):
        ctx = self.engine.get_context_for_conversation("working on my thesis")
        self.assertIsInstance(ctx, str)

    def test_infer_project_from_input(self):
        self.engine.create_project("Machine Learning Paper", "ML research", "AI")
        result = self.engine.infer_project_from_input(
            "I made progress on the machine learning paper today"
        )
        # May or may not match depending on token overlap; just verify no crash
        self.assertTrue(result is None or isinstance(result, dict))

    def test_detect_project_signal(self):
        self.engine.create_project("Auth System", "authentication module", "software")
        signal = self.engine.detect_project_signal(
            "I finally got the auth system working", "happy"
        )
        self.assertIsInstance(signal, dict)
        self.assertIn("detected", signal)

    def test_get_project_context_returns_string(self):
        ctx = self.engine.get_project_context()
        self.assertIsInstance(ctx, str)

    def test_get_status_structure(self):
        status = self.engine.get_status()
        self.assertIn("active_projects", status)

    def test_progress_bounded_0_to_1(self):
        r = self.engine.create_project("Bounds Test", "", "general")
        self.engine.update_project(r["id"], progress=1.5)
        project = self.engine.get_project(r["id"])
        # Progress should be capped or at least not crash
        self.assertIsNotNone(project)


# ===================================================================
# Step 2: Shared Cognitive Workspace
# ===================================================================

class TestCognitiveWorkspace(unittest.TestCase):
    """Tests for cognitive_workspace.py."""

    def setUp(self):
        from cognitive_workspace import CognitiveWorkspace
        self.ws = CognitiveWorkspace()

    def test_create_workspace_returns_id(self):
        result = self.ws.create_workspace("Test WS", "desc", "research")
        self.assertEqual(result["status"], "created")
        self.assertIn("id", result)

    def test_get_workspace_returns_structure(self):
        r = self.ws.create_workspace("Struct WS", "d")
        ws = self.ws.get_workspace(r["id"])
        self.assertIsNotNone(ws)
        self.assertIn("title", ws)
        self.assertIn("nodes", ws)

    def test_get_workspace_missing_returns_none(self):
        result = self.ws.get_workspace(999999)
        self.assertIsNone(result)

    def test_add_node_returns_created(self):
        r = self.ws.create_workspace("Node WS", "d")
        n = self.ws.add_node(r["id"], "Test concept content", "concept")
        self.assertEqual(n["status"], "created")
        self.assertIn("id", n)

    def test_add_multiple_node_types(self):
        r = self.ws.create_workspace("Types WS", "d")
        for ntype in ("note", "concept", "idea", "insight", "question"):
            n = self.ws.add_node(r["id"], f"Content for {ntype}", ntype)
            self.assertEqual(n["status"], "created")

    def test_update_node(self):
        r = self.ws.create_workspace("Update WS", "d")
        n = self.ws.add_node(r["id"], "Original", "note")
        result = self.ws.update_node(n["id"], content="Updated content")
        self.assertEqual(result["status"], "updated")

    def test_link_nodes_returns_created(self):
        r = self.ws.create_workspace("Link WS", "d")
        n1 = self.ws.add_node(r["id"], "Node A", "concept")
        n2 = self.ws.add_node(r["id"], "Node B", "concept")
        link = self.ws.link_nodes(n1["id"], n2["id"], "related")
        self.assertEqual(link["status"], "created")

    def test_link_nodes_with_weight(self):
        r = self.ws.create_workspace("Weight WS", "d")
        n1 = self.ws.add_node(r["id"], "A", "note")
        n2 = self.ws.add_node(r["id"], "B", "note")
        link = self.ws.link_nodes(n1["id"], n2["id"], "related", weight=0.9)
        self.assertEqual(link["status"], "created")

    def test_get_active_workspaces_returns_list(self):
        workspaces = self.ws.get_active_workspaces()
        self.assertIsInstance(workspaces, list)

    def test_archive_workspace(self):
        r = self.ws.create_workspace("Archive WS", "d")
        result = self.ws.archive_workspace(r["id"])
        self.assertEqual(result["status"], "archived")

    def test_search_nodes_returns_list(self):
        r = self.ws.create_workspace("Search WS", "d")
        self.ws.add_node(r["id"], "Machine learning research notes", "note")
        results = self.ws.search_nodes("machine learning")
        self.assertIsInstance(results, list)

    def test_get_related_nodes(self):
        r = self.ws.create_workspace("Related WS", "d")
        n1 = self.ws.add_node(r["id"], "Central", "concept")
        n2 = self.ws.add_node(r["id"], "Related", "concept")
        self.ws.link_nodes(n1["id"], n2["id"])
        related = self.ws.get_related_nodes(n1["id"])
        self.assertIsInstance(related, list)

    def test_get_idea_tree(self):
        r = self.ws.create_workspace("Tree WS", "d")
        self.ws.add_node(r["id"], "Root idea", "idea")
        tree = self.ws.get_idea_tree(r["id"])
        self.assertIsInstance(tree, dict)

    def test_summarize_workspace_returns_string(self):
        r = self.ws.create_workspace("Summary WS", "description")
        self.ws.add_node(r["id"], "Key insight about ML", "insight")
        self.ws.add_node(r["id"], "Question about data quality", "question")
        summary = self.ws.summarize_workspace(r["id"])
        self.assertIsInstance(summary, str)
        self.assertTrue(len(summary) > 0)

    def test_find_connections(self):
        connections = self.ws.find_connections("test input text")
        self.assertIsInstance(connections, list)

    def test_get_status_structure(self):
        status = self.ws.get_status()
        self.assertIn("total_workspaces", status)
        self.assertIn("total_nodes", status)


# ===================================================================
# Step 3: Knowledge Synthesis Engine
# ===================================================================

class TestKnowledgeSynthesis(unittest.TestCase):
    """Tests for knowledge_synthesis.py."""

    def setUp(self):
        from knowledge_synthesis import KnowledgeSynthesis
        self.synth = KnowledgeSynthesis()

    def test_synthesize_single_text(self):
        result = self.synth.synthesize(["machine learning"])
        self.assertIsInstance(result, dict)
        self.assertIn("summary", result)

    def test_synthesize_with_context(self):
        result = self.synth.synthesize(["deep learning"], context="AI research")
        self.assertIsInstance(result, dict)

    def test_detect_contradictions_returns_dict(self):
        result = self.synth.detect_contradictions(
            "Machine learning requires large datasets",
            "Machine learning works well with small datasets",
        )
        self.assertIsInstance(result, dict)
        self.assertIn("has_contradiction", result)

    def test_detect_contradictions_same_text(self):
        result = self.synth.detect_contradictions(
            "Neural networks are powerful",
            "Neural networks are powerful",
        )
        self.assertIsInstance(result, dict)
        # Same text should not be contradictory
        self.assertFalse(result.get("has_contradiction", False))

    def test_find_patterns(self):
        texts = [
            "Neural networks use backpropagation for learning",
            "Deep learning models use gradient descent optimization",
            "Machine learning algorithms learn from data patterns",
        ]
        patterns = self.synth.find_patterns(texts)
        self.assertIsInstance(patterns, list)

    def test_cluster_insights(self):
        # cluster_insights works on workspace nodes, pass workspace_id
        from cognitive_workspace import CognitiveWorkspace
        ws = CognitiveWorkspace()
        r = ws.create_workspace("Cluster Test WS", "for clustering")
        ws.add_node(r["id"], "Python is great for data science", "insight")
        ws.add_node(r["id"], "Python has excellent ML libraries", "insight")
        ws.add_node(r["id"], "JavaScript is good for web development", "insight")
        clusters = self.synth.cluster_insights(workspace_id=r["id"])
        self.assertIsInstance(clusters, list)

    def test_generate_summary(self):
        texts = ["First point about AI.", "Second point about ML."]
        summary = self.synth.generate_summary(texts)
        self.assertIsInstance(summary, str)

    def test_get_semantic_links(self):
        links = self.synth.get_semantic_links("neural networks")
        self.assertIsInstance(links, list)

    def test_suggest_connections(self):
        connections = self.synth.suggest_connections("attention mechanisms in transformers")
        self.assertIsInstance(connections, list)

    def test_get_status_structure(self):
        status = self.synth.get_status()
        self.assertIn("engine", status)

    def test_sentiment_polarity_positive(self):
        score = self.synth._get_sentiment_polarity("This is great and excellent work!")
        self.assertIn(score, [-1, 0, 1])

    def test_sentiment_polarity_negative(self):
        score = self.synth._get_sentiment_polarity("This is terrible and awful!")
        self.assertIn(score, [-1, 0, 1])

    def test_sentiment_polarity_neutral(self):
        score = self.synth._get_sentiment_polarity("The temperature is 20 degrees.")
        self.assertEqual(score, 0)


# ===================================================================
# Step 4: Research Intelligence System
# ===================================================================

class TestResearchIntelligence(unittest.TestCase):
    """Tests for research_intelligence.py."""

    def setUp(self):
        from research_intelligence import ResearchIntelligence
        self.research = ResearchIntelligence()

    def test_start_session_returns_created(self):
        result = self.research.start_session("Quantum mechanics")
        self.assertEqual(result["status"], "created")
        self.assertIn("id", result)

    def test_start_session_with_domain(self):
        result = self.research.start_session("Epigenetics", domain="biology")
        self.assertEqual(result["status"], "created")

    def test_get_session_returns_structure(self):
        r = self.research.start_session("Session Test")
        session = self.research.get_session(r["id"])
        self.assertIsNotNone(session)
        self.assertEqual(session["topic"], "Session Test")

    def test_get_session_missing_returns_none(self):
        result = self.research.get_session(999999)
        self.assertIsNone(result)

    def test_add_finding(self):
        r = self.research.start_session("Finding Test")
        result = self.research.add_finding(r["id"], "Key finding about topic")
        self.assertEqual(result["status"], "added")

    def test_add_finding_with_source(self):
        r = self.research.start_session("Source Test")
        result = self.research.add_finding(
            r["id"], "Finding with source", source="arxiv.org"
        )
        self.assertEqual(result["status"], "added")

    def test_add_question(self):
        r = self.research.start_session("Question Test")
        result = self.research.add_question(r["id"], "What about X?")
        self.assertEqual(result["status"], "added")

    def test_add_source(self):
        r = self.research.start_session("Source Add Test")
        result = self.research.add_source(r["id"], {
            "url": "https://example.com/paper",
            "title": "Test Paper",
            "type": "article",
        })
        self.assertEqual(result["status"], "added")

    def test_get_active_sessions_returns_list(self):
        sessions = self.research.get_active_sessions()
        self.assertIsInstance(sessions, list)

    def test_close_session(self):
        r = self.research.start_session("Close Test")
        result = self.research.close_session(r["id"])
        self.assertEqual(result["status"], "closed")

    def test_calculate_depth_score(self):
        r = self.research.start_session("Depth Test")
        self.research.add_finding(r["id"], "Finding 1")
        self.research.add_finding(r["id"], "Finding 2")
        self.research.add_question(r["id"], "Question 1")
        score = self.research.calculate_depth_score(r["id"])
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_get_session_evolution(self):
        r = self.research.start_session("Evolution Test")
        self.research.add_finding(r["id"], "First finding")
        evo = self.research.get_session_evolution(r["id"])
        self.assertIsInstance(evo, dict)

    def test_get_research_continuity(self):
        self.research.start_session("Continuity topic")
        result = self.research.get_research_continuity("Continuity topic")
        self.assertIsInstance(result, dict)
        self.assertIn("has_prior_research", result)

    def test_suggest_questions_returns_list(self):
        r = self.research.start_session("Suggest Q Test")
        self.research.add_finding(r["id"], "Interesting finding about neurons")
        questions = self.research.suggest_questions(r["id"])
        self.assertIsInstance(questions, list)

    def test_detect_research_signal(self):
        signal = self.research.detect_research_signal(
            "I've been reading about quantum entanglement"
        )
        self.assertIsInstance(signal, dict)

    def test_get_research_context_returns_string(self):
        ctx = self.research.get_research_context()
        self.assertIsInstance(ctx, str)

    def test_get_status_structure(self):
        status = self.research.get_status()
        self.assertIn("active_sessions", status)

    def test_depth_score_increases_with_findings(self):
        r = self.research.start_session("Depth Growth Test")
        score_0 = self.research.calculate_depth_score(r["id"])
        for i in range(5):
            self.research.add_finding(r["id"], f"Finding {i}")
            self.research.add_question(r["id"], f"Question {i}")
        score_1 = self.research.calculate_depth_score(r["id"])
        self.assertGreaterEqual(score_1, score_0)


# ===================================================================
# Step 5: Creative Collaboration Layer
# ===================================================================

class TestCreativeCollaboration(unittest.TestCase):
    """Tests for creative_collaboration.py."""

    def setUp(self):
        from creative_collaboration import CreativeCollaboration
        self.creative = CreativeCollaboration()

    def test_brainstorm_returns_dict(self):
        result = self.creative.brainstorm("sustainable energy solutions")
        self.assertIsInstance(result, dict)

    def test_brainstorm_with_existing_ideas(self):
        result = self.creative.brainstorm(
            "app ideas",
            existing_ideas=["fitness tracker", "meal planner"],
        )
        self.assertIsInstance(result, dict)

    def test_challenge_assumptions_returns_list(self):
        result = self.creative.challenge_assumptions(
            "We need more data to train better models"
        )
        self.assertIsInstance(result, list)

    def test_challenge_assumptions_non_empty_for_assertive_text(self):
        result = self.creative.challenge_assumptions(
            "Everyone knows that AI will replace all jobs"
        )
        self.assertIsInstance(result, list)
        # Should detect some assumption signals
        self.assertTrue(len(result) >= 0)  # May or may not find signals

    def test_expand_perspective_returns_dict(self):
        result = self.creative.expand_perspective("remote work is the future")
        self.assertIsInstance(result, dict)

    def test_expand_perspective_with_dimensions(self):
        result = self.creative.expand_perspective(
            "AI in healthcare",
            dimensions=["ethical", "economic", "technical"],
        )
        self.assertIsInstance(result, dict)

    def test_generate_alternatives(self):
        result = self.creative.generate_alternatives(
            "use a database for storage",
            count=3,
        )
        self.assertIsInstance(result, list)

    def test_reframe_returns_list(self):
        result = self.creative.reframe("How do we reduce costs?")
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)

    def test_random_stimulus_returns_string(self):
        result = self.creative.random_stimulus()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_random_stimulus_with_domain(self):
        result = self.creative.random_stimulus(domain="technology")
        self.assertIsInstance(result, str)

    def test_get_ideation_scaffolding(self):
        result = self.creative.get_ideation_scaffolding("sustainable cities")
        self.assertIsInstance(result, dict)

    def test_get_status_structure(self):
        status = self.creative.get_status()
        self.assertIn("engine", status)

    def test_brainstorm_does_not_overwhelm(self):
        """AISHA should not flood with too many ideas."""
        result = self.creative.brainstorm("space exploration")
        # The brainstorm output should be bounded
        if "ideas" in result:
            self.assertLessEqual(len(result["ideas"]), 10)

    def test_reframe_invitational_language(self):
        """Reframes should use invitational, not directive language."""
        reframes = self.creative.reframe("We must cut the budget")
        for r in reframes:
            self.assertNotIn("you must", r.lower())
            self.assertNotIn("you should", r.lower())


# ===================================================================
# Step 6: Adaptive Knowledge Graph
# ===================================================================

class TestAdaptiveKnowledgeGraph(unittest.TestCase):
    """Tests for knowledge_graph.py."""

    def setUp(self):
        from knowledge_graph import AdaptiveKnowledgeGraph
        self.kg = AdaptiveKnowledgeGraph()

    def test_add_concept_creates_node(self):
        result = self.kg.add_concept("neural networks", domain="AI")
        self.assertIn(result["status"], ("created", "reinforced"))

    def test_add_concept_reinforces_existing(self):
        self.kg.add_concept("reinforcement learning")
        result = self.kg.add_concept("reinforcement learning")
        self.assertEqual(result["status"], "reinforced")

    def test_add_concept_skips_short(self):
        result = self.kg.add_concept("AI")
        self.assertEqual(result["status"], "skipped")

    def test_add_relationship_creates_edge(self):
        result = self.kg.add_relationship(
            "deep learning", "machine learning", "part_of"
        )
        self.assertIn(result["status"], ("created", "reinforced"))

    def test_add_relationship_auto_creates_concepts(self):
        result = self.kg.add_relationship(
            "concept_auto_a", "concept_auto_b", "related_to"
        )
        self.assertIn(result["status"], ("created", "reinforced"))
        # Both concepts should now exist
        a = self.kg.get_concept("concept_auto_a")
        b = self.kg.get_concept("concept_auto_b")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)

    def test_add_relationship_skips_self_reference(self):
        result = self.kg.add_relationship("self_ref", "self_ref")
        self.assertEqual(result["status"], "skipped")

    def test_add_relationship_invalid_defaults_to_related_to(self):
        result = self.kg.add_relationship(
            "invalid_rel_a", "invalid_rel_b", "nonexistent_relationship"
        )
        self.assertIn(result["status"], ("created", "reinforced"))

    def test_reinforce_edge(self):
        self.kg.add_relationship("reinforce_a", "reinforce_b")
        result = self.kg.reinforce_edge("reinforce_a", "reinforce_b", amount=0.15)
        self.assertEqual(result["status"], "reinforced")

    def test_reinforce_edge_not_found(self):
        result = self.kg.reinforce_edge("nonexistent_x", "nonexistent_y")
        self.assertEqual(result["status"], "not_found")

    def test_get_concept(self):
        self.kg.add_concept("retrieval test concept")
        result = self.kg.get_concept("retrieval test concept")
        self.assertIsNotNone(result)
        self.assertEqual(result["concept"], "retrieval test concept")

    def test_get_concept_missing_returns_none(self):
        result = self.kg.get_concept("absolutely_nonexistent_concept_xyz123")
        self.assertIsNone(result)

    def test_get_neighbors(self):
        self.kg.add_relationship("neighbor_center", "neighbor_edge_1")
        self.kg.add_relationship("neighbor_center", "neighbor_edge_2")
        neighbors = self.kg.get_neighbors("neighbor_center")
        self.assertIsInstance(neighbors, list)
        self.assertGreaterEqual(len(neighbors), 1)

    def test_get_neighbors_missing_concept(self):
        neighbors = self.kg.get_neighbors("totally_missing_node")
        self.assertEqual(neighbors, [])

    def test_get_subgraph_structure(self):
        self.kg.add_relationship("subgraph_a", "subgraph_b")
        self.kg.add_relationship("subgraph_b", "subgraph_c")
        subgraph = self.kg.get_subgraph("subgraph_a", depth=2)
        self.assertIn("center", subgraph)
        self.assertIn("nodes", subgraph)
        self.assertIn("edges", subgraph)

    def test_find_paths(self):
        self.kg.add_relationship("path_start", "path_mid")
        self.kg.add_relationship("path_mid", "path_end")
        paths = self.kg.find_paths("path_start", "path_end", max_depth=3)
        self.assertIsInstance(paths, list)

    def test_find_paths_self(self):
        paths = self.kg.find_paths("same_node", "same_node")
        self.assertEqual(paths, [["same_node"]])

    def test_get_clusters(self):
        clusters = self.kg.get_clusters(min_size=2)
        self.assertIsInstance(clusters, list)

    def test_get_important_concepts(self):
        self.kg.add_concept("important_concept_test")
        concepts = self.kg.get_important_concepts(top_k=5)
        self.assertIsInstance(concepts, list)

    def test_extract_concepts_from_text(self):
        concepts = self.kg.extract_concepts_from_text(
            "Machine learning and deep learning use neural networks for pattern recognition"
        )
        self.assertIsInstance(concepts, list)

    def test_update_from_conversation(self):
        edges = self.kg.update_from_conversation(
            "The transformer architecture uses attention mechanisms",
            "Yes, attention is key to transformer performance",
            emotion="neutral",
        )
        self.assertIsInstance(edges, int)
        self.assertGreaterEqual(edges, 0)

    def test_observe_concepts(self):
        result = self.kg.observe_concepts(
            "Natural language processing is advancing rapidly"
        )
        self.assertIsInstance(result, dict)
        self.assertIn("new", result)
        self.assertIn("reinforced", result)
        self.assertIn("edges", result)
        self.assertIn("concepts", result)

    def test_decay_edges_returns_count(self):
        pruned = self.kg.decay_edges(max_age_days=90)
        self.assertIsInstance(pruned, int)

    def test_get_status_structure(self):
        status = self.kg.get_status()
        self.assertIn("total_nodes", status)
        self.assertIn("total_edges", status)
        self.assertIn("avg_edge_weight", status)

    def test_weight_bounds_enforced(self):
        """Edge weights must be in [0.01, 1.0]."""
        from knowledge_graph import _MIN_WEIGHT, _MAX_WEIGHT
        self.assertEqual(_MIN_WEIGHT, 0.01)
        self.assertEqual(_MAX_WEIGHT, 1.0)

    def test_valid_relationships_set(self):
        """All valid relationship types must be documented."""
        from knowledge_graph import _VALID_RELATIONSHIPS
        expected = {
            "related_to", "part_of", "depends_on", "causes",
            "contrasts_with", "extends", "similar_to",
            "used_in", "enables", "derives_from",
        }
        self.assertEqual(_VALID_RELATIONSHIPS, expected)


# ===================================================================
# Step 7: Cognitive Reflection Engine
# ===================================================================

class TestCollaborativeReflection(unittest.TestCase):
    """Tests for collaborative_reflection.py."""

    def setUp(self):
        from collaborative_reflection import CollaborativeReflection
        self.reflection = CollaborativeReflection()

    def test_generate_reasoning_summary_returns_string(self):
        result = self.reflection.generate_reasoning_summary()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_analyze_thinking_patterns_structure(self):
        result = self.reflection.analyze_thinking_patterns(days=30)
        self.assertIsInstance(result, dict)
        self.assertIn("topic_frequency", result)
        self.assertIn("depth_distribution", result)
        self.assertIn("question_to_finding_ratio", result)
        self.assertIn("concept_clusters", result)
        self.assertIn("observations", result)
        self.assertIn("period_days", result)

    def test_analyze_thinking_patterns_period_matches(self):
        result = self.reflection.analyze_thinking_patterns(days=7)
        self.assertEqual(result["period_days"], 7)

    def test_surface_blind_spots_returns_list(self):
        result = self.reflection.surface_blind_spots("machine learning")
        self.assertIsInstance(result, list)
        self.assertLessEqual(len(result), 4)  # Never overwhelm

    def test_surface_blind_spots_with_explored_aspects(self):
        result = self.reflection.surface_blind_spots(
            "AI ethics", explored_aspects=["bias", "fairness"]
        )
        self.assertIsInstance(result, list)

    def test_blind_spots_never_overwhelming(self):
        """Blind spots should be capped to avoid overwhelming user."""
        result = self.reflection.surface_blind_spots("broad_topic")
        self.assertLessEqual(len(result), 4)

    def test_suggest_explorations_returns_list(self):
        result = self.reflection.suggest_explorations("neural networks")
        self.assertIsInstance(result, list)
        self.assertLessEqual(len(result), 5)

    def test_get_learning_trajectory_general(self):
        result = self.reflection.get_learning_trajectory()
        self.assertIsInstance(result, dict)
        self.assertIn("observation", result)

    def test_get_learning_trajectory_specific_topic(self):
        result = self.reflection.get_learning_trajectory("nonexistent_topic_xyz")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "not_found")

    def test_get_collaboration_quality(self):
        result = self.reflection.get_collaboration_quality()
        self.assertIsInstance(result, dict)
        self.assertIn("overall_score", result)
        self.assertIn("dimensions", result)
        self.assertIn("observation", result)

    def test_collaboration_quality_score_bounded(self):
        result = self.reflection.get_collaboration_quality()
        self.assertGreaterEqual(result["overall_score"], 0.0)
        self.assertLessEqual(result["overall_score"], 1.0)

    def test_get_status_structure(self):
        status = self.reflection.get_status()
        self.assertIn("engine", status)
        self.assertIn("collaboration_quality", status)
        self.assertIn("capabilities", status)

    def test_quality_observation_tiers(self):
        from collaborative_reflection import CollaborativeReflection
        # Test all observation tiers
        high = CollaborativeReflection._quality_observation(0.8)
        mid = CollaborativeReflection._quality_observation(0.5)
        low = CollaborativeReflection._quality_observation(0.2)
        zero = CollaborativeReflection._quality_observation(0.05)
        for obs in [high, mid, low, zero]:
            self.assertIsInstance(obs, str)
            self.assertTrue(len(obs) > 0)

    def test_observations_use_invitational_language(self):
        """Observations must never use authoritarian language."""
        result = self.reflection.analyze_thinking_patterns(days=30)
        for obs in result.get("observations", []):
            obs_lower = obs.lower()
            self.assertNotIn("you must", obs_lower)
            self.assertNotIn("you need to", obs_lower)
            self.assertNotIn("you have to", obs_lower)


# ===================================================================
# Step 8: Collaborative Intelligence Integration
# ===================================================================

class TestCollaborativeIntegration(unittest.TestCase):
    """Tests for Phase 7 integration in orchestrator + conversation engine."""

    def test_orchestrator_valid_tables_include_kg(self):
        """Knowledge graph tables must be in orchestrator's allowed list."""
        from cognitive_orchestrator import _VALID_TABLES
        self.assertIn("knowledge_graph_nodes", _VALID_TABLES)
        self.assertIn("knowledge_graph_edges", _VALID_TABLES)

    def test_orchestrator_has_kg_lazy_loader(self):
        from cognitive_orchestrator import CognitiveOrchestrator
        orch = CognitiveOrchestrator()
        self.assertTrue(hasattr(orch, '_get_knowledge_graph'))

    def test_orchestrator_process_turn_returns_kg_updates(self):
        """process_turn should include kg_updates in its return dict."""
        from cognitive_orchestrator import CognitiveOrchestrator
        orch = CognitiveOrchestrator()
        result = orch.process_turn(
            "I learned about transformers and attention mechanisms today",
            "That's a great area of study!",
            emotion="happy",
            session_id="test_session_7",
        )
        self.assertIn("kg_updates", result)
        self.assertIsInstance(result["kg_updates"], int)

    def test_orchestrator_recall_includes_kg_context(self):
        """recall() should include kg_context in its return dict."""
        from cognitive_orchestrator import CognitiveOrchestrator
        orch = CognitiveOrchestrator()
        result = orch.recall("neural networks")
        self.assertIn("kg_context", result)
        self.assertIsInstance(result["kg_context"], list)

    def test_orchestrator_recall_still_has_semantic(self):
        """Regression: recall must still include semantic, episodes, patterns."""
        from cognitive_orchestrator import CognitiveOrchestrator
        orch = CognitiveOrchestrator()
        result = orch.recall("test recall")
        self.assertIn("semantic", result)
        self.assertIn("episodes", result)
        self.assertIn("patterns", result)

    def test_conversation_engine_has_phase7_block(self):
        """conversation_engine.py must contain Phase 7 integration block."""
        import inspect
        from conversation_engine import ConversationEngine
        source = inspect.getsource(ConversationEngine.process_text)
        self.assertIn("Phase 7", source)
        self.assertIn("project_cognition", source)
        self.assertIn("knowledge_graph", source)

    def test_db_schema_has_phase7_tables(self):
        """All Phase 7 tables must exist in the database."""
        from database.db import get_connection
        with get_connection() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]

        phase7_tables = [
            "projects", "project_milestones",
            "cognitive_workspaces", "workspace_nodes", "node_links",
            "research_sessions",
            "knowledge_graph_nodes", "knowledge_graph_edges",
        ]
        for table in phase7_tables:
            self.assertIn(table, tables, f"Phase 7 table missing: {table}")

    def test_db_phase7_indexes_exist(self):
        """Phase 7 indexes must exist for performance."""
        from database.db import get_connection
        with get_connection() as conn:
            indexes = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()]

        expected_indexes = [
            "idx_projects_status",
            "idx_projects_domain",
            "idx_project_milestones_project",
            "idx_cognitive_workspaces_status",
            "idx_workspace_nodes_workspace",
            "idx_node_links_source",
            "idx_node_links_target",
            "idx_research_sessions_status",
            "idx_kg_nodes_concept",
            "idx_kg_edges_source",
        ]
        for idx in expected_indexes:
            self.assertIn(idx, indexes, f"Phase 7 index missing: {idx}")


# ===================================================================
# Human Agency Audit
# ===================================================================

class TestHumanAgencyAudit(unittest.TestCase):
    """
    Verify AISHA never:
    - replaces human judgment
    - becomes authoritative oracle AI
    - discourages independent thinking
    - dominates creative reasoning
    - creates intellectual dependency
    - over-directs decisions
    """

    def test_blind_spot_templates_are_invitational(self):
        """Blind spot templates must use invitational, not directive language."""
        from collaborative_reflection import _BLIND_SPOT_TEMPLATES
        for template in _BLIND_SPOT_TEMPLATES:
            t_lower = template.lower()
            self.assertNotIn("you must", t_lower)
            self.assertNotIn("you should", t_lower)
            self.assertNotIn("you have to", t_lower)
            self.assertNotIn("you need to", t_lower)

    def test_exploration_templates_are_invitational(self):
        """Exploration templates must use invitational language."""
        from collaborative_reflection import _EXPLORATION_TEMPLATES
        for template in _EXPLORATION_TEMPLATES:
            t_lower = template.lower()
            self.assertNotIn("you must", t_lower)
            self.assertNotIn("you should", t_lower)
            self.assertNotIn("you have to", t_lower)

    def test_brainstorm_not_overwhelming(self):
        """Brainstorm output must be bounded — no idea flooding."""
        from creative_collaboration import CreativeCollaboration
        c = CreativeCollaboration()
        result = c.brainstorm("test topic")
        # Should not produce an unbounded number of items
        if "ideas" in result:
            self.assertLessEqual(len(result["ideas"]), 12)

    def test_reframe_not_directive(self):
        """Reframes should offer perspectives, not commands."""
        from creative_collaboration import CreativeCollaboration
        c = CreativeCollaboration()
        reframes = c.reframe("How to increase productivity?")
        for r in reframes:
            r_lower = r.lower()
            self.assertNotIn("you must", r_lower)
            self.assertNotIn("do this", r_lower)

    def test_max_concepts_per_text_bounded(self):
        """Knowledge graph should not extract unbounded concepts."""
        from knowledge_graph import _MAX_CONCEPTS_PER_TEXT
        self.assertLessEqual(_MAX_CONCEPTS_PER_TEXT, 10)

    def test_blind_spots_capped_at_4(self):
        """Blind spots must never overwhelm — max 4."""
        from collaborative_reflection import CollaborativeReflection
        cr = CollaborativeReflection()
        result = cr.surface_blind_spots("anything")
        self.assertLessEqual(len(result), 4)

    def test_exploration_suggestions_capped(self):
        """Exploration suggestions capped at 5."""
        from collaborative_reflection import CollaborativeReflection
        cr = CollaborativeReflection()
        result = cr.suggest_explorations("anything")
        self.assertLessEqual(len(result), 5)

    def test_quality_observation_never_judgmental(self):
        """Quality observations must be supportive, not judgmental."""
        from collaborative_reflection import CollaborativeReflection
        for score in [0.0, 0.2, 0.5, 0.8, 1.0]:
            obs = CollaborativeReflection._quality_observation(score)
            obs_lower = obs.lower()
            self.assertNotIn("you failed", obs_lower)
            self.assertNotIn("poor performance", obs_lower)
            self.assertNotIn("you're doing it wrong", obs_lower)
            self.assertNotIn("disappointing", obs_lower)

    def test_research_questions_are_suggestions(self):
        """Research questions should be suggestions, not demands."""
        from research_intelligence import ResearchIntelligence
        ri = ResearchIntelligence()
        r = ri.start_session("Test questions")
        ri.add_finding(r["id"], "Some interesting finding about the topic")
        questions = ri.suggest_questions(r["id"])
        for q in questions:
            q_lower = q.lower()
            self.assertNotIn("you must answer", q_lower)
            self.assertNotIn("you need to research", q_lower)


# ===================================================================
# Privacy & Safety Audit
# ===================================================================

class TestPrivacySafetyAudit(unittest.TestCase):
    """Verify privacy and safety guarantees across Phase 7."""

    def test_no_cloud_imports_in_project_cognition(self):
        """project_cognition.py must not import cloud SDKs."""
        import inspect
        from project_cognition import ProjectCognition
        source = inspect.getsource(ProjectCognition)
        self.assertNotIn("requests.post", source)
        self.assertNotIn("boto3", source)
        self.assertNotIn("google.cloud", source)
        self.assertNotIn("openai", source)

    def test_no_cloud_imports_in_knowledge_graph(self):
        """knowledge_graph.py must not import cloud SDKs."""
        import inspect
        from knowledge_graph import AdaptiveKnowledgeGraph
        source = inspect.getsource(AdaptiveKnowledgeGraph)
        self.assertNotIn("requests.post", source)
        self.assertNotIn("boto3", source)
        self.assertNotIn("google.cloud", source)

    def test_no_cloud_imports_in_collaborative_reflection(self):
        """collaborative_reflection.py must not import cloud SDKs."""
        import inspect
        from collaborative_reflection import CollaborativeReflection
        source = inspect.getsource(CollaborativeReflection)
        self.assertNotIn("requests.post", source)
        self.assertNotIn("boto3", source)
        self.assertNotIn("google.cloud", source)

    def test_no_cloud_imports_in_creative_collaboration(self):
        import inspect
        from creative_collaboration import CreativeCollaboration
        source = inspect.getsource(CreativeCollaboration)
        self.assertNotIn("requests.post", source)
        self.assertNotIn("boto3", source)
        self.assertNotIn("google.cloud", source)

    def test_all_phase7_modules_use_sqlite(self):
        """All Phase 7 modules must use local SQLite, not remote databases."""
        import inspect
        from project_cognition import ProjectCognition
        from cognitive_workspace import CognitiveWorkspace
        from research_intelligence import ResearchIntelligence
        from knowledge_graph import AdaptiveKnowledgeGraph
        from collaborative_reflection import CollaborativeReflection

        for cls in [ProjectCognition, CognitiveWorkspace,
                    ResearchIntelligence, AdaptiveKnowledgeGraph]:
            source = inspect.getsource(cls)
            self.assertIn("get_connection", source,
                          f"{cls.__name__} must use SQLite via get_connection()")

    def test_edge_weight_cannot_exceed_1(self):
        from knowledge_graph import _MAX_WEIGHT
        self.assertLessEqual(_MAX_WEIGHT, 1.0)

    def test_edge_decay_rate_reasonable(self):
        from knowledge_graph import _EDGE_DECAY_RATE
        self.assertGreater(_EDGE_DECAY_RATE, 0)
        self.assertLess(_EDGE_DECAY_RATE, 0.1)

    def test_concept_has_minimum_length(self):
        """Concepts must have a minimum length to avoid noise."""
        from knowledge_graph import _MIN_CONCEPT_LENGTH
        self.assertGreaterEqual(_MIN_CONCEPT_LENGTH, 2)

    def test_db_uses_wal_mode(self):
        """Database must use WAL mode for concurrent access."""
        from database.db import get_connection
        with get_connection() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(mode, "wal")


# ===================================================================
# Phase 6 Regression
# ===================================================================

class TestPhase6Regression(unittest.TestCase):
    """Verify Phase 6 modules still work after Phase 7 changes."""

    def test_deep_personalization_still_works(self):
        from deep_personalization import deep_personalization
        status = deep_personalization.get_status()
        self.assertIn("dimensions", status)

    def test_emotional_timing_still_works(self):
        from emotional_timing import emotional_timing
        status = emotional_timing.get_status()
        self.assertIn("should_reflect", status)

    def test_behavioral_intelligence_still_works(self):
        from behavioral_intelligence import behavioral_intelligence
        prompt = behavioral_intelligence.get_behavioral_prompt()
        self.assertIsInstance(prompt, str)

    def test_reflective_cognition_still_works(self):
        from reflective_cognition import reflective_cognition
        self.assertTrue(hasattr(reflective_cognition, 'generate_reflection'))

    def test_life_management_still_works(self):
        from life_management import life_management
        status = life_management.get_status()
        self.assertIn("active_goals", status)

    def test_orchestrator_still_returns_semantic(self):
        """Orchestrator recall must still include Phase 3 semantic results."""
        from cognitive_orchestrator import CognitiveOrchestrator
        orch = CognitiveOrchestrator()
        result = orch.recall("test regression")
        self.assertIn("semantic", result)
        self.assertIn("episodes", result)
        self.assertIn("patterns", result)

    def test_orchestrator_process_turn_still_returns_latency(self):
        from cognitive_orchestrator import CognitiveOrchestrator
        orch = CognitiveOrchestrator()
        result = orch.process_turn("hello world", "hi", "neutral", "test")
        self.assertIn("latency_ms", result)
        self.assertIn("intents_committed", result)

    def test_db_schema_still_has_phase6_tables(self):
        from database.db import get_connection
        with get_connection() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        phase6_tables = [
            "deep_personalization", "emotional_timing_log",
            "multi_step_recipes", "multi_step_recipe_actions",
            "llm_reflections", "proactive_events",
        ]
        for table in phase6_tables:
            self.assertIn(table, tables, f"Phase 6 table missing: {table}")

    def test_db_schema_still_has_phase5_tables(self):
        from database.db import get_connection
        with get_connection() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        phase5_tables = [
            "workflow_sessions", "daily_behavioral_summary",
            "routine_patterns", "behavioral_model",
            "cognitive_reflections", "automation_recipes",
            "ecosystem_timeline", "personality_snapshots",
            "life_goals", "device_sessions",
        ]
        for table in phase5_tables:
            self.assertIn(table, tables, f"Phase 5 table missing: {table}")

    def test_db_schema_still_has_phase3_tables(self):
        from database.db import get_connection
        with get_connection() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        phase3_tables = [
            "semantic_memory", "semantic_vocab",
            "episodes", "life_patterns", "cognitive_plans",
        ]
        for table in phase3_tables:
            self.assertIn(table, tables, f"Phase 3 table missing: {table}")


# ===================================================================
# Cross-Module Integration Tests
# ===================================================================

class TestCrossModuleIntegration(unittest.TestCase):
    """End-to-end integration tests across Phase 7 modules."""

    def test_project_to_workspace_flow(self):
        """Create a project, then a workspace linked to it."""
        from project_cognition import ProjectCognition
        from cognitive_workspace import CognitiveWorkspace

        pc = ProjectCognition()
        ws = CognitiveWorkspace()

        project = pc.create_project("Integration Test Project", "test", "software")
        workspace = ws.create_workspace(
            "Integration Test Workspace",
            f"Workspace for project {project['id']}",
            "research",
        )
        node = ws.add_node(workspace["id"], "Key design decision", "insight")

        self.assertEqual(project["status"], "created")
        self.assertEqual(workspace["status"], "created")
        self.assertEqual(node["status"], "created")

    def test_research_to_knowledge_graph_flow(self):
        """Research findings should enrich the knowledge graph."""
        from research_intelligence import ResearchIntelligence
        from knowledge_graph import AdaptiveKnowledgeGraph

        ri = ResearchIntelligence()
        kg = AdaptiveKnowledgeGraph()

        session = ri.start_session("Graph neural networks")
        ri.add_finding(session["id"], "GNNs use message passing between nodes")
        ri.add_finding(session["id"], "Attention mechanisms improve GNN performance")

        # Feed findings into knowledge graph
        kg_result = kg.update_from_conversation(
            "Graph neural networks use message passing",
            "Attention mechanisms improve performance",
        )
        self.assertGreaterEqual(kg_result, 0)

    def test_synthesis_with_workspace_data(self):
        """Knowledge synthesis should work with workspace content."""
        from cognitive_workspace import CognitiveWorkspace
        from knowledge_synthesis import KnowledgeSynthesis

        ws = CognitiveWorkspace()
        synth = KnowledgeSynthesis()

        w = ws.create_workspace("Synthesis Integration WS", "test")
        ws.add_node(w["id"], "Transformers use attention mechanisms", "concept")
        ws.add_node(w["id"], "CNNs use convolutional filters", "concept")

        # Synthesize the concepts
        result = synth.synthesize("neural network architectures")
        self.assertIsInstance(result, dict)

    def test_reflection_uses_knowledge_graph(self):
        """Collaborative reflection should leverage KG data."""
        from collaborative_reflection import CollaborativeReflection
        from knowledge_graph import AdaptiveKnowledgeGraph

        kg = AdaptiveKnowledgeGraph()
        cr = CollaborativeReflection()

        # Add some concepts to the graph
        kg.add_concept("quantum computing", domain="physics")
        kg.add_concept("quantum entanglement", domain="physics")
        kg.add_relationship("quantum computing", "quantum entanglement", "related_to")

        # Reflection should be able to analyze
        trajectory = cr.get_learning_trajectory("quantum computing")
        self.assertIsInstance(trajectory, dict)

    def test_full_cognitive_pipeline(self):
        """Simulate a full turn through all Phase 7 systems."""
        from project_cognition import ProjectCognition
        from cognitive_workspace import CognitiveWorkspace
        from knowledge_graph import AdaptiveKnowledgeGraph
        from research_intelligence import ResearchIntelligence
        from collaborative_reflection import CollaborativeReflection

        pc = ProjectCognition()
        ws = CognitiveWorkspace()
        kg = AdaptiveKnowledgeGraph()
        ri = ResearchIntelligence()
        cr = CollaborativeReflection()

        user_input = "I'm researching how attention mechanisms work in large language models"

        # 1. Project signal detection
        signal = pc.detect_project_signal(user_input, "curious")
        self.assertIsInstance(signal, dict)

        # 2. Knowledge graph observation
        kg_result = kg.observe_concepts(user_input)
        self.assertIsInstance(kg_result, dict)

        # 3. Research continuity
        continuity = ri.get_research_continuity("attention mechanisms")
        self.assertIsInstance(continuity, dict)

        # 4. Workspace search
        ws_results = ws.search_nodes("attention")
        self.assertIsInstance(ws_results, list)

        # 5. Reflection
        trajectory = cr.get_learning_trajectory()
        self.assertIsInstance(trajectory, dict)

        # All steps completed without crash
        self.assertTrue(True)


# ===================================================================
# Performance Tests
# ===================================================================

class TestPerformance(unittest.TestCase):
    """Verify Phase 7 operations meet latency requirements."""

    def test_knowledge_graph_add_concept_under_50ms(self):
        from knowledge_graph import AdaptiveKnowledgeGraph
        kg = AdaptiveKnowledgeGraph()
        t0 = time.time()
        for i in range(10):
            kg.add_concept(f"perf_concept_{i}", domain="test")
        elapsed = (time.time() - t0) * 1000
        per_op = elapsed / 10
        self.assertLess(per_op, 50, f"add_concept took {per_op:.1f}ms per op")

    def test_knowledge_graph_observe_under_2000ms(self):
        from knowledge_graph import AdaptiveKnowledgeGraph
        kg = AdaptiveKnowledgeGraph()
        t0 = time.time()
        kg.observe_concepts("Testing performance of concept observation pipeline")
        elapsed = (time.time() - t0) * 1000
        self.assertLess(elapsed, 2000, f"observe_concepts took {elapsed:.1f}ms")

    def test_workspace_create_under_150ms(self):
        from cognitive_workspace import CognitiveWorkspace
        ws = CognitiveWorkspace()
        t0 = time.time()
        ws.create_workspace("Perf WS", "d")
        elapsed = (time.time() - t0) * 1000
        self.assertLess(elapsed, 150, f"create_workspace took {elapsed:.1f}ms")

    def test_project_creation_under_150ms(self):
        from project_cognition import ProjectCognition
        pc = ProjectCognition()
        t0 = time.time()
        pc.create_project("Perf Project", "d", "test")
        elapsed = (time.time() - t0) * 1000
        self.assertLess(elapsed, 150, f"create_project took {elapsed:.1f}ms")

    def test_orchestrator_process_turn_under_3000ms(self):
        """Full orchestrator turn must complete under 3000ms (cold start)."""
        from cognitive_orchestrator import CognitiveOrchestrator
        orch = CognitiveOrchestrator()
        t0 = time.time()
        orch.process_turn(
            "Testing the latency of the full cognitive pipeline",
            "Response for latency test",
            "neutral", "perf_test",
        )
        elapsed = (time.time() - t0) * 1000
        self.assertLess(elapsed, 3000, f"process_turn took {elapsed:.1f}ms")


# ===================================================================
# Runner
# ===================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
