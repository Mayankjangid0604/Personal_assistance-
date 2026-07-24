"""
Human Oversight Framework for Aisha AI Assistant (Phase 8 Step 1).

Enforces autonomy governance, permission boundaries, interruption safety,
persistent audit trails, and a database-backed rollback/undo framework.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection

class HumanOversightManager:
    """
    Central nervous system for AISHA's human oversight and autonomy constraints.

    Provides database-backed:
        - Autonomy tiers
        - Interruption/pause state
        - Action-specific permission overrides (boundaries)
        - Persistent explainable audit trails
        - Reversible action rollback registry
    """

    def __init__(self) -> None:
        # Default initialization settings if empty
        self._init_default_settings()
        print("  [Oversight] Human Oversight Framework initialized")

    def _init_default_settings(self) -> None:
        """Seed default governance settings if not already present."""
        now = datetime.now().isoformat(timespec="seconds")
        defaults = {
            "autonomy_tier": "2",  # Default to Normal/Confirmation
            "is_paused": "0",      # Default to running/active
        }
        try:
            with get_connection() as conn:
                for key, val in defaults.items():
                    existing = conn.execute(
                        "SELECT key FROM human_oversight_settings WHERE key = ?",
                        (key,),
                    ).fetchone()
                    if not existing:
                        conn.execute(
                            "INSERT INTO human_oversight_settings (key, value, updated_at) "
                            "VALUES (?, ?, ?)",
                            (key, val, now),
                        )
        except Exception as e:
            # Table might not exist yet during initial boot, db.py handles schema creation
            pass

    # ----- Autonomy Tiers & Interruption System ---------------------------

    def get_autonomy_tier(self) -> int:
        """Return the current active autonomy tier (0-3)."""
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM human_oversight_settings WHERE key = 'autonomy_tier'"
                ).fetchone()
                if row:
                    return int(row["value"])
        except Exception:
            pass
        return 2

    def set_autonomy_tier(self, tier: int) -> None:
        """Set the autonomy tier (0=silent, 1=notify, 2=confirmation, 3=full)."""
        tier = max(0, min(3, tier))
        now = datetime.now().isoformat(timespec="seconds")
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO human_oversight_settings (key, value, updated_at) "
                "VALUES ('autonomy_tier', ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (str(tier), now),
            )

    def is_paused(self) -> bool:
        """Check if all autonomous executions are globally paused/interrupted."""
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM human_oversight_settings WHERE key = 'is_paused'"
                ).fetchone()
                if row:
                    return row["value"] == "1"
        except Exception:
            pass
        return False

    def pause_autonomy(self) -> None:
        """Pause all background executions."""
        now = datetime.now().isoformat(timespec="seconds")
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO human_oversight_settings (key, value, updated_at) "
                "VALUES ('is_paused', '1', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (now,),
            )
            # Log interruption event
            conn.execute(
                "INSERT INTO autonomy_audit_log (action_id, action, params_json, attribution, reasoning, confidence, status, detail, risk_level, timestamp) "
                "VALUES (?, 'pause_autonomy', '{}', 'user', 'Global autonomy execution paused by human override', 1.0, 'executed', 'Autonomy paused', 'safe', ?)",
                (f"int-{uuid.uuid4().hex[:8]}", now),
            )

    def resume_autonomy(self) -> None:
        """Resume execution of background tasks."""
        now = datetime.now().isoformat(timespec="seconds")
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO human_oversight_settings (key, value, updated_at) "
                "VALUES ('is_paused', '0', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (now,),
            )
            # Log resume event
            conn.execute(
                "INSERT INTO autonomy_audit_log (action_id, action, params_json, attribution, reasoning, confidence, status, detail, risk_level, timestamp) "
                "VALUES (?, 'resume_autonomy', '{}', 'user', 'Global autonomy execution resumed by human override', 1.0, 'executed', 'Autonomy resumed', 'safe', ?)",
                (f"res-{uuid.uuid4().hex[:8]}", now),
            )

    # ----- Permission Boundaries ------------------------------------------

    def get_action_permission(self, action: str) -> str:
        """
        Get the explicit permission status of an action.
        Returns 'allowed', 'blocked', or 'default'.
        """
        key = f"permission_boundary:{action}"
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM human_oversight_settings WHERE key = ?",
                    (key,),
                ).fetchone()
                if row:
                    return row["value"]
        except Exception:
            pass
        return "default"

    def set_action_permission(self, action: str, status: str) -> None:
        """Set explicit permission boundary override ('allowed', 'blocked', 'default')."""
        if status not in ("allowed", "blocked", "default"):
            raise ValueError("Status must be allowed, blocked, or default")

        key = f"permission_boundary:{action}"
        now = datetime.now().isoformat(timespec="seconds")

        with get_connection() as conn:
            if status == "default":
                conn.execute("DELETE FROM human_oversight_settings WHERE key = ?", (key,))
            else:
                conn.execute(
                    "INSERT INTO human_oversight_settings (key, value, updated_at) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                    (key, status, now),
                )

    # ----- Audit Log & Explainability --------------------------------------

    def log_action(
        self,
        action_id: str,
        action: str,
        params: dict,
        attribution: str,
        reasoning: str,
        confidence: float,
        risk_level: str,
        status: str = "pending",
        detail: str | None = None,
    ) -> None:
        """Log or update an autonomous action record in the persistent audit trail."""
        now = datetime.now().isoformat(timespec="seconds")
        params_json = json.dumps(params)

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO autonomy_audit_log "
                "(action_id, action, params_json, attribution, reasoning, confidence, status, detail, risk_level, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(action_id) DO UPDATE SET "
                "status = excluded.status, "
                "detail = COALESCE(excluded.detail, detail), "
                "timestamp = excluded.timestamp",
                (action_id, action, params_json, attribution, reasoning, confidence, status, detail, risk_level, now),
            )

    def get_audit_log(self, limit: int = 20) -> list[dict[str, Any]]:
        """Retrieve recent persistent audit logs."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM autonomy_audit_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        
        result = []
        for r in rows:
            d = dict(r)
            d["params"] = json.loads(d["params_json"])
            d["reason"] = d.get("reasoning", "")
            result.append(d)
        return result

    # ----- Rollback Framework ----------------------------------------------

    def register_rollback(
        self,
        action_id: str,
        undo_action: str,
        undo_params: dict,
        description: str,
    ) -> None:
        """Register a reversing action for rollback tracking."""
        now = datetime.now().isoformat(timespec="seconds")
        undo_params_json = json.dumps(undo_params)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO rollback_registry "
                "(action_id, undo_action, undo_params_json, description, status, created_at) "
                "VALUES (?, ?, ?, ?, 'active', ?)",
                (action_id, undo_action, undo_params_json, description, now),
            )

    def rollback(self, action_id: str) -> dict[str, Any]:
        """
        Execute the registered rollback for a given action.
        Returns execution status of the undo operation.
        """
        with get_connection() as conn:
            rollback_entry = conn.execute(
                "SELECT * FROM rollback_registry WHERE action_id = ?",
                (action_id,),
            ).fetchone()

        if not rollback_entry:
            return {"status": "error", "message": f"No rollback registered for action '{action_id}'"}

        if rollback_entry["status"] == "rolled_back":
            return {"status": "error", "message": f"Action '{action_id}' has already been rolled back"}

        undo_action = rollback_entry["undo_action"]
        undo_params = json.loads(rollback_entry["undo_params_json"])
        description = rollback_entry["description"]

        # Dispatch the undo logic
        success = False
        message = ""

        try:
            if undo_action == "clipboard_store":
                success = self._rollback_clipboard(undo_params)
                message = "Clipboard restored to previous state."
            elif undo_action == "delete_db_record":
                success = self._rollback_delete_db_record(undo_params)
                message = f"Database record deleted from table '{undo_params.get('table')}'."
            elif undo_action == "execute_sql":
                success = self._rollback_execute_sql(undo_params)
                message = "Database state reverted via custom SQL."
            elif undo_action == "manual":
                # Action cannot be programmatically undone, requiring human manual steps
                success = True
                message = f"Undo requires manual verification: {description}"
            else:
                # Custom or unhandled reversibility gets flagged for manual handling
                success = True
                message = f"Rollback dispatched as manual fallback: {description}"

            status = "rolled_back" if success else "failed"
            now = datetime.now().isoformat(timespec="seconds")

            # Update rollback status
            with get_connection() as conn:
                conn.execute(
                    "UPDATE rollback_registry SET status = ? WHERE action_id = ?",
                    (status, action_id),
                )
                conn.execute(
                    "UPDATE autonomy_audit_log SET status = ?, detail = ? WHERE action_id = ?",
                    (status, f"Rolled back: {message}", action_id),
                )

            return {"status": status, "message": message}

        except Exception as e:
            return {"status": "error", "message": f"Rollback failed: {str(e)}"}

    def get_rollbackable_actions(self) -> list[dict[str, Any]]:
        """Return list of active rollbackable actions."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT r.*, a.action, a.attribution, a.timestamp "
                "FROM rollback_registry r "
                "JOIN autonomy_audit_log a ON r.action_id = a.action_id "
                "WHERE r.status = 'active' ORDER BY r.created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ----- Reversal Helpers ------------------------------------------------

    def _rollback_clipboard(self, params: dict) -> bool:
        """Write text back to system clipboard."""
        text = params.get("text", "")
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(13, text)  # CF_UNICODETEXT
            win32clipboard.CloseClipboard()
            return True
        except Exception:
            return False

    def _rollback_delete_db_record(self, params: dict) -> bool:
        """Delete a record from the local SQLite database."""
        table = params.get("table")
        key_col = params.get("key_col")
        val = params.get("val")

        if not table or not key_col or val is None:
            return False

        # Validate identifiers to prevent SQL injection
        safe_table = "".join(c for c in table if c.isalnum() or c == "_")
        safe_key = "".join(c for c in key_col if c.isalnum() or c == "_")

        try:
            with get_connection() as conn:
                conn.execute(
                    f"DELETE FROM {safe_table} WHERE {safe_key} = ?",
                    (val,),
                )
            return True
        except Exception:
            return False

    def _rollback_execute_sql(self, params: dict) -> bool:
        """Execute a list of SQL queries for state reversion."""
        queries = params.get("queries", [])
        try:
            with get_connection() as conn:
                for q, vals in queries:
                    conn.execute(q, vals)
            return True
        except Exception:
            return False


# Singleton Export
human_oversight = HumanOversightManager()
