"""
Predictive Workspace Orchestration for AISHA AI Assistant (Phase 8 Step 6).

Implements context preloading based on desktop awareness, device continuity restoration,
and governor-bound safety audits for automated workspace preparation.
"""

from __future__ import annotations

import json
import os
import sys
import logging
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection
from human_oversight import human_oversight
from automation_governor import automation_governor

_log = logging.getLogger("aisha.workspace_orchestration")


class WorkspaceOrchestrator:
    """
    Predictively prepares cognitive workspaces based on user actions, time, and focus.
    """

    def predict_and_preload(self) -> dict[str, Any]:
        """
        Analyze current desktop category and predictively preload relevant workspace nodes.
        Audits the preloading action under governor boundaries.
        """
        action_id = f"preload-{int(datetime.now().timestamp())}"
        
        # 1. Fetch current desktop status
        try:
            from desktop_awareness import desktop_awareness
            status = desktop_awareness.get_status()
            category = status.get("current_category", "general")
        except Exception:
            category = "general"

        # Map desktop category to workspace type
        ws_type = "general"
        if category == "coding":
            ws_type = "software"
        elif category in ("studying", "research"):
            ws_type = "research"

        # 2. Query matching workspaces
        with get_connection() as conn:
            workspace = conn.execute(
                "SELECT * FROM cognitive_workspaces WHERE workspace_type = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
                (ws_type,)
            ).fetchone()
            
            if not workspace:
                # Fallback to any active workspace
                workspace = conn.execute(
                    "SELECT * FROM cognitive_workspaces WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1"
                ).fetchone()

        if not workspace:
            return {"status": "skipped", "reason": "no active workspaces found"}

        workspace = dict(workspace)
        ws_id = workspace["id"]

        # 3. Preload nodes
        with get_connection() as conn:
            nodes = conn.execute("SELECT * FROM workspace_nodes WHERE workspace_id = ? LIMIT 10", (ws_id,)).fetchall()
        
        node_list = [dict(n) for n in nodes]

        # 4. Check governor & Log Audit
        allowed, reason = automation_governor.can_automate(
            source="workspace_orchestrator",
            action="notify", # Treat preload warning as a safe notify category check
            confidence=0.9,
            action_risk="safe"
        )

        if not allowed:
            return {"status": "governor_blocked", "reason": reason}

        human_oversight.log_action(
            action_id=action_id,
            action="preload_workspace",
            params={"workspace_id": ws_id, "category": category, "node_count": len(node_list)},
            attribution="workspace_orchestrator",
            reasoning=f"Predictive preloading workspace '{workspace['title']}' based on desktop category '{category}'.",
            confidence=0.92,
            risk_level="safe",
            status="executed"
        )

        # Preloading is side-effect free, so rollback is a clean no-op
        human_oversight.register_rollback(
            action_id=action_id,
            undo_action="manual",
            undo_params={},
            description="Predictive preloading is memory-only; no database undo required."
        )

        return {
            "status": "success",
            "action_id": action_id,
            "workspace_id": ws_id,
            "title": workspace["title"],
            "nodes_preloaded": len(node_list),
            "nodes": node_list
        }

    def restore_continuity_state(self, device_id: str) -> dict[str, Any]:
        """
        Pull continuity session state from database for a specific device.
        """
        with get_connection() as conn:
            session = conn.execute(
                "SELECT * FROM device_sessions WHERE device_id = ? ORDER BY session_start DESC LIMIT 1",
                (device_id,)
            ).fetchone()

        if not session:
            return {"status": "no_session", "device_id": device_id}

        session = dict(session)
        state = json.loads(session.get("cognitive_state_json") or "{}")

        return {
            "status": "success",
            "device_id": device_id,
            "device_name": session.get("device_name"),
            "session_start": session.get("session_start"),
            "cognitive_state": state
        }


# Singleton export
workspace_orchestrator = WorkspaceOrchestrator()
