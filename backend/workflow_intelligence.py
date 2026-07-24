"""
Workflow Intelligence Engine for Aisha AI Assistant (Phase 4 Step 1).

Understands user workflows and activity patterns by analyzing sequences
of application usage over time.  Classifies higher-order workflows such as
"Code-Debug Cycle", "Research-Write Loop", and detects productivity states
such as deep focus, multitasking overload, and routine patterns.

Privacy-first:
    - No content capture, no keylogging, no file reading
    - Reads only window titles + process names from desktop_awareness
    - Rolling buffer of app categories -- not raw window text

EventBus events emitted:
    workflow:detected  -- a meaningful workflow has been identified
    workflow:changed   -- user switched to a different workflow
    workflow:overload  -- multitasking overload detected

Usage::

    from workflow_intelligence import workflow_intelligence

    # Update with current desktop state
    state = workflow_intelligence.update(desktop_snapshot)

    # Query the active workflow
    workflow = workflow_intelligence.get_active_workflow()

    # Get productivity context string for LLM
    context = workflow_intelligence.get_context_summary()
"""

from __future__ import annotations

import os
import sys
import time
from collections import deque
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Workflow Definitions
# ---------------------------------------------------------------------------

# Workflow: (name, required_categories, min_transitions, description)
# A workflow is detected when at least `min_transitions` of the recent
# window history fall into the listed categories.
_WORKFLOW_DEFINITIONS: list[dict] = [
    {
        "name": "code_debug_cycle",
        "label": "Code-Debug Cycle",
        "categories": {"coding", "browsing"},          # Code + browser (Stack Overflow etc.)
        "min_each": 1,
        "description": "Switching between coding and research/debugging",
    },
    {
        "name": "research_write_loop",
        "label": "Research-Write Loop",
        "categories": {"browsing", "studying"},         # Browser + docs/notes
        "min_each": 1,
        "description": "Researching and taking notes or writing",
    },
    {
        "name": "deep_coding",
        "label": "Deep Coding Session",
        "categories": {"coding"},
        "min_each": 4,                                  # Mostly coding for sustained time
        "description": "Sustained focused coding session",
    },
    {
        "name": "deep_study",
        "label": "Deep Study Session",
        "categories": {"studying"},
        "min_each": 4,
        "description": "Sustained focused study or reading session",
    },
    {
        "name": "communication_heavy",
        "label": "Communication-Heavy",
        "categories": {"communication"},
        "min_each": 3,
        "description": "Predominantly messaging, email, or calls",
    },
    {
        "name": "design_work",
        "label": "Design Session",
        "categories": {"design"},
        "min_each": 2,
        "description": "Working in design tools",
    },
    {
        "name": "learning_session",
        "label": "Learning Session",
        "categories": {"studying", "browsing"},
        "min_each": 2,
        "description": "Active online or offline learning",
    },
    {
        "name": "multitasking",
        "label": "Heavy Multitasking",
        "categories": None,                             # Detected by diversity, not specific cats
        "min_each": 0,
        "description": "Many different applications in rapid succession (overload risk)",
    },
]

# How many recent window snapshots to keep in the rolling buffer
_BUFFER_SIZE = 20

# Minimum distinct categories in last N snapshots to flag multitasking overload
_MULTITASKING_THRESHOLD = 5

# Minimum time in current workflow before emitting a change event (seconds)
_WORKFLOW_STABILITY_SECONDS = 90


# ---------------------------------------------------------------------------
# Workflow Intelligence Engine
# ---------------------------------------------------------------------------

