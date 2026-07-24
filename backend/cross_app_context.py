"""
Cross-Application Context Layer for Aisha AI Assistant (Phase 4 Step 2).

Reasons across active applications to build a unified workspace understanding.
Instead of treating each app as a silo, this engine identifies contextual
relationships between apps and infers shared task context.

Examples of detected contexts:
    - "Code + Browser"    → coding research session
    - "PDF + Notion"      → study synthesis session
    - "Browser + Discord" → distracted communication mode
    - "IDE + Terminal"    → active development

Privacy-first:
    - Uses only app category data from WorkflowIntelligence + DesktopAwareness
    - No window content or file path inspection

EventBus events:
    context:workspace_changed  -- workspace context has shifted meaningfully

Usage::

    from cross_app_context import cross_app_context

    ctx = cross_app_context.get_unified_context(desktop_snapshot)
    summary = cross_app_context.get_context_string()
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Workspace Context Rules
# ---------------------------------------------------------------------------

# Maps a frozenset of active categories → (context_name, label, description)
_CONTEXT_RULES: list[dict] = [
    {
        "name": "coding_research",
        "label": "Coding + Research",
        "requires": {"coding", "browsing"},
        "description": "Looking up documentation or Stack Overflow while coding.",
        "suggestions": [
            "Shall I search for anything specific related to your code?",
            "Would it help to summarize what you found in the browser?",
        ],
    },
    {
        "name": "study_synthesis",
        "label": "Study + Note-Taking",
        "requires": {"studying", "browsing"},
        "description": "Reading and taking notes simultaneously.",
        "suggestions": [
            "Would you like me to help organize your notes?",
            "Want a quick summary of what you've been reading?",
        ],
    },
    {
        "name": "active_development",
        "label": "Active Development",
        "requires": {"coding"},
        "description": "Focused development session.",
        "suggestions": [
            "You're in a coding session — let me know if you need any help.",
        ],
    },
    {
        "name": "communication_distraction",
        "label": "Communication + Work",
        "requires": {"communication", "coding"},
        "description": "Mixing deep work with messaging — potential distraction.",
        "suggestions": [
            "You're mixing coding with communication. Consider a focus block?",
        ],
    },
    {
        "name": "design_research",
        "label": "Design + Research",
        "requires": {"design", "browsing"},
        "description": "Looking up design references while working.",
        "suggestions": [
            "Working on a design? I can help find references or describe ideas.",
        ],
    },
    {
        "name": "deep_study",
        "label": "Deep Study",
        "requires": {"studying"},
        "description": "Focused studying or reading session.",
        "suggestions": [
            "Deep in study mode — I'll keep it brief.",
        ],
    },
    {
        "name": "media_break",
        "label": "Media / Break",
        "requires": {"media"},
        "description": "User appears to be on a break or consuming media.",
        "suggestions": [
            "Looks like a break — enjoy! Let me know when you're back.",
        ],
    },
]


# ---------------------------------------------------------------------------
# Cross-Application Context Engine
# ---------------------------------------------------------------------------

class CrossAppContext:
    """
    Builds unified workspace context from multi-application state.

    Analyzes the combination of active app categories to infer shared
    task context and provide coherent, context-aware assistance.
    """

    def __init__(self) -> None:
        self._current_context_name: str | None = None
        self._context_label: str = "General"
        self._context_description: str = ""
        self._context_suggestions: list[str] = []
        self._context_since: float = 0.0
        self._active_categories: set[str] = set()

        print("  [CrossApp] Context Layer initialized")

    def update(self, desktop_snapshot: dict[str, Any]) -> dict[str, Any]:
        """
        Update the workspace context from a desktop snapshot.

        Also queries the workflow intelligence buffer for category distribution.
        Returns unified workspace context dict.
        """
        now = time.time()

        # Get current category from snapshot
        current_cat = desktop_snapshot.get("category", "other")
        workflow = desktop_snapshot.get("workflow")

        # Build a richer picture from workflow intelligence
        try:
            from workflow_intelligence import workflow_intelligence
            dist = workflow_intelligence.get_category_distribution()
            active_cats = {
                cat for cat, count in dist.items()
                if count >= 2 and cat not in ("other", "unknown")
            }
        except Exception:
            active_cats = {current_cat} if current_cat not in ("other", "unknown") else set()

        # Always include the current category
        if current_cat not in ("other", "unknown"):
            active_cats.add(current_cat)

        self._active_categories = active_cats

        # Classify context
        new_context = self._classify_context(active_cats)
        changed = new_context != self._current_context_name

        if changed:
            self._current_context_name = new_context
            defn = self._get_defn(new_context)
            if defn:
                self._context_label = defn["label"]
                self._context_description = defn["description"]
                self._context_suggestions = defn.get("suggestions", [])
            else:
                self._context_label = "General"
                self._context_description = ""
                self._context_suggestions = []
            self._context_since = now

        return {
            "context_name": self._current_context_name,
            "context_label": self._context_label,
            "context_description": self._context_description,
            "active_categories": sorted(self._active_categories),
            "context_changed": changed,
            "context_duration_min": round((now - self._context_since) / 60, 1),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    def get_unified_context(self, desktop_snapshot: dict[str, Any]) -> dict[str, Any]:
        """Update and return unified workspace context."""
        return self.update(desktop_snapshot)

    def get_context_string(self) -> str:
        """
        Return a concise human-readable workspace context string.

        Suitable for inclusion in LLM system prompts.
        """
        if not self._current_context_name or not self._context_description:
            return ""

        parts = [f"Workspace context: {self._context_label}."]
        if self._context_description:
            parts.append(self._context_description)
        return " ".join(parts)

    def get_suggestion(self) -> str | None:
        """
        Return a contextual suggestion if appropriate.

        Returns None if no suggestions or context hasn't been stable long enough.
        """
        # Only suggest after some stability
        if time.time() - self._context_since < 120:  # 2 minutes stability
            return None
        if not self._context_suggestions:
            return None
        import random
        return random.choice(self._context_suggestions)

    def get_current_context(self) -> dict[str, Any]:
        """Return current workspace context."""
        return {
            "name": self._current_context_name,
            "label": self._context_label,
            "description": self._context_description,
            "active_categories": sorted(self._active_categories),
            "duration_min": round((time.time() - self._context_since) / 60, 1),
        }

    def get_status(self) -> dict[str, Any]:
        """Return full cross-app context status."""
        return {
            "current_context": self.get_current_context(),
            "context_string": self.get_context_string(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _classify_context(self, active_categories: set[str]) -> str | None:
        """Match active categories to a context definition."""
        best: str | None = None
        best_overlap: int = 0

        for defn in _CONTEXT_RULES:
            required = defn["requires"]
            overlap = len(required & active_categories)

            # Must satisfy ALL required categories
            if overlap == len(required) and overlap > best_overlap:
                best_overlap = overlap
                best = defn["name"]

        return best

    def _get_defn(self, name: str | None) -> dict | None:
        """Look up a context definition by name."""
        if not name:
            return None
        for defn in _CONTEXT_RULES:
            if defn["name"] == name:
                return defn
        return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

cross_app_context = CrossAppContext()
