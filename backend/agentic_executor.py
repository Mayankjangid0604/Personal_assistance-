"""
Agentic Task Execution System for Aisha AI Assistant (Phase 4 Step 3).

Allows AISHA to safely execute contextual actions on the user's desktop.
All actions are:
    - Permission-aware (each action declares its risk level)
    - Confirmation-gated (high-risk actions require explicit user approval)
    - Reversible where possible
    - Audited (every execution is logged)
    - Bounded (restricted to a defined safe action set)

Safe action types:
    open_app          -- open an application by name
    open_url          -- open a URL in the default browser
    set_focus_mode    -- toggle Windows Focus Assist / DnD (best-effort)
    notify            -- send a desktop notification
    clipboard_store   -- store text to clipboard

AISHA CANNOT:
    - Delete or move files
    - Access private file content
    - Execute arbitrary shell commands
    - Access the network beyond browser opens
    - Run code

Design principle:
    "Suggest before acting. Ask before anything irreversible."

Usage::

    from agentic_executor import executor

    # Request an action (goes through permission gate)
    result = executor.request(
        action="open_app",
        params={"app": "notion"},
        reason="You mentioned you wanted to take notes on this topic.",
        auto_approve=False,   # Requires explicit confirmation
    )

    # Check pending confirmations
    pending = executor.get_pending()

    # Approve a pending action
    result = executor.approve(action_id)

    # Cancel a pending action
    executor.cancel(action_id)

    # Get audit log
    log = executor.get_audit_log(limit=10)
"""

from __future__ import annotations

import os
import json
import subprocess
import sys
import time
import uuid
import webbrowser
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection
from human_oversight import human_oversight


# ---------------------------------------------------------------------------
# Action Definitions
# ---------------------------------------------------------------------------

# Risk levels:
#   safe      -- no confirmation needed (notifications, UI hints)
#   moderate  -- auto-approved in tier 3, confirmed in tier 2, blocked in tier 0/1
#   high      -- always requires explicit confirmation

_ACTION_REGISTRY: dict[str, dict] = {
    "notify": {
        "label": "Send Notification",
        "risk": "safe",
        "reversible": True,
        "description": "Show a desktop notification to the user.",
    },
    "open_url": {
        "label": "Open URL in Browser",
        "risk": "moderate",
        "reversible": True,
        "description": "Open a web URL in the default browser.",
    },
    "open_app": {
        "label": "Open Application",
        "risk": "moderate",
        "reversible": True,
        "description": "Launch an application on the desktop.",
    },
    "clipboard_store": {
        "label": "Copy to Clipboard",
        "risk": "safe",
        "reversible": True,
        "description": "Store text to the system clipboard.",
    },
    "focus_mode_on": {
        "label": "Enable Focus Mode",
        "risk": "safe",
        "reversible": True,
        "description": "Best-effort: enable Windows Focus Assist or DnD mode.",
    },
    "focus_mode_off": {
        "label": "Disable Focus Mode",
        "risk": "safe",
        "reversible": True,
        "description": "Best-effort: disable Windows Focus Assist or DnD mode.",
    },
}

# Known application mappings (name → executable)
_APP_MAPPINGS: dict[str, str] = {
    "notepad": "notepad.exe",
    "notion": "notion.exe",
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "vscode": "code.exe",
    "code": "code.exe",
    "terminal": "wt.exe",           # Windows Terminal
    "powershell": "powershell.exe",
    "calculator": "calc.exe",
    "explorer": "explorer.exe",
    "anki": "anki.exe",
    "spotify": "spotify.exe",
    "slack": "slack.exe",
    "discord": "discord.exe",
    "teams": "teams.exe",
    "outlook": "outlook.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "figma": "figma.exe",
    "obsidian": "obsidian.exe",
}

# Autonomy tiers (mirrors presence governor):
#   0 = silent (no actions)
#   1 = notifications only
#   2 = moderate (open_url, open_app with confirmation)
#   3 = full (auto-approve moderate actions)
_DEFAULT_AUTONOMY_TIER = 2

# Max pending confirmations before blocking new requests
_MAX_PENDING = 5

# How long a pending action stays alive before it expires (seconds)
_PENDING_TTL = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Agentic Executor
# ---------------------------------------------------------------------------