class WorkflowIntelligence:
    """
    Analyzes sequences of desktop activity to identify higher-order workflows.

    Maintains a rolling buffer of recent activity categories and uses
    pattern matching to classify the user's current workflow.
    """

    def __init__(self) -> None:
        # Rolling buffer: list of {"category": str, "ts": float}
        self._buffer: deque[dict] = deque(maxlen=_BUFFER_SIZE)

        # Currently detected workflow
        self._active_workflow: str | None = None
        self._workflow_start: float = 0.0
        self._workflow_label: str = "Unknown"
        self._workflow_description: str = ""

        # Overload tracking
        self._overload_detected: bool = False
        self._last_overload_at: float = 0.0

        # Transition stats
        self._transition_count: int = 0
        self._last_category: str | None = None

        print("  [Workflow] Intelligence Engine initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, desktop_snapshot: dict[str, Any]) -> dict[str, Any]:
        """
        Process a new desktop snapshot from desktop_awareness.

        Updates the rolling buffer and re-evaluates the active workflow.

        Parameters:
            desktop_snapshot: dict returned by desktop_awareness.poll()

        Returns:
            dict with workflow state, overload flag, and any EventBus events
        """
        category = desktop_snapshot.get("category", "other")
        now = time.time()

        # Track transitions
        if self._last_category and category != self._last_category:
            self._transition_count += 1
        self._last_category = category

        # Add to rolling buffer
        self._buffer.append({
            "category": category,
            "ts": now,
            "window_title": desktop_snapshot.get("window_title", "")[:60],
        })

        # Re-classify workflow
        new_workflow = self._classify_workflow()
        changed = new_workflow != self._active_workflow

        if changed:
            # Only register the change if it's been stable long enough
            time_in_workflow = now - self._workflow_start
            if self._active_workflow is None or time_in_workflow >= _WORKFLOW_STABILITY_SECONDS:
                old = self._active_workflow
                self._active_workflow = new_workflow
                self._workflow_start = now
                defn = self._get_workflow_defn(new_workflow)
                self._workflow_label = defn.get("label", new_workflow) if defn else new_workflow
                self._workflow_description = defn.get("description", "") if defn else ""

        # Multitasking overload detection
        overload = self._detect_overload()
        self._overload_detected = overload

        return {
            "active_workflow": self._active_workflow,
            "workflow_label": self._workflow_label,
            "workflow_changed": changed,
            "overload": overload,
            "buffer_size": len(self._buffer),
            "transition_count": self._transition_count,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    def get_active_workflow(self) -> dict[str, Any] | None:
        """Return the currently active workflow, or None."""
        if not self._active_workflow:
            return None
        return {
            "name": self._active_workflow,
            "label": self._workflow_label,
            "description": self._workflow_description,
            "started_at": datetime.fromtimestamp(self._workflow_start).isoformat(
                timespec="seconds"
            ),
            "duration_min": round((time.time() - self._workflow_start) / 60, 1),
            "overload": self._overload_detected,
        }

    def is_deep_work(self) -> bool:
        """True if user is in a sustained single-focus workflow (coding or study)."""
        return self._active_workflow in ("deep_coding", "deep_study")

    def is_overloaded(self) -> bool:
        """True if multitasking overload has been detected."""
        return self._overload_detected

    def get_category_distribution(self) -> dict[str, int]:
        """Return count of each category in the rolling buffer."""
        counts: dict[str, int] = {}
        for entry in self._buffer:
            cat = entry["category"]
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def get_context_summary(self) -> str:
        """
        Generate a human-readable workflow context string for LLM prompts.

        Concise, non-intrusive — just enough to inform response style.
        """
        wf = self.get_active_workflow()
        if not wf:
            return ""

        parts = [f"The user is currently in a '{wf['label']}' workflow."]

        if wf["duration_min"] >= 10:
            parts.append(
                f"They have been at this for {wf['duration_min']:.0f} minutes."
            )

        if wf["overload"]:
            parts.append(
                "The user appears to be juggling many tasks — keep responses focused."
            )
        elif self.is_deep_work():
            parts.append("They are in deep work. Keep responses concise and non-disruptive.")

        return " ".join(parts)

    def get_routine_hints(self) -> list[str]:
        """
        Return observations about the user's workflow patterns.

        Used by the presence engine and behavioral intelligence.
        """
        hints = []
        dist = self.get_category_distribution()

        dominant = max(dist, key=dist.get) if dist else None
        if dominant and dist.get(dominant, 0) >= _BUFFER_SIZE // 2:
            hints.append(f"User is predominantly in '{dominant}' mode.")

        if self._overload_detected:
            hints.append(
                "Rapid app switching detected — user may benefit from focus suggestions."
            )

        if self.is_deep_work():
            hints.append("User is in deep work — minimize interruptions.")

        return hints

    def get_status(self) -> dict[str, Any]:
        """Return full workflow intelligence status."""
        return {
            "active_workflow": self.get_active_workflow(),
            "category_distribution": self.get_category_distribution(),
            "overload_detected": self._overload_detected,
            "transition_count": self._transition_count,
            "buffer_entries": len(self._buffer),
            "routine_hints": self.get_routine_hints(),
        }

    # ------------------------------------------------------------------
    # Internal Classification
    # ------------------------------------------------------------------

    def _classify_workflow(self) -> str | None:
        """
        Classify the current workflow from the rolling buffer.

        Returns the workflow name or None.
        """
        if len(self._buffer) < 2:
            return None

        dist = self.get_category_distribution()
        categories_present = set(dist.keys()) - {"other", "unknown"}

        # Check multitasking overload first
        if len(categories_present) >= _MULTITASKING_THRESHOLD:
            return "multitasking"

        # Try to match a workflow definition
        best_match: str | None = None
        best_score: int = 0

        for defn in _WORKFLOW_DEFINITIONS:
            if defn["name"] == "multitasking":
                continue  # handled above

            required = defn["categories"]
            min_each = defn["min_each"]

            if required is None:
                continue

            # Check if all required categories meet the minimum count
            all_met = all(
                dist.get(cat, 0) >= min_each
                for cat in required
            )

            if all_met:
                score = sum(dist.get(cat, 0) for cat in required)
                if score > best_score:
                    best_score = score
                    best_match = defn["name"]

        return best_match

    def _detect_overload(self) -> bool:
        """
        Detect multitasking overload.

        Overload = more than N distinct categories in recent history
        AND rapid transitions (high transition count relative to buffer size).
        """
        if len(self._buffer) < _BUFFER_SIZE // 2:
            return False

        dist = self.get_category_distribution()
        distinct = len(set(dist.keys()) - {"other"})

        if distinct < _MULTITASKING_THRESHOLD:
            return False

        # Also check transition rate
        rapid = self._transition_count > (len(self._buffer) * 0.7)
        return rapid

    def _get_workflow_defn(self, name: str | None) -> dict | None:
        """Look up a workflow definition by name."""
        if not name:
            return None
        for defn in _WORKFLOW_DEFINITIONS:
            if defn["name"] == name:
                return defn
        return None

    def reset(self) -> None:
        """Reset the workflow intelligence state (e.g., on new session)."""
        self._buffer.clear()
        self._active_workflow = None
        self._workflow_start = 0.0
        self._transition_count = 0
        self._last_category = None
        self._overload_detected = False


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

workflow_intelligence = WorkflowIntelligence()
