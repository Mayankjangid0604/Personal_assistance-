"""
Ecosystem Memory Layer for Aisha AI Assistant (Phase 5 Step 5).

Maintains long-term continuity across workflows, sessions, and life events
by building a structured ecosystem timeline. Provides "continuity bridging"
— allowing AISHA to remember what the user was working on last week and
surface that context naturally.

Design principles:
    - Timeline is event-based, not session-based
    - Events are behavioral summaries, never raw content
    - Continuity strings are <=2 sentences, non-intrusive
    - Timeline is local-only (never synced)

Timeline event types:
    workflow_milestone   -- a sustained workflow session worth noting
    plan_progress        -- measurable progress on a cognitive plan
    routine_established  -- a new routine pattern detected
    insight_generated    -- a reflective insight was shown
    behavioral_shift     -- a notable behavioral model trend change

Usage::

    from ecosystem_memory import ecosystem_memory

    # Record an event (called by conversation_engine)
    ecosystem_memory.record_event("workflow_milestone", "Completed a deep coding session")

    # Get a continuity bridge string for LLM context
    bridge = ecosystem_memory.get_continuity_summary()

    # Get recent timeline for inspection
    timeline = ecosystem_memory.get_recent_timeline(days=7)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection


class EcosystemMemory:
    """
    Long-term continuity and ecosystem timeline manager.

    Records meaningful behavioral events and distills them into
    concise continuity context for conversation turns.
    """

    # Max events to hold in memory cache
    _CACHE_SIZE = 50
    # Max timeline days to retrieve for context
    _CONTEXT_DAYS = 7

    def __init__(self) -> None:
        self._event_cache: list[dict] = []
        self._cache_loaded: bool = False
        print("  [Ecosystem] Memory Layer initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_event(
        self,
        event_type: str,
        summary: str,
        context: dict | None = None,
    ) -> None:
        """Record a timeline event."""
        now = datetime.now().isoformat(timespec="seconds")
        ctx_json = json.dumps(context or {})
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO ecosystem_timeline "
                    "(event_type, summary, context_json, occurred_at) "
                    "VALUES (?, ?, ?, ?)",
                    (event_type, summary, ctx_json, now),
                )
        except Exception:
            pass
        # Invalidate cache
        self._cache_loaded = False

    def get_continuity_summary(self) -> str:
        """
        Return a 1–2 sentence continuity bridge for LLM context.

        Only returns content when there's something meaningful to surface.
        """
        events = self._load_recent_events(days=self._CONTEXT_DAYS)
        if not events:
            return ""

        # Find the most significant recent events
        milestones = [e for e in events if e["event_type"] == "workflow_milestone"]
        progress = [e for e in events if e["event_type"] == "plan_progress"]
        routines = [e for e in events if e["event_type"] == "routine_established"]

        parts = []

        if milestones:
            latest = milestones[0]
            # Calculate days ago
            occurred = datetime.fromisoformat(latest["occurred_at"])
            days_ago = (datetime.now() - occurred).days
            if days_ago == 0:
                parts.append(f"Earlier today: {latest['summary']}.")
            elif days_ago == 1:
                parts.append(f"Yesterday: {latest['summary']}.")
            elif days_ago <= 7:
                parts.append(f"{days_ago} days ago: {latest['summary']}.")

        if progress and len(parts) < 2:
            parts.append(progress[0]["summary"] + ".")

        if routines and not parts:
            parts.append(routines[0]["summary"] + ".")

        if not parts:
            return ""

        return " ".join(parts[:2])

    def get_recent_timeline(self, days: int = 7) -> list[dict]:
        """Return recent timeline events."""
        return self._load_recent_events(days=days)

    def get_status(self) -> dict[str, Any]:
        """Return ecosystem memory status."""
        total = 0
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM ecosystem_timeline"
                ).fetchone()
                total = row["cnt"] if row else 0
        except Exception:
            pass
        recent = self._load_recent_events(days=7)
        return {
            "total_events": total,
            "recent_events": len(recent),
            "continuity_summary": self.get_continuity_summary(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_recent_events(self, days: int = 7) -> list[dict]:
        cutoff = (
            datetime.now() - timedelta(days=days)
        ).isoformat(timespec="seconds")
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT event_type, summary, context_json, occurred_at "
                    "FROM ecosystem_timeline "
                    "WHERE occurred_at >= ? ORDER BY occurred_at DESC LIMIT 20",
                    (cutoff,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []


ecosystem_memory = EcosystemMemory()