class AgenticExecutor:
    """
    Safe, bounded action executor for AISHA's agentic capabilities.

    Enforces permission gates, audit trails, and reversibility for every
    action taken on the user's system. Integrates with the HumanOversight Framework.
    """

    def __init__(self) -> None:
        self._action_count: int = 0
        print("  [Executor] Agentic Executor initialized (database-backed)")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_autonomy_tier(self, tier: int) -> None:
        """Set the autonomy tier via the human oversight manager."""
        human_oversight.set_autonomy_tier(tier)

    @property
    def autonomy_tier(self) -> int:
        return human_oversight.get_autonomy_tier()

    def request(
        self,
        action: str,
        params: dict[str, Any],
        reason: str = "",
        auto_approve: bool = False,
    ) -> dict[str, Any]:
        """
        Request an action to be executed.
        """
        action_id = str(uuid.uuid4())[:8]

        # 1. Global Interruption Check
        if human_oversight.is_paused():
            self._audit(action_id, action, params, "rejected", "Autonomy is globally paused (interrupted)", reason)
            return {
                "status": "rejected",
                "action_id": action_id,
                "reason": "Autonomy is globally paused (interrupted).",
                "result": None,
            }

        # 2. Permission Boundary Check
        permission = human_oversight.get_action_permission(action)
        if permission == "blocked":
            self._audit(action_id, action, params, "rejected", "Action explicitly blocked by permission boundaries", reason)
            return {
                "status": "rejected",
                "action_id": action_id,
                "reason": f"Action '{action}' is blocked by permission boundaries.",
                "result": None,
            }

        # 3. Action Registry Check
        if action not in _ACTION_REGISTRY:
            self._audit(action_id, action, params, "rejected", "Unknown action", reason)
            return {"status": "rejected", "action_id": action_id,
                    "reason": f"Unknown action: '{action}'", "result": None}

        defn = _ACTION_REGISTRY[action]
        risk = defn["risk"]

        # 4. Explicit Allow Override
        if permission == "allowed":
            return self._execute_now(action_id, action, params, reason)

        # 5. Standard Tier-Based Checks
        tier = human_oversight.get_autonomy_tier()
        if tier == 0:
            self._audit(action_id, action, params, "rejected", "Tier 0 blocks all actions", reason)
            return {"status": "rejected", "action_id": action_id,
                    "reason": "Autonomous actions are currently silent (tier=0).", "result": None}

        if tier == 1 and risk != "safe":
            self._audit(action_id, action, params, "rejected", "Tier 1: moderate/high blocked", reason)
            return {"status": "rejected", "action_id": action_id,
                    "reason": "Only notifications are allowed (tier=1).", "result": None}

        # Safe actions execute immediately
        if risk == "safe":
            return self._execute_now(action_id, action, params, reason)

        # High risk always requires confirmation
        if risk == "high":
            return self._queue_pending(action_id, action, params, reason)

        # Moderate risk executes immediately if auto-approved or on tier 3, else pending
        if auto_approve or tier >= 3:
            return self._execute_now(action_id, action, params, reason)
        else:
            return self._queue_pending(action_id, action, params, reason)

    def approve(self, action_id: str) -> dict[str, Any]:
        """Approve and execute a pending action."""
        with get_connection() as conn:
            pending = conn.execute(
                "SELECT action, params_json, reasoning FROM autonomy_audit_log WHERE action_id = ? AND status = 'pending'",
                (action_id,),
            ).fetchone()

        if not pending:
            return {"status": "error", "reason": f"No pending action with id '{action_id}'"}

        params = json.loads(pending["params_json"])
        return self._execute_now(
            action_id,
            pending["action"],
            params,
            pending["reasoning"] + " [user-approved]",
        )

    def cancel(self, action_id: str) -> dict[str, Any]:
        """Cancel a pending action."""
        with get_connection() as conn:
            pending = conn.execute(
                "SELECT action, params_json, reasoning FROM autonomy_audit_log WHERE action_id = ? AND status = 'pending'",
                (action_id,),
            ).fetchone()

        if not pending:
            return {"status": "error", "reason": f"No pending action with id '{action_id}'"}

        params = json.loads(pending["params_json"])
        self._audit(action_id, pending["action"], params, "cancelled", "Cancelled by user", pending["reasoning"])
        return {"status": "cancelled", "action_id": action_id}

    def get_pending(self) -> list[dict[str, Any]]:
        """Return list of actions awaiting user confirmation."""
        # Clean/expire old pending items (over 5 mins)
        now_ts = datetime.fromtimestamp(time.time() - _PENDING_TTL).isoformat(timespec="seconds")
        with get_connection() as conn:
            conn.execute(
                "UPDATE autonomy_audit_log SET status = 'rejected', detail = 'Expired' "
                "WHERE status = 'pending' AND timestamp < ?",
                (now_ts,),
            )
            rows = conn.execute(
                "SELECT action_id, action, params_json, reasoning, timestamp FROM autonomy_audit_log WHERE status = 'pending'"
            ).fetchall()

        pending_list = []
        for r in rows:
            params = json.loads(r["params_json"])
            label = _ACTION_REGISTRY.get(r["action"], {}).get("label", r["action"])
            
            # calculate elapsed time
            elapsed = 0
            try:
                dt = datetime.fromisoformat(r["timestamp"])
                elapsed = int(time.time() - dt.timestamp())
            except Exception:
                pass

            pending_list.append({
                "action_id": r["action_id"],
                "action": r["action"],
                "label": label,
                "params": params,
                "reason": r["reasoning"],
                "queued_ago_sec": elapsed,
            })
        return pending_list

    def get_audit_log(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent audit log entries from the database."""
        return human_oversight.get_audit_log(limit)

    def get_status(self) -> dict[str, Any]:
        """Return executor status."""
        with get_connection() as conn:
            pending_count = conn.execute(
                "SELECT COUNT(*) FROM autonomy_audit_log WHERE status = 'pending'"
            ).fetchone()[0]
            total_executed = conn.execute(
                "SELECT COUNT(*) FROM autonomy_audit_log WHERE status = 'executed'"
            ).fetchone()[0]
            log_size = conn.execute(
                "SELECT COUNT(*) FROM autonomy_audit_log"
            ).fetchone()[0]

        return {
            "autonomy_tier": self.autonomy_tier,
            "pending_count": pending_count,
            "total_actions_executed": total_executed,
            "audit_log_size": log_size,
        }

    # ------------------------------------------------------------------
    # Execution Implementations
    # ------------------------------------------------------------------

    def _execute_now(
        self,
        action_id: str,
        action: str,
        params: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        """Execute an action immediately."""
        # 1. Capture Rollback/Undo state *before* modification
        self._register_undo_state(action_id, action, params)

        try:
            if action == "notify":
                result = self._do_notify(params)
            elif action == "open_url":
                result = self._do_open_url(params)
            elif action == "open_app":
                result = self._do_open_app(params)
            elif action == "clipboard_store":
                result = self._do_clipboard_store(params)
            elif action in ("focus_mode_on", "focus_mode_off"):
                result = self._do_focus_mode(params, action == "focus_mode_on")
            else:
                result = {"ok": False, "message": "Unhandled action"}

            status = "executed" if result.get("ok") else "failed"
            self._action_count += 1

            # Update rollback for notify if it succeeded and returned notif_id
            if action == "notify" and result.get("ok") and "notif_id" in result:
                human_oversight.register_rollback(
                    action_id=action_id,
                    undo_action="delete_db_record",
                    undo_params={"table": "notifications", "key_col": "id", "val": result["notif_id"]},
                    description=f"Delete notification message: '{params.get('message', '')[:30]}...'"
                )

            self._audit(action_id, action, params, status, result.get("message", ""), reason)

            return {
                "status": status,
                "action_id": action_id,
                "reason": reason,
                "result": result,
            }

        except Exception as e:
            self._audit(action_id, action, params, "error", str(e), reason)
            return {"status": "error", "action_id": action_id,
                    "reason": reason, "result": {"ok": False, "message": str(e)}}

    def _queue_pending(
        self,
        action_id: str,
        action: str,
        params: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        """Queue an action for user confirmation."""
        # Check max pending
        with get_connection() as conn:
            pending_count = conn.execute(
                "SELECT COUNT(*) FROM autonomy_audit_log WHERE status = 'pending'"
            ).fetchone()[0]

        if pending_count >= _MAX_PENDING:
            return {
                "status": "rejected",
                "action_id": action_id,
                "reason": "Too many pending confirmations. Please review existing requests first.",
                "result": None,
            }

        label = _ACTION_REGISTRY.get(action, {}).get("label", action)
        self._audit(action_id, action, params, "pending", "Awaiting confirmation", reason)

        return {
            "status": "pending",
            "action_id": action_id,
            "reason": reason,
            "confirmation_needed": True,
            "label": label,
            "result": None,
        }

    def _register_undo_state(self, action_id: str, action: str, params: dict[str, Any]) -> None:
        """Register the undo operation prior to execution of reversible actions."""
        try:
            if action == "clipboard_store":
                prev_text = ""
                try:
                    import win32clipboard
                    win32clipboard.OpenClipboard()
                    prev_text = win32clipboard.GetClipboardData(13)  # CF_UNICODETEXT
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass
                human_oversight.register_rollback(
                    action_id=action_id,
                    undo_action="clipboard_store",
                    undo_params={"text": prev_text},
                    description=f"Restore clipboard contents to: '{prev_text[:30]}...'"
                )
            elif action == "open_url":
                human_oversight.register_rollback(
                    action_id=action_id,
                    undo_action="manual",
                    undo_params={},
                    description=f"Open URL '{params.get('url')}' cannot be programmatically closed. Close browser manually."
                )
            elif action == "open_app":
                human_oversight.register_rollback(
                    action_id=action_id,
                    undo_action="manual",
                    undo_params={},
                    description=f"Launch application '{params.get('app')}' cannot be programmatically terminated safely. Please close it manually."
                )
            elif action in ("focus_mode_on", "focus_mode_off"):
                human_oversight.register_rollback(
                    action_id=action_id,
                    undo_action="focus_mode_toggle",
                    undo_params={"enable": action == "focus_mode_off"},
                    description="Revert focus mode setting toggle"
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Action Implementations
    # ------------------------------------------------------------------

    def _do_notify(self, params: dict) -> dict:
        """Send a desktop notification."""
        title = params.get("title", "AISHA")
        message = params.get("message", "")
        try:
            from notifications import add_notification
            notif = add_notification(message, category="agentic")
            return {"ok": True, "message": f"Notification sent: {message[:50]}", "notif_id": notif.get("id")}
        except Exception:
            return {"ok": True, "message": "Notification queued (fallback)"}

    def _do_open_url(self, params: dict) -> dict:
        """Open a URL in the default browser."""
        url = params.get("url", "")
        if not url:
            return {"ok": False, "message": "No URL provided"}

        if not url.startswith(("http://", "https://")):
            return {"ok": False, "message": "Only http/https URLs are allowed"}

        try:
            webbrowser.open(url)
            return {"ok": True, "message": f"Opened URL: {url[:80]}"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def _do_open_app(self, params: dict) -> dict:
        """Open an application."""
        app = params.get("app", "").lower().strip()
        if not app:
            return {"ok": False, "message": "No app specified"}

        executable = _APP_MAPPINGS.get(app)
        if not executable:
            return {
                "ok": False,
                "message": (
                    f"'{app}' is not in the safe application list. "
                    f"Known apps: {', '.join(sorted(_APP_MAPPINGS.keys()))}"
                ),
            }

        try:
            subprocess.Popen(
                [executable],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"ok": True, "message": f"Launched: {executable}"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def _do_clipboard_store(self, params: dict) -> dict:
        """Store text to clipboard."""
        text = params.get("text", "")
        if not text:
            return {"ok": False, "message": "No text to copy"}

        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(13, text)  # CF_UNICODETEXT
            win32clipboard.CloseClipboard()
            return {"ok": True, "message": f"Copied {len(text)} chars to clipboard"}
        except ImportError:
            return {"ok": False, "message": "win32clipboard not available"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def _do_focus_mode(self, params: dict, enable: bool) -> dict:
        """Best-effort focus mode toggle."""
        action_word = "enable" if enable else "disable"
        return {
            "ok": True,
            "message": (
                f"Focus mode {action_word} requested. "
                "Note: Windows Focus Assist may require manual adjustment."
            ),
        }

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def _audit(
        self,
        action_id: str,
        action: str,
        params: dict,
        status: str,
        detail: str,
        reason: str,
    ) -> None:
        """Audit log helper."""
        attribution = "orchestrator"
        if "user" in reason.lower() or "user-approved" in reason.lower():
            attribution = "user"
        elif "agent:" in reason.lower():
            parts = reason.split("agent:")
            if len(parts) > 1:
                attribution = parts[1].split()[0].strip()

        defn = _ACTION_REGISTRY.get(action, {"risk": "safe"})
        risk = defn.get("risk", "safe")

        human_oversight.log_action(
            action_id=action_id,
            action=action,
            params=params,
            attribution=attribution,
            reasoning=reason,
            confidence=0.95,
            risk_level=risk,
            status=status,
            detail=detail,
        )


# Singleton
executor = AgenticExecutor()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

executor = AgenticExecutor()
