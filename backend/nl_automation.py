"""
Natural Language Automation System for Aisha AI Assistant (Phase 5 Step 4).

Allows users to describe automations in plain English. AISHA parses the
intent, creates a validated automation recipe, simulates it first, and
routes all execution through the existing AutomationGovernor.

Example user phrases:
    "When I start coding, open the browser"
    "During study sessions, silence distractions"
    "At night, reduce interruptions"
    "Remind me to take a break after long focus sessions"

Recipe anatomy:
    trigger_type:  what causes the automation
        workflow_start    -- a specific workflow begins
        time_of_day       -- a time-of-day condition
        emotion_state     -- a detected emotional state
        category_active   -- an app category becomes active
        burnout_signal    -- burnout risk reaches a threshold

    action_type: what AISHA does (from agentic_executor registry)
        notify            -- send a desktop notification
        open_url          -- open a URL
        open_app          -- open an application
        clipboard_store   -- store something to clipboard
        focus_mode_on     -- enable focus mode
        focus_mode_off    -- disable focus mode

All recipes are:
    - Gated through AutomationGovernor before any execution
    - Reversible (all implemented actions are reversible)
    - User-approachable (can be listed, toggled, deleted)
    - Simulated before first activation

Usage::

    from nl_automation import nl_automation

    # Parse a natural language automation request
    recipe = nl_automation.parse("When I start coding, open VSCode")

    # Get all active recipes
    recipes = nl_automation.get_active_recipes()

    # Check and execute triggered recipes for current state
    triggered = nl_automation.check_triggers(desktop_snapshot, emotion)
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


# ---------------------------------------------------------------------------
# Trigger Patterns (NLP Rules)
# ---------------------------------------------------------------------------

_TRIGGER_PATTERNS: list[dict] = [
    # Workflow triggers
    {
        "pattern": r"when i (start|begin|open) (coding|programming|writing code)",
        "trigger_type": "workflow_start",
        "trigger_value": "deep_coding",
        "label": "when coding starts",
    },
    {
        "pattern": r"when i (start|begin) (studying|learning|reading)",
        "trigger_type": "workflow_start",
        "trigger_value": "deep_study",
        "label": "when studying starts",
    },
    {
        "pattern": r"during (coding|programming) sessions?",
        "trigger_type": "workflow_start",
        "trigger_value": "deep_coding",
        "label": "during coding sessions",
    },
    {
        "pattern": r"during (study|learning|reading) sessions?",
        "trigger_type": "workflow_start",
        "trigger_value": "deep_study",
        "label": "during study sessions",
    },
    # Time triggers
    {
        "pattern": r"at night|in the evening|after (9|10|11)\s*pm",
        "trigger_type": "time_of_day",
        "trigger_value": "evening",
        "label": "at night",
    },
    {
        "pattern": r"in the morning|when i wake up|early morning",
        "trigger_type": "time_of_day",
        "trigger_value": "morning",
        "label": "in the morning",
    },
    # Burnout / focus triggers
    {
        "pattern": r"after (long|extended) (focus|work|coding) sessions?",
        "trigger_type": "burnout_signal",
        "trigger_value": "moderate",
        "label": "after long focus sessions",
    },
    {
        "pattern": r"when (i.?m|i am) (tired|exhausted|burned out|overwhelmed)",
        "trigger_type": "burnout_signal",
        "trigger_value": "high",
        "label": "when burned out",
    },
    # Category triggers
    {
        "pattern": r"when (i.?m|i am) (browsing|on the web|using the browser)",
        "trigger_type": "category_active",
        "trigger_value": "browsing",
        "label": "when browsing",
    },
    {
        "pattern": r"when (i.?m|i am) (in a meeting|on a call|communicating)",
        "trigger_type": "category_active",
        "trigger_value": "communication",
        "label": "during communication",
    },
]

# ---------------------------------------------------------------------------
# Action Patterns (NLP Rules)
# ---------------------------------------------------------------------------

_ACTION_PATTERNS: list[dict] = [
    {
        "pattern": r"open (vscode|visual studio code|vscode)",
        "action_type": "open_app",
        "params": {"app": "vscode"},
        "label": "open VSCode",
    },
    {
        "pattern": r"open (notepad|notes?)",
        "action_type": "open_app",
        "params": {"app": "notepad"},
        "label": "open Notepad",
    },
    {
        "pattern": r"open (chrome|the browser|browser|firefox)",
        "action_type": "open_app",
        "params": {"app": "chrome"},
        "label": "open the browser",
    },
    {
        "pattern": r"open (calculator|calc)",
        "action_type": "open_app",
        "params": {"app": "calculator"},
        "label": "open Calculator",
    },
    {
        "pattern": r"open (terminal|cmd|command prompt|powershell)",
        "action_type": "open_app",
        "params": {"app": "terminal"},
        "label": "open the terminal",
    },
    {
        "pattern": r"(remind me|send a reminder|notify me) (to take a break|to rest|to pause)",
        "action_type": "notify",
        "params": {"message": "Time for a short break. You've earned it."},
        "label": "send a break reminder",
    },
    {
        "pattern": r"(remind me|notify me|alert me)",
        "action_type": "notify",
        "params": {"message": "Reminder from your automation."},
        "label": "send a notification",
    },
    {
        "pattern": r"(reduce|minimize|limit) (interruptions?|distractions?|notifications?)",
        "action_type": "focus_mode_on",
        "params": {},
        "label": "enable focus mode",
    },
    {
        "pattern": r"(silence|mute|disable) (notifications?|distractions?|interruptions?)",
        "action_type": "focus_mode_on",
        "params": {},
        "label": "enable focus mode (silence notifications)",
    },
    {
        "pattern": r"(enable|turn on|activate) focus (mode|time)",
        "action_type": "focus_mode_on",
        "params": {},
        "label": "enable focus mode",
    },
]

_SAFE_ACTION_TYPES = {"notify", "focus_mode_on", "focus_mode_off"}


# ---------------------------------------------------------------------------
# Natural Language Automation Engine
# ---------------------------------------------------------------------------

class NLAutomation:
    """
    Parses natural language automation requests into validated, gated recipes.

    All recipe execution routes through AutomationGovernor.
    Only single-action recipes in Phase 5 (multi-step in Phase 6).
    """

    def __init__(self) -> None:
        self._active_recipes: list[dict] = []
        self._loaded: bool = False
        print("  [NLAuto] Natural Language Automation initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, user_input: str) -> dict[str, Any]:
        """
        Parse a natural language automation request.

        Returns a dict with status and recipe data (or error).
        Does NOT execute — returns a recipe for user confirmation.
        """
        lower = user_input.lower()

        trigger = self._match_trigger(lower)
        action = self._match_action(lower)

        if not trigger:
            return {
                "status": "unrecognized",
                "error": "Could not identify when this should trigger.",
                "suggestion": (
                    "Try phrasing like: 'When I start coding, open VSCode' or "
                    "'At night, reduce interruptions'."
                ),
            }

        if not action:
            return {
                "status": "unrecognized",
                "error": "Could not identify what action to take.",
                "suggestion": (
                    "Try phrasing the action as: 'open VSCode', 'send me a reminder', "
                    "or 'reduce interruptions'."
                ),
            }

        # Safety validation
        safety = self._validate_safety(action)
        if not safety["safe"]:
            return {
                "status": "rejected",
                "error": safety["reason"],
            }

        # Build recipe
        recipe = self._build_recipe(trigger, action, user_input)
        return {
            "status": "ready",
            "recipe": recipe,
            "simulation": self._simulate(recipe),
            "message": (
                f"I can set up an automation: {trigger['label']}, {action['label']}. "
                "Should I create this?"
            ),
        }

    def create_recipe(self, trigger: dict, action: dict, description: str) -> dict:
        """
        Persist a validated recipe to SQLite.

        Returns the saved recipe dict.
        """
        now = datetime.now().isoformat(timespec="seconds")
        recipe = self._build_recipe(trigger, action, description)

        try:
            with get_connection() as conn:
                cursor = conn.execute(
                    "INSERT INTO automation_recipes "
                    "(trigger_description, action_description, trigger_type, "
                    "action_type, params_json, enabled, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 1, ?)",
                    (
                        trigger.get("label", description),
                        action.get("label", ""),
                        recipe["trigger_type"],
                        recipe["action_type"],
                        json.dumps(recipe["params"]),
                        now,
                    ),
                )
                recipe["id"] = cursor.lastrowid
        except Exception as e:
            return {"status": "error", "error": str(e)}

        self._loaded = False  # Force reload
        return {"status": "created", "recipe": recipe}

    def parse_and_create(self, user_input: str) -> dict[str, Any]:
        """Parse and immediately create a recipe (for user-confirmed requests)."""
        result = self.parse(user_input)
        if result["status"] != "ready":
            return result

        recipe = result["recipe"]
        trigger = {"label": recipe["trigger_label"], "trigger_type": recipe["trigger_type"],
                   "trigger_value": recipe["trigger_value"]}
        action = {"label": recipe["action_label"], "action_type": recipe["action_type"],
                  "params": recipe["params"]}
        return self.create_recipe(trigger, action, user_input)

    def check_triggers(
        self,
        desktop_snapshot: dict[str, Any],
        emotion: str = "neutral",
        burnout_risk: str = "none",
    ) -> list[dict]:
        """
        Check all active recipes against current state and return triggered ones.

        Triggered recipes are passed to AutomationGovernor for execution gating.
        Does NOT execute directly — returns a list for the caller to handle.
        """
        self._ensure_loaded()
        triggered = []
        category = desktop_snapshot.get("category", "other")
        workflow = desktop_snapshot.get("workflow_name")

        for recipe in self._active_recipes:
            if self._matches_trigger(recipe, workflow, category, emotion, burnout_risk):
                triggered.append(recipe)

        return triggered

    def get_active_recipes(self) -> list[dict]:
        """Return all enabled automation recipes."""
        self._ensure_loaded()
        return list(self._active_recipes)

    def toggle_recipe(self, recipe_id: int, enabled: bool) -> dict:
        """Enable or disable a recipe."""
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE automation_recipes SET enabled = ? WHERE id = ?",
                    (1 if enabled else 0, recipe_id),
                )
            self._loaded = False
            return {"status": "ok", "id": recipe_id, "enabled": enabled}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_status(self) -> dict[str, Any]:
        """Return NL automation status."""
        self._ensure_loaded()
        return {
            "active_recipes": len(self._active_recipes),
            "recipes": [
                {
                    "id": r["id"],
                    "trigger_description": r.get("trigger_description"),
                    "action_description": r.get("action_description"),
                    "enabled": bool(r.get("enabled", True)),
                    "last_triggered": r.get("last_triggered"),
                }
                for r in self._active_recipes
            ],
        }

    # ------------------------------------------------------------------
    # Internal Matching
    # ------------------------------------------------------------------

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
        """Validate that an action is safe for auto-recipe creation."""
        action_type = action.get("action_type", "")

        # Only allow actions in the registry
        try:
            from agentic_executor import _ACTION_REGISTRY
            if action_type not in _ACTION_REGISTRY:
                return {
                    "safe": False,
                    "reason": f"Action '{action_type}' is not a recognized safe action.",
                }
            risk = _ACTION_REGISTRY[action_type].get("risk", "high")
            if risk == "high":
                return {
                    "safe": False,
                    "reason": "High-risk actions cannot be automated via natural language.",
                }
        except ImportError:
            pass

        return {"safe": True}

    def _build_recipe(
        self, trigger: dict, action: dict, description: str
    ) -> dict:
        return {
            "trigger_type": trigger["trigger_type"],
            "trigger_value": trigger.get("trigger_value"),
            "trigger_label": trigger.get("label", ""),
            "action_type": action["action_type"],
            "action_label": action.get("label", ""),
            "params": action.get("params", {}),
            "description": description,
        }

    def _simulate(self, recipe: dict) -> str:
        """Return a simulation description (no actual execution)."""
        trigger_label = recipe.get("trigger_label", recipe["trigger_type"])
        action_label = recipe.get("action_label", recipe["action_type"])
        return (
            f"Simulation: {trigger_label} -> {action_label} "
            f"[will execute with AutomationGovernor approval]"
        )

    def _matches_trigger(
        self,
        recipe: dict,
        workflow: str | None,
        category: str,
        emotion: str,
        burnout_risk: str,
    ) -> bool:
        """Check if a recipe's trigger conditions are met."""
        ttype = recipe.get("trigger_type")
        tval = recipe.get("trigger_value", "")

        if ttype == "workflow_start":
            return workflow == tval
        if ttype == "category_active":
            return category == tval
        if ttype == "emotion_state":
            return emotion == tval
        if ttype == "burnout_signal":
            risk_order = {"none": 0, "low": 1, "moderate": 2, "high": 3}
            threshold = risk_order.get(tval, 2)
            current = risk_order.get(burnout_risk, 0)
            return current >= threshold
        if ttype == "time_of_day":
            from datetime import datetime
            hour = datetime.now().hour
            if tval == "morning":
                return 5 <= hour < 10
            if tval == "evening":
                return hour >= 21 or hour < 2
        return False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._load_recipes()

    def _load_recipes(self) -> None:
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, trigger_description, action_description, "
                    "trigger_type, action_type, params_json, enabled, "
                    "created_at, last_triggered FROM automation_recipes "
                    "WHERE enabled = 1"
                ).fetchall()
            self._active_recipes = []
            for row in rows:
                r = dict(row)
                try:
                    r["params"] = json.loads(r.get("params_json", "{}"))
                except Exception:
                    r["params"] = {}
                # trigger_value is inferred at match time (stored in trigger_type context)
                # For now, extract from action_description or default to None
                r["trigger_value"] = r.get("trigger_description", "")
                self._active_recipes.append(r)
            self._loaded = True
        except Exception:
            self._active_recipes = []


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

nl_automation = NLAutomation()
