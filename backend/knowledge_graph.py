"""
Adaptive Knowledge Graph for Aisha AI Assistant (Phase 7 Step 6).

Builds evolving conceptual relationships with semantic concept linking,
contextual relationship weighting, adaptive topic clustering, and
long-term conceptual continuity.

Design principles:
    - Lightweight and interpretable — no black-box algorithms
    - Nodes are concept strings with importance and access counts
    - Edges evolve: reinforced on co-occurrence, decayed over time
    - Auto-updates from conversation turns (extract + link concepts)
    - All operations are traceable and explainable

Usage::

    from knowledge_graph import knowledge_graph

    knowledge_graph.add_concept("machine learning", domain="technology")
    knowledge_graph.add_concept("neural networks", domain="technology")
    knowledge_graph.add_relationship("machine learning", "neural networks", "related_to")
    neighbors = knowledge_graph.get_neighbors("machine learning")
    clusters = knowledge_graph.get_clusters()
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import deque
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

_VALID_RELATIONSHIPS = {
    "related_to", "part_of", "depends_on", "causes", "contrasts_with",
    "extends", "similar_to", "used_in", "enables", "derives_from",
}

# Edge weight bounds
_MIN_WEIGHT = 0.01
_MAX_WEIGHT = 1.0

# Decay: edges lose this fraction per day if unreinforced
_EDGE_DECAY_RATE = 0.01

# Minimum concept length
_MIN_CONCEPT_LENGTH = 3

# Maximum concepts to extract from a single text
_MAX_CONCEPTS_PER_TEXT = 8


# ---------------------------------------------------------------------------
# Adaptive Knowledge Graph
# ---------------------------------------------------------------------------

class AdaptiveKnowledgeGraph:
    """
    Evolving conceptual graph with weighted edges and adaptive clustering.

    Writes directly to ``knowledge_graph_nodes`` and
    ``knowledge_graph_edges`` tables.
    """

    def __init__(self) -> None:
        print("  [KnowledgeGraph] Initialized")

    # ----- Concept Management ----------------------------------------------

    def add_concept(
        self,
        concept: str,
        domain: str = "general",
        context: dict | None = None,
    ) -> dict[str, Any]:
        """
        Add a concept node or reinforce an existing one.

        If the concept already exists, its importance and access count
        are boosted.
        """
        concept = concept.strip().lower()
        if len(concept) < _MIN_CONCEPT_LENGTH:
            return {"status": "skipped", "reason": "concept too short"}

        now = datetime.now().isoformat(timespec="seconds")
        context_json = json.dumps(context or {})

        with get_connection() as conn:
            existing = conn.execute(
                "SELECT id, importance, access_count FROM knowledge_graph_nodes "
                "WHERE concept = ?",
                (concept,),
            ).fetchone()

            if existing:
                # Reinforce existing concept
                new_importance = min(1.0, existing["importance"] + 0.05)
                conn.execute(
                    "UPDATE knowledge_graph_nodes SET "
                    "importance = ?, access_count = access_count + 1, "
                    "last_accessed = ? WHERE id = ?",
                    (new_importance, now, existing["id"]),
                )
                return {
                    "status": "reinforced",
                    "id": existing["id"],
                    "concept": concept,
                    "importance": new_importance,
                }
            else:
                cursor = conn.execute(
                    "INSERT INTO knowledge_graph_nodes "
                    "(concept, domain, importance, access_count, "
                    "context_json, created_at, last_accessed) "
                    "VALUES (?, ?, 0.3, 1, ?, ?, ?)",
                    (concept, domain, context_json, now, now),
                )
                return {
                    "status": "created",
                    "id": cursor.lastrowid,
                    "concept": concept,
                }

    # ----- Relationship Management -----------------------------------------

    def add_relationship(
        self,
        source_concept: str,
        target_concept: str,
        relationship: str = "related_to",
        weight: float = 0.5,
    ) -> dict[str, Any]:
        """
        Add or reinforce a relationship between two concepts.

        Creates concept nodes if they don't exist.
        """
        relationship = relationship if relationship in _VALID_RELATIONSHIPS else "related_to"
        weight = max(_MIN_WEIGHT, min(_MAX_WEIGHT, weight))

        source_concept = source_concept.strip().lower()
        target_concept = target_concept.strip().lower()

        if source_concept == target_concept:
            return {"status": "skipped", "reason": "self-reference"}

        now = datetime.now().isoformat(timespec="seconds")

        # Ensure both concepts exist
        self.add_concept(source_concept)
        self.add_concept(target_concept)

        with get_connection() as conn:
            source = conn.execute(
                "SELECT id FROM knowledge_graph_nodes WHERE concept = ?",
                (source_concept,),
            ).fetchone()
            target = conn.execute(
                "SELECT id FROM knowledge_graph_nodes WHERE concept = ?",
                (target_concept,),
            ).fetchone()

            if not source or not target:
                return {"status": "error", "error": "Concept lookup failed"}

            # Check existing edge
            existing = conn.execute(
                "SELECT id, weight, evidence_count FROM knowledge_graph_edges "
                "WHERE source_id = ? AND target_id = ?",
                (source["id"], target["id"]),
            ).fetchone()

            if existing:
                # Reinforce: average weights and increment evidence
                new_weight = min(_MAX_WEIGHT, (existing["weight"] + weight) / 2 + 0.05)
                conn.execute(
                    "UPDATE knowledge_graph_edges SET "
                    "weight = ?, evidence_count = evidence_count + 1, "
                    "last_reinforced = ? WHERE id = ?",
                    (new_weight, now, existing["id"]),
                )
                return {
                    "status": "reinforced",
                    "id": existing["id"],
                    "weight": round(new_weight, 3),
                }
            else:
                cursor = conn.execute(
                    "INSERT INTO knowledge_graph_edges "
                    "(source_id, target_id, relationship, weight, "
                    "evidence_count, created_at, last_reinforced) "
                    "VALUES (?, ?, ?, ?, 1, ?, ?)",
                    (source["id"], target["id"], relationship, weight, now, now),
                )
                return {
                    "status": "created",
                    "id": cursor.lastrowid,
                    "source": source_concept,
                    "target": target_concept,
                }

    def reinforce_edge(
        self,
        source_concept: str,
        target_concept: str,
        amount: float = 0.1,
    ) -> dict[str, Any]:
        """Strengthen an existing edge between two concepts."""
        source_concept = source_concept.strip().lower()
        target_concept = target_concept.strip().lower()
        now = datetime.now().isoformat(timespec="seconds")

        with get_connection() as conn:
            source = conn.execute(
                "SELECT id FROM knowledge_graph_nodes WHERE concept = ?",
                (source_concept,),
            ).fetchone()
            target = conn.execute(
                "SELECT id FROM knowledge_graph_nodes WHERE concept = ?",
                (target_concept,),
            ).fetchone()

            if not source or not target:
                return {"status": "not_found"}

            conn.execute(
                "UPDATE knowledge_graph_edges SET "
                "weight = MIN(?, weight + ?), "
                "evidence_count = evidence_count + 1, "
                "last_reinforced = ? "
                "WHERE source_id = ? AND target_id = ?",
                (_MAX_WEIGHT, amount, now, source["id"], target["id"]),
            )

        return {"status": "reinforced", "amount": amount}

    # ----- Decay -----------------------------------------------------------

    def decay_edges(self, max_age_days: int = 90) -> int:
        """
        Decay unused edges and prune very weak ones.

        Returns the number of edges pruned.
        """
        cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
        now = datetime.now()
        pruned = 0

        with get_connection() as conn:
            # Get edges that haven't been reinforced recently
            edges = conn.execute(
                "SELECT id, weight, last_reinforced FROM knowledge_graph_edges "
                "WHERE last_reinforced < ?",
                (cutoff,),
            ).fetchall()

            for edge in edges:
                try:
                    last = datetime.fromisoformat(edge["last_reinforced"])
                    days_since = (now - last).days
                    decay = _EDGE_DECAY_RATE * days_since
                    new_weight = edge["weight"] - decay

                    if new_weight < _MIN_WEIGHT:
                        conn.execute(
                            "DELETE FROM knowledge_graph_edges WHERE id = ?",
                            (edge["id"],),
                        )
                        pruned += 1
                    else:
                        conn.execute(
                            "UPDATE knowledge_graph_edges SET weight = ? WHERE id = ?",
                            (new_weight, edge["id"]),
                        )
                except (ValueError, TypeError):
                    pass

        return pruned

    # ----- Retrieval -------------------------------------------------------

    def get_concept(self, concept: str) -> dict[str, Any] | None:
        """Get a concept node by name."""
        concept = concept.strip().lower()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_graph_nodes WHERE concept = ?",
                (concept,),
            ).fetchone()

        if not row:
            return None

        d = dict(row)
        d["context"] = json.loads(d.get("context_json", "{}"))
        return d

    def get_neighbors(
        self, concept: str, depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Get immediate connections of a concept."""
        concept = concept.strip().lower()

        with get_connection() as conn:
            node = conn.execute(
                "SELECT id FROM knowledge_graph_nodes WHERE concept = ?",
                (concept,),
            ).fetchone()

            if not node:
                return []

            # Get edges where this node is source or target
            edges = conn.execute(
                "SELECT e.*, "
                "s.concept as source_concept, t.concept as target_concept "
                "FROM knowledge_graph_edges e "
                "JOIN knowledge_graph_nodes s ON e.source_id = s.id "
                "JOIN knowledge_graph_nodes t ON e.target_id = t.id "
                "WHERE e.source_id = ? OR e.target_id = ? "
                "ORDER BY e.weight DESC",
                (node["id"], node["id"]),
            ).fetchall()

        neighbors = []
        for edge in edges:
            other = (
                edge["target_concept"]
                if edge["source_concept"] == concept
                else edge["source_concept"]
            )
            neighbors.append({
                "concept": other,
                "relationship": edge["relationship"],
                "weight": edge["weight"],
                "evidence_count": edge["evidence_count"],
            })

        return neighbors

    def get_subgraph(
        self, concept: str, depth: int = 2,
    ) -> dict[str, Any]:
        """
        Get a concept and its surrounding nodes/edges up to given depth.

        Returns nodes and edges in the subgraph.
        """
        concept = concept.strip().lower()
        visited: set[str] = set()
        nodes: list[dict] = []
        edges: list[dict] = []

        queue = deque([(concept, 0)])

        while queue:
            current, d = queue.popleft()
            if current in visited or d > depth:
                continue
            visited.add(current)

            node = self.get_concept(current)
            if node:
                nodes.append({
                    "concept": current,
                    "importance": node.get("importance", 0),
                    "access_count": node.get("access_count", 0),
                    "domain": node.get("domain", "general"),
                })

            if d < depth:
                neighbors = self.get_neighbors(current)
                for n in neighbors:
                    edges.append({
                        "source": current,
                        "target": n["concept"],
                        "relationship": n["relationship"],
                        "weight": n["weight"],
                    })
                    if n["concept"] not in visited:
                        queue.append((n["concept"], d + 1))

        return {
            "center": concept,
            "depth": depth,
            "nodes": nodes,
            "edges": edges,
        }

    # ----- Path Finding ----------------------------------------------------

    def find_paths(
        self,
        source: str,
        target: str,
        max_depth: int = 4,
    ) -> list[list[str]]:
        """
        Find conceptual paths between two concepts using BFS.

        Returns list of paths (each path is a list of concept strings).
        """
        source = source.strip().lower()
        target = target.strip().lower()

        if source == target:
            return [[source]]

        # BFS
        queue: deque[list[str]] = deque([[source]])
        visited: set[str] = set()
        found_paths: list[list[str]] = []

        while queue and len(found_paths) < 3:
            path = queue.popleft()
            current = path[-1]

            if len(path) > max_depth:
                continue

            if current in visited:
                continue
            visited.add(current)

            neighbors = self.get_neighbors(current)
            for n in neighbors:
                new_path = path + [n["concept"]]
                if n["concept"] == target:
                    found_paths.append(new_path)
                elif n["concept"] not in visited:
                    queue.append(new_path)

        return found_paths

    # ----- Clustering ------------------------------------------------------

    def get_clusters(self, min_size: int = 3) -> list[dict[str, Any]]:
        """
        Detect topic clusters using connected components with weight threshold.
        """
        with get_connection() as conn:
            nodes = conn.execute(
                "SELECT id, concept, domain, importance FROM knowledge_graph_nodes",
            ).fetchall()
            edges = conn.execute(
                "SELECT source_id, target_id, weight FROM knowledge_graph_edges "
                "WHERE weight >= 0.2",
            ).fetchall()

        if not nodes:
            return []

        # Build adjacency list
        adj: dict[int, set[int]] = {}
        for node in nodes:
            adj[node["id"]] = set()
        for edge in edges:
            adj.setdefault(edge["source_id"], set()).add(edge["target_id"])
            adj.setdefault(edge["target_id"], set()).add(edge["source_id"])

        # Find connected components
        visited: set[int] = set()
        components: list[set[int]] = []

        for node in nodes:
            if node["id"] in visited:
                continue
            component: set[int] = set()
            stack = [node["id"]]
            while stack:
                nid = stack.pop()
                if nid in visited:
                    continue
                visited.add(nid)
                component.add(nid)
                for neighbor in adj.get(nid, set()):
                    if neighbor not in visited:
                        stack.append(neighbor)
            components.append(component)

        # Build cluster data
        node_map = {n["id"]: n for n in nodes}
        clusters = []
        for comp in components:
            if len(comp) < min_size:
                continue

            cluster_nodes = [node_map[nid] for nid in comp if nid in node_map]
            concepts = [n["concept"] for n in cluster_nodes]

            # Dominant domain
            from collections import Counter
            domains = Counter(n["domain"] for n in cluster_nodes)
            dominant_domain = domains.most_common(1)[0][0] if domains else "general"

            clusters.append({
                "concepts": concepts,
                "size": len(concepts),
                "domain": dominant_domain,
                "avg_importance": round(
                    sum(n["importance"] for n in cluster_nodes) / len(cluster_nodes), 3
                ),
            })

        clusters.sort(key=lambda c: c["size"], reverse=True)
        return clusters

    def get_important_concepts(self, top_k: int = 10) -> list[dict[str, Any]]:
        """Return the most important concepts in the graph."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT concept, domain, importance, access_count "
                "FROM knowledge_graph_nodes "
                "ORDER BY importance DESC LIMIT ?",
                (top_k,),
            ).fetchall()

        return [dict(r) for r in rows]

    # ----- Concept Extraction ----------------------------------------------

    def extract_concepts_from_text(self, text: str) -> list[str]:
        """
        Extract key concepts from text using tokenization.

        Reuses semantic_memory's tokenizer for consistency.
        """
        from semantic_memory import tokenize
        tokens = tokenize(text)

        if not tokens:
            return []

        # Count frequencies and take most common
        from collections import Counter
        freq = Counter(tokens)
        top = freq.most_common(_MAX_CONCEPTS_PER_TEXT)

        return [term for term, _ in top if len(term) >= _MIN_CONCEPT_LENGTH]

    # ----- Conversation Auto-Update ----------------------------------------

    def update_from_conversation(
        self,
        user_input: str,
        response: str,
        emotion: str = "neutral",
    ) -> int:
        """
        Auto-update the knowledge graph from a conversation turn.

        Extracts concepts from both user input and response,
        then links co-occurring concepts.

        Returns number of edges created/reinforced.
        """
        concepts = self.extract_concepts_from_text(
            f"{user_input} {response}"
        )

        if len(concepts) < 2:
            return 0

        # Add all concepts
        for concept in concepts:
            self.add_concept(concept)

        # Link co-occurring concepts
        edges_updated = 0
        for i in range(len(concepts)):
            for j in range(i + 1, len(concepts)):
                if concepts[i] != concepts[j]:
                    result = self.add_relationship(
                        concepts[i], concepts[j],
                        relationship="related_to",
                        weight=0.3,
                    )
                    if result.get("status") in ("created", "reinforced"):
                        edges_updated += 1

        return edges_updated

    # ----- Conversation Engine Hooks ----------------------------------------

    def observe_concepts(
        self,
        user_input: str,
        workspace_context: str = "general",
    ) -> dict[str, Any]:
        """
        Extract and observe concepts from user input.

        Called by ``conversation_engine`` on each turn.
        Returns summary of new vs reinforced concepts.
        """
        concepts = self.extract_concepts_from_text(user_input)
        new_count = 0
        reinforced_count = 0

        for concept in concepts:
            result = self.add_concept(concept, domain=workspace_context)
            if result.get("status") == "created":
                new_count += 1
            elif result.get("status") == "reinforced":
                reinforced_count += 1

        # Link co-occurring concepts
        edges = 0
        for i in range(len(concepts)):
            for j in range(i + 1, len(concepts)):
                if concepts[i] != concepts[j]:
                    r = self.add_relationship(
                        concepts[i], concepts[j],
                        relationship="related_to", weight=0.3,
                    )
                    if r.get("status") in ("created", "reinforced"):
                        edges += 1

        return {
            "new": new_count,
            "reinforced": reinforced_count,
            "edges": edges,
            "concepts": concepts,
        }

    # ----- Diagnostics -----------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return knowledge graph diagnostic summary."""
        with get_connection() as conn:
            total_nodes = conn.execute(
                "SELECT COUNT(*) FROM knowledge_graph_nodes",
            ).fetchone()[0]
            total_edges = conn.execute(
                "SELECT COUNT(*) FROM knowledge_graph_edges",
            ).fetchone()[0]
            avg_weight = conn.execute(
                "SELECT AVG(weight) FROM knowledge_graph_edges",
            ).fetchone()[0] or 0.0

        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "avg_edge_weight": round(avg_weight, 3),
            "clusters": len(self.get_clusters(min_size=2)),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

knowledge_graph = AdaptiveKnowledgeGraph()
