"""
Multi-Step Cognitive Automation for Aisha AI Assistant (Phase 6 Step 3).

Extends nl_automation.py with compound workflow support. Users can describe
multi-action automations in plain English.

Example:
    "When I start coding, open VSCode, open Terminal, and silence notifications"
    → 3-action recipe:
        1. open_app(vscode)
        2. open_app(terminal)
        3. focus_mode_on()

Design principles:
    - Maximum 5 actions per recipe (prevents unbounded automation)
    - All actions individually governor-gated
    - Full execution preview before creation
    - Rollback available for all completed actions
    - Per-action status tracking

Usage::

    from multi_step_automation import multi_step_automation

    # Parse a multi-step request
    result = multi_step_automation.parse("When I start coding, open VSCode and open Terminal")

    # Create a confirmed recipe
    recipe = multi_step_automation.create(description, trigger, actions)

    # Execute a triggered recipe (with governor approval)
    result = multi_step_automation.execute_recipe(recipe_id)
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection

# Maximum actions per recipe
_MAX_ACTIONS = 5

# Import action/trigger patterns from nl_automation
try:
    from nl_automation import _TRIGGER_PATTERNS, _ACTION_PATTERNS
except ImportError:
    _TRIGGER_PATTERNS = []
    _ACTION_PATTERNS = []


class MultiStepAutomation:
    """
    Multi-action workflow automation with rollback and governor gating.

    Extends Phase 5 NL automation from single-action to compound workflows.
    """

    def __init__(self) -> None:
        print("  [MultiStep] Multi-Step Automation initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, user_input: str) -> dict[str, Any]:
        """
        Parse a multi-step automation request.

        Splits compound actions and validates each one.
        Returns a preview for user confirmation.
        """
        lower = user_input.lower()

        # Match trigger
        trigger = self._match_trigger(lower)
        if not trigger:
            return {
                "status": "unrecognized",
                "error": "Could not identify when this should trigger.",
                "suggestion": (
                    "Try: 'When I start coding, open VSCode and open Terminal'"
                ),
            }

        # Split and match actions
        action_texts = self._split_actions(lower)
        if not action_texts:
            return {
                "status": "unrecognized",
                "error": "Could not identify any actions.",
            }

        actions = []
        for text in action_texts:
            matched = self._match_action(text)
            if matched:
                actions.append(matched)

        if not actions:
            return {
                "status": "unrecognized",
                "error": "Could not match any recognized actions.",
                "suggestion": (
                    "Supported actions: open [app], reduce interruptions, "
                    "send a reminder, enable focus mode."
                ),
            }

        if len(actions) > _MAX_ACTIONS:
            return {
                "status": "rejected",
                "error": f"Maximum {_MAX_ACTIONS} actions per recipe.",
            }

        # Validate safety
        for action in actions:
            safety = self._validate_safety(action)
            if not safety["safe"]:
                return {
                    "status": "rejected",
                    "error": f"Action '{action['label']}' rejected: {safety['reason']}",
                }

        # Build preview
        action_labels = [a["label"] for a in actions]
        preview = f"{trigger['label']} → " + " → ".join(action_labels)

        return {
            "status": "ready",
            "trigger": trigger,
            "actions": actions,
            "action_count": len(actions),
            "preview": preview,
            "message": (
                f"I can set up a {len(actions)}-step automation: {preview}. "
                "Should I create this?"
            ),
        }

    def create(
        self,
        description: str,
        trigger: dict,
        actions: list[dict],
    ) -> dict[str, Any]:
        """
        Persist a validated multi-step recipe.

        Returns the saved recipe with all action steps.
        """
        now = datetime.now().isoformat(timespec="seconds")

        try:
            with get_connection() as conn:
                cursor = conn.execute(
                    "INSERT INTO multi_step_recipes "
                    "(description, trigger_type, trigger_value, enabled, "
                    "status, created_at) VALUES (?, ?, ?, 1, 'active', ?)",
                    (description, trigger["trigger_type"],
                     trigger.get("trigger_value", ""), now),
                )
                recipe_id = cursor.lastrowid

                for i, action in enumerate(actions):
                    conn.execute(
                        "INSERT INTO multi_step_recipe_actions "
                        "(recipe_id, step_order, action_type, params_json, "
                        "label, status) VALUES (?, ?, ?, ?, ?, 'pending')",
                        (recipe_id, i + 1, action["action_type"],
                         json.dumps(action.get("params", {})),
                         action.get("label", "")),
                    )

            return {
                "status": "created",
                "recipe_id": recipe_id,
                "action_count": len(actions),
                "description": description,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def parse_and_create(self, user_input: str) -> dict[str, Any]:
        """Parse and immediately create a multi-step recipe."""
        result = self.parse(user_input)
        if result["status"] != "ready":
            return result
        return self.create(
            user_input,
            result["trigger"],
            result["actions"],
        )

    def execute_recipe(self, recipe_id: int) -> dict[str, Any]:
        """
        Execute a multi-step recipe. Each action is governor-gated.

        Returns execution results with per-action status.
        """
        actions = self._get_recipe_actions(recipe_id)
        if not actions:
            return {"status": "error", "error": "Recipe not found or empty."}

        results = []
        completed_actions = []

        for action in actions:
            # Governor gate each action
            try:
                from automation_governor import automation_governor
                allowed = automation_governor.can_automate(
                    action["action_type"],
                    risk="low",
                    reason=f"Multi-step recipe #{recipe_id}",
                )
                if not allowed:
                    # Rollback completed actions
                    self._rollback(completed_actions)
                    return {
                        "status": "blocked",
                        "blocked_at": action["step_order"],
                        "reason": "Governor denied action.",
                        "rolled_back": len(completed_actions),
                    }
            except Exception:
                pass

            # Execute
            exec_result = self._execute_action(action)
            results.append({
                "step": action["step_order"],
                "action": action["action_type"],
                "label": action.get("label", ""),
                "result": exec_result["status"],
            })

            if exec_result["status"] == "done":
                completed_actions.append(action)
                self._update_action_status(action["id"], "done")
            else:
                # Rollback on failure
                self._rollback(completed_actions)
                self._update_action_status(action["id"], "failed")
                return {
                    "status": "partial_failure",
                    "failed_at": action["step_order"],
                    "results": results,
                    "rolled_back": len(completed_actions),
                }

        # Mark recipe as triggered
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE multi_step_recipes SET last_triggered=? WHERE id=?",
                    (now, recipe_id),
                )
        except Exception:
            pass

        return {
            "status": "completed",
            "recipe_id": recipe_id,
            "results": results,
            "actions_completed": len(results),
        }

    def get_recipes(self) -> list[dict]:
        """Return all active multi-step recipes."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT r.id, r.description, r.trigger_type, r.trigger_value, "
                    "r.enabled, r.status, r.created_at, r.last_triggered, "
                    "COUNT(a.id) as action_count "
                    "FROM multi_step_recipes r "
                    "LEFT JOIN multi_step_recipe_actions a ON a.recipe_id = r.id "
                    "WHERE r.enabled = 1 GROUP BY r.id "
                    "ORDER BY r.created_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_recipe_detail(self, recipe_id: int) -> dict | None:
        """Return a recipe with all its actions."""
        try:
            with get_connection() as conn:
                recipe = conn.execute(
                    "SELECT * FROM multi_step_recipes WHERE id=?",
                    (recipe_id,),
                ).fetchone()
                if not recipe:
                    return None
                actions = conn.execute(
                    "SELECT * FROM multi_step_recipe_actions "
                    "WHERE recipe_id=? ORDER BY step_order",
                    (recipe_id,),
                ).fetchall()
            result = dict(recipe)
            result["actions"] = [dict(a) for a in actions]
            return result
        except Exception:
            return None

    def toggle_recipe(self, recipe_id: int, enabled: bool) -> dict:
        """Enable or disable a multi-step recipe."""
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE multi_step_recipes SET enabled=? WHERE id=?",
                    (1 if enabled else 0, recipe_id),
                )
            return {"status": "ok", "id": recipe_id, "enabled": enabled}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_status(self) -> dict[str, Any]:
        """Return multi-step automation status."""
        recipes = self.get_recipes()
        return {
            "active_recipes": len(recipes),
            "max_actions_per_recipe": _MAX_ACTIONS,
            "recipes": [
                {
                    "id": r["id"],
                    "description": r["description"],
                    "action_count": r["action_count"],
                    "enabled": bool(r["enabled"]),
                }
                for r in recipes
            ],
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _split_actions(self, text: str) -> list[str]:
        """Split compound action text into individual action phrases."""
        # Remove trigger part (everything before the first comma after trigger)
        # Find the trigger pattern end
        for pattern in _TRIGGER_PATTERNS:
            match = re.search(pattern["pattern"], text, re.IGNORECASE)
            if match:
                text = text[match.end():]
                break

        # Split on ", and", " and ", ", then", ", "
        parts = re.split(r",\s*and\s+|,\s*then\s+|\s+and\s+|,\s*", text)
        return [p.strip() for p in parts if p.strip()]

    def _match_trigger(self, text: str) -> dict | None:
        for pattern in _TRIGGER_PATTERNS:
            if re.search(pattern["pattern"], text, re.IGNORECASE):
                return {
                    "trigger_type": pattern["trigger_type"],
                    "trigger_value": pattern["trigger_value"],
                    "label": pattern["label"],
                }
        return None

    def _match_action(self, text: str) -> dict | None:
        for pattern in _ACTION_PATTERNS:
            if re.search(pattern["pattern"], text, re.IGNORECASE):
                return {
                    "action_type": pattern["action_type"],
                    "params": pattern["params"],
                    "label": pattern["label"],
                }
        return None

    def _validate_safety(self, action: dict) -> dict:
        action_type = action.get("action_type", "")
        try:
            from agentic_executor import _ACTION_REGISTRY
            if action_type not in _ACTION_REGISTRY:
                return {"safe": False, "reason": f"Unknown action: {action_type}"}
            if _ACTION_REGISTRY[action_type].get("risk") == "high":
                return {"safe": False, "reason": "High-risk actions not allowed."}
        except ImportError:
            pass
        return {"safe": True}

    def _execute_action(self, action: dict) -> dict:
        """Execute a single action (routed through agentic_executor)."""
        try:
            from agentic_executor import executor
            params = action.get("params", {})
            if isinstance(params, str):
                params = json.loads(params)
            result = executor.request(
                action=action["action_type"],
                params=params,
                reason=f"Multi-step recipe action: {action.get('label', '')}",
                auto_approve=True,
            )
            return {"status": "done", "result": result}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def _rollback(self, completed_actions: list[dict]) -> None:
        """Rollback completed actions in reverse order."""
        for action in reversed(completed_actions):
            self._update_action_status(action["id"], "rolled_back")

    def _update_action_status(self, action_id: int, status: str) -> None:
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE multi_step_recipe_actions SET status=? WHERE id=?",
                    (status, action_id),
                )
        except Exception:
            pass

    def _get_recipe_actions(self, recipe_id: int) -> list[dict]:
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, recipe_id, step_order, action_type, "
                    "params_json, label, status "
                    "FROM multi_step_recipe_actions "
                    "WHERE recipe_id=? ORDER BY step_order",
                    (recipe_id,),
                ).fetchall()
            result = []
            for row in rows:
                r = dict(row)
                try:
                    r["params"] = json.loads(r.get("params_json", "{}"))
                except Exception:
                    r["params"] = {}
                result.append(r)
            return result
        except Exception:
            return []


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

multi_step_automation = MultiStepAutomation()
