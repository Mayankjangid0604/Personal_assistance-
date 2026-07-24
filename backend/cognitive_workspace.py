"""
Shared Cognitive Workspace for Aisha AI Assistant (Phase 7 Step 2).

Persistent collaborative idea spaces with concept linking, idea trees,
contextual references, thought continuity, and workspace summarization.

Workspace types:
    general         -- open-ended thinking space
    brainstorm      -- structured brainstorming sessions
    research_map    -- research topic mapping
    project_plan    -- project planning and architecture
    idea_evolution  -- tracking how ideas develop over time

Node types:
    note       -- simple text note
    idea       -- a distinct idea or proposal
    concept    -- an abstract concept or principle
    question   -- an open question to explore
    reference  -- a source or citation
    insight    -- a derived observation or conclusion

Link relationships:
    related       -- general association
    supports      -- evidence or argument for
    contradicts   -- conflicting information
    extends       -- builds upon
    derived_from  -- originated from
    inspires      -- creative stimulus

Design principles:
    - Workspaces are persistent "thinking boards" across sessions
    - Linking is lightweight — encourages exploration not rigidity
    - Summarization provides continuity without requiring re-read
    - No prescriptive structure imposed on user's thinking

Usage::

    from cognitive_workspace import cognitive_workspace

    ws = cognitive_workspace.create_workspace("Phase 7 Architecture")
    cognitive_workspace.add_node(ws["id"], "Project tracking needs milestones")
    cognitive_workspace.add_node(ws["id"], "Knowledge graph should be lightweight")
    cognitive_workspace.link_nodes(1, 2, "related")
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_WORKSPACE_TYPES = {
    "general", "brainstorm", "research_map", "project_plan", "idea_evolution",
}

_VALID_NODE_TYPES = {
    "note", "idea", "concept", "question", "reference", "insight",
}

_VALID_RELATIONSHIPS = {
    "related", "supports", "contradicts", "extends", "derived_from", "inspires",
}

_VALID_STATUSES = {"active", "archived"}


# ---------------------------------------------------------------------------
# Cognitive Workspace Engine
# ---------------------------------------------------------------------------

class CognitiveWorkspace:
    """
    Persistent collaborative idea spaces with concept linking.

    Writes directly to ``cognitive_workspaces``, ``workspace_nodes``,
    and ``node_links`` tables.
    """

    def __init__(self) -> None:
        print("  [CognitiveWorkspace] Initialized")

    # ----- Workspace CRUD --------------------------------------------------

    def create_workspace(
        self,
        title: str,
        description: str = "",
        workspace_type: str = "general",
    ) -> dict[str, Any]:
        """Create a new workspace."""
        workspace_type = workspace_type if workspace_type in _VALID_WORKSPACE_TYPES else "general"
        now = datetime.now().isoformat(timespec="seconds")

        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO cognitive_workspaces "
                "(title, description, workspace_type, status, summary, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, 'active', NULL, ?, ?)",
                (title, description, workspace_type, now, now),
            )
            ws_id = cursor.lastrowid

        return {
            "status": "created",
            "id": ws_id,
            "title": title,
            "workspace_type": workspace_type,
        }

    def archive_workspace(self, workspace_id: int) -> dict[str, Any]:
        """Archive a workspace (soft delete)."""
        now = datetime.now().isoformat(timespec="seconds")
        with get_connection() as conn:
            conn.execute(
                "UPDATE cognitive_workspaces SET status = 'archived', "
                "updated_at = ? WHERE id = ?",
                (now, workspace_id),
            )
        return {"status": "archived", "id": workspace_id}

    # ----- Node Operations -------------------------------------------------

    def add_node(
        self,
        workspace_id: int,
        content: str,
        node_type: str = "note",
        tags: list[str] | None = None,
        importance: float = 0.5,
    ) -> dict[str, Any]:
        """Add a node (idea/note/concept) to a workspace."""
        node_type = node_type if node_type in _VALID_NODE_TYPES else "note"
        importance = max(0.0, min(1.0, importance))
        tags_json = json.dumps(tags or [])
        now = datetime.now().isoformat(timespec="seconds")

        with get_connection() as conn:
            # Verify workspace exists
            ws = conn.execute(
                "SELECT id FROM cognitive_workspaces WHERE id = ?",
                (workspace_id,),
            ).fetchone()
            if not ws:
                return {"status": "error", "error": "Workspace not found"}

            cursor = conn.execute(
                "INSERT INTO workspace_nodes "
                "(workspace_id, content, node_type, importance, tags_json, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (workspace_id, content, node_type, importance, tags_json, now, now),
            )
            node_id = cursor.lastrowid

            # Update workspace timestamp
            conn.execute(
                "UPDATE cognitive_workspaces SET updated_at = ? WHERE id = ?",
                (now, workspace_id),
            )

        return {
            "status": "created",
            "id": node_id,
            "workspace_id": workspace_id,
            "node_type": node_type,
        }

    def update_node(
        self, node_id: int, **kwargs: Any,
    ) -> dict[str, Any]:
        """Update a workspace node. Accepts: content, node_type, importance, tags."""
        allowed = {"content", "node_type", "importance"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}

        if "tags" in kwargs:
            updates["tags_json"] = json.dumps(kwargs["tags"])
        if "node_type" in updates and updates["node_type"] not in _VALID_NODE_TYPES:
            return {"status": "error", "error": f"Invalid node_type: {updates['node_type']}"}
        if "importance" in updates:
            updates["importance"] = max(0.0, min(1.0, float(updates["importance"])))

        if not updates:
            return {"status": "no_changes"}

        updates["updated_at"] = datetime.now().isoformat(timespec="seconds")

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [node_id]

        with get_connection() as conn:
            conn.execute(
                f"UPDATE workspace_nodes SET {set_clause} WHERE id = ?",
                values,
            )

        return {"status": "updated", "id": node_id}

    # ----- Link Operations -------------------------------------------------

    def link_nodes(
        self,
        source_id: int,
        target_id: int,
        relationship: str = "related",
        weight: float = 0.5,
    ) -> dict[str, Any]:
        """Create a link between two workspace nodes."""
        relationship = relationship if relationship in _VALID_RELATIONSHIPS else "related"
        weight = max(0.0, min(1.0, weight))
        now = datetime.now().isoformat(timespec="seconds")

        with get_connection() as conn:
            # Check if link already exists
            existing = conn.execute(
                "SELECT id FROM node_links "
                "WHERE source_id = ? AND target_id = ?",
                (source_id, target_id),
            ).fetchone()

            if existing:
                # Update existing link
                conn.execute(
                    "UPDATE node_links SET relationship = ?, weight = ?, "
                    "created_at = ? WHERE id = ?",
                    (relationship, weight, now, existing["id"]),
                )
                return {"status": "updated", "id": existing["id"]}

            cursor = conn.execute(
                "INSERT INTO node_links "
                "(source_id, target_id, relationship, weight, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (source_id, target_id, relationship, weight, now),
            )
            link_id = cursor.lastrowid

        return {
            "status": "created",
            "id": link_id,
            "source_id": source_id,
            "target_id": target_id,
            "relationship": relationship,
        }

    # ----- Retrieval -------------------------------------------------------

    def get_workspace(self, workspace_id: int) -> dict[str, Any] | None:
        """Get a workspace with all its nodes and links."""
        with get_connection() as conn:
            ws = conn.execute(
                "SELECT * FROM cognitive_workspaces WHERE id = ?",
                (workspace_id,),
            ).fetchone()
            if not ws:
                return None

            nodes = conn.execute(
                "SELECT * FROM workspace_nodes "
                "WHERE workspace_id = ? ORDER BY importance DESC",
                (workspace_id,),
            ).fetchall()

            node_ids = [n["id"] for n in nodes]
            links = []
            if node_ids:
                placeholders = ",".join("?" for _ in node_ids)
                links = conn.execute(
                    f"SELECT * FROM node_links "
                    f"WHERE source_id IN ({placeholders}) "
                    f"OR target_id IN ({placeholders})",
                    node_ids + node_ids,
                ).fetchall()

        result = dict(ws)
        result["nodes"] = [self._node_to_dict(n) for n in nodes]
        result["links"] = [dict(l) for l in links]
        return result

    def get_active_workspaces(self) -> list[dict[str, Any]]:
        """Return all active workspaces with node counts."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT w.*, "
                "(SELECT COUNT(*) FROM workspace_nodes WHERE workspace_id = w.id) as node_count "
                "FROM cognitive_workspaces w "
                "WHERE w.status = 'active' "
                "ORDER BY w.updated_at DESC",
            ).fetchall()

        return [dict(r) for r in rows]

    def search_nodes(
        self,
        query: str,
        workspace_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Search across workspace nodes by keyword."""
        query_pattern = f"%{query}%"

        with get_connection() as conn:
            if workspace_id:
                rows = conn.execute(
                    "SELECT * FROM workspace_nodes "
                    "WHERE workspace_id = ? AND content LIKE ? "
                    "ORDER BY importance DESC LIMIT 20",
                    (workspace_id, query_pattern),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM workspace_nodes "
                    "WHERE content LIKE ? "
                    "ORDER BY importance DESC LIMIT 20",
                    (query_pattern,),
                ).fetchall()

        return [self._node_to_dict(r) for r in rows]

    def get_related_nodes(self, node_id: int) -> list[dict[str, Any]]:
        """Find all nodes connected to the given node."""
        with get_connection() as conn:
            # Find all linked node IDs
            links = conn.execute(
                "SELECT source_id, target_id, relationship, weight "
                "FROM node_links "
                "WHERE source_id = ? OR target_id = ?",
                (node_id, node_id),
            ).fetchall()

            related_ids = set()
            link_info: dict[int, dict] = {}
            for link in links:
                other_id = link["target_id"] if link["source_id"] == node_id else link["source_id"]
                related_ids.add(other_id)
                link_info[other_id] = {
                    "relationship": link["relationship"],
                    "weight": link["weight"],
                }

            if not related_ids:
                return []

            placeholders = ",".join("?" for _ in related_ids)
            nodes = conn.execute(
                f"SELECT * FROM workspace_nodes WHERE id IN ({placeholders})",
                list(related_ids),
            ).fetchall()

        results = []
        for node in nodes:
            d = self._node_to_dict(node)
            d["link"] = link_info.get(node["id"], {})
            results.append(d)

        return results

    def get_idea_tree(self, workspace_id: int) -> dict[str, Any]:
        """
        Build a hierarchical view of linked nodes in a workspace.

        Returns a tree structure with root nodes (nodes with no incoming links)
        and their descendants.
        """
        ws = self.get_workspace(workspace_id)
        if not ws:
            return {"workspace_id": workspace_id, "roots": []}

        nodes_by_id = {n["id"]: n for n in ws["nodes"]}
        has_parent = set()

        for link in ws["links"]:
            if link["relationship"] in ("extends", "derived_from", "supports"):
                has_parent.add(link["source_id"])

        # Root nodes = nodes with no parent relationships
        roots = [n for n in ws["nodes"] if n["id"] not in has_parent]

        # Build children map
        children_map: dict[int, list[dict]] = {}
        for link in ws["links"]:
            parent_id = link["target_id"]
            child_id = link["source_id"]
            if parent_id in nodes_by_id and child_id in nodes_by_id:
                children_map.setdefault(parent_id, []).append(
                    nodes_by_id[child_id]
                )

        def _build_tree(node: dict, depth: int = 0) -> dict:
            tree_node = {**node, "children": [], "depth": depth}
            if depth < 5:  # Prevent infinite recursion
                for child in children_map.get(node["id"], []):
                    tree_node["children"].append(_build_tree(child, depth + 1))
            return tree_node

        return {
            "workspace_id": workspace_id,
            "title": ws["title"],
            "roots": [_build_tree(r) for r in roots],
        }

    # ----- Summarization ---------------------------------------------------

    def summarize_workspace(self, workspace_id: int) -> str:
        """
        Generate a concise summary of a workspace.

        Concatenates top-importance nodes with relationship context.
        """
        ws = self.get_workspace(workspace_id)
        if not ws:
            return ""

        nodes = ws.get("nodes", [])
        if not nodes:
            return f"Workspace '{ws['title']}' is empty."

        # Sort by importance, take top nodes
        sorted_nodes = sorted(nodes, key=lambda n: n.get("importance", 0), reverse=True)
        top_nodes = sorted_nodes[:8]

        parts = [f"Workspace '{ws['title']}' ({ws.get('workspace_type', 'general')}):"]

        for node in top_nodes:
            node_type = node.get("node_type", "note")
            content = node["content"][:120]
            parts.append(f"  [{node_type}] {content}")

        # Note any contradictions
        contradictions = [
            l for l in ws.get("links", [])
            if l["relationship"] == "contradicts"
        ]
        if contradictions:
            parts.append(f"  ({len(contradictions)} noted contradiction(s))")

        summary = "\n".join(parts)

        # Cache the summary
        now = datetime.now().isoformat(timespec="seconds")
        with get_connection() as conn:
            conn.execute(
                "UPDATE cognitive_workspaces SET summary = ?, updated_at = ? "
                "WHERE id = ?",
                (summary, now, workspace_id),
            )

        return summary

    # ----- Conversation Engine Hooks ---------------------------------------

    def find_connections(self, user_input: str) -> list[dict[str, Any]]:
        """
        Find workspace nodes related to the user's current input.

        Called by ``conversation_engine`` on each turn.
        Returns matching nodes across all active workspaces.
        """
        return self.search_nodes(user_input)[:5]

    # ----- Diagnostics -----------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return cognitive workspace diagnostic summary."""
        with get_connection() as conn:
            total_ws = conn.execute(
                "SELECT COUNT(*) FROM cognitive_workspaces",
            ).fetchone()[0]
            active_ws = conn.execute(
                "SELECT COUNT(*) FROM cognitive_workspaces WHERE status = 'active'",
            ).fetchone()[0]
            total_nodes = conn.execute(
                "SELECT COUNT(*) FROM workspace_nodes",
            ).fetchone()[0]
            total_links = conn.execute(
                "SELECT COUNT(*) FROM node_links",
            ).fetchone()[0]

        return {
            "total_workspaces": total_ws,
            "active_workspaces": active_ws,
            "total_nodes": total_nodes,
            "total_links": total_links,
        }

    # ----- Helpers ---------------------------------------------------------

    @staticmethod
    def _node_to_dict(row: Any) -> dict[str, Any]:
        """Convert a workspace_nodes row to a dict with parsed tags."""
        d = dict(row)
        try:
            d["tags"] = json.loads(d.get("tags_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            d["tags"] = []
        return d


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

cognitive_workspace = CognitiveWorkspace()
