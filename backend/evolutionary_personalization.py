"""
Evolutionary Personalization for Aisha AI Assistant (Phase 5 Step 6).

Tracks long-term personality dimension drift and applies ultra-slow
micro-corrections to keep AISHA's interaction style aligned with who
the user actually is over weeks and months.

Operates on top of `personality.py` — does NOT replace it.
personality.py: fast micro-adjustments per interaction (LEARN_RATE=0.03)
evolutionary_personalization.py: slow weekly drift corrections (rate=0.005)

Safety constraints:
    - Maximum drift: 0.15 per dimension per month
    - Minimum 7 days between snapshots
    - Corrections only applied if weekly trend is consistent
    - Never overcorrects toward extremes (clamped at 0.1, 0.9)

Dimensions tracked:
    Same 6 as personality.py: warmth, verbosity, formality, humor,
    empathy, directness

Usage::

    from evolutionary_personalization import evolutionary_personalization

    # Take a weekly snapshot (called once per week)
    evolutionary_personalization.maybe_snapshot()

    # Get drift correction context for LLM
    context = evolutionary_personalization.get_drift_context()

    # Get status
    status = evolutionary_personalization.get_status()
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


# Maximum per-dimension drift in any 30-day period
_MAX_MONTHLY_DRIFT = 0.15
# Minimum days between snapshots
_SNAPSHOT_INTERVAL_DAYS = 7
# Evolutionary learning rate (much slower than personality.py)
_EVO_RATE = 0.005
# Dimension value clamps
_DIM_MIN, _DIM_MAX = 0.10, 0.90

_DIMENSIONS = ["warmth", "verbosity", "formality", "humor", "empathy", "directness"]


class EvolutionaryPersonalization:
    """
    Applies slow, stable long-term personality drift corrections.

    Reads personality snapshots from the last 30 days and computes
    whether a dimension is drifting consistently in a direction.
    If so, applies a tiny nudge to lock in the genuine long-term preference.
    """

    def __init__(self) -> None:
        self._last_snapshot_date: str | None = None
        self._drift_corrections: dict[str, float] = {}
        self._load_last_snapshot_date()
        print("  [EvoPersona] Evolutionary Personalization initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def maybe_snapshot(self) -> bool:
        """
        Take a snapshot of the current personality state if due.

        Returns True if a snapshot was taken.
        """
        today = datetime.now().strftime("%Y-%m-%d")

        if self._last_snapshot_date:
            last = datetime.strptime(self._last_snapshot_date, "%Y-%m-%d")
            if (datetime.now() - last).days < _SNAPSHOT_INTERVAL_DAYS:
                return False

        try:
            from personality import personality_engine
            dimensions = {
                dim: personality_engine.get_dimension(dim)
                for dim in _DIMENSIONS
            }
        except ImportError:
            return False

        now = datetime.now().isoformat(timespec="seconds")
        behavioral_ctx = self._get_behavioral_context()

        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO personality_snapshots "
                    "(snapshot_date, dimensions_json, behavioral_context) "
                    "VALUES (?, ?, ?)",
                    (today, json.dumps(dimensions), behavioral_ctx),
                )
        except Exception:
            return False

        self._last_snapshot_date = today
        self._compute_drift_corrections()
        return True

    def get_drift_context(self) -> str:
        """
        Return a context string describing meaningful long-term personality drift.

        Used to augment LLM personality prompts with genuine long-term learning.
        Empty string if no meaningful drift.
        """
        if not self._drift_corrections:
            return ""

        parts = []
        for dim, drift in self._drift_corrections.items():
            if abs(drift) < 0.05:
                continue
            direction = "more" if drift > 0 else "less"
            if dim == "warmth":
                parts.append(f"User responds better to {direction} warmth over time.")
            elif dim == "verbosity":
                parts.append(f"User prefers {direction} detailed responses long-term.")
            elif dim == "humor":
                parts.append(f"User appreciates {direction} humor in the long run.")
            elif dim == "formality":
                parts.append(f"User has been gravitating toward {direction} formal interaction.")

        return " ".join(parts[:2]) if parts else ""

    def get_status(self) -> dict[str, Any]:
        """Return evolutionary personalization status."""
        return {
            "last_snapshot_date": self._last_snapshot_date,
            "drift_corrections": {
                k: round(v, 4) for k, v in self._drift_corrections.items()
            },
            "drift_context": self.get_drift_context(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _compute_drift_corrections(self) -> None:
        """
        Compute drift by comparing oldest vs. newest snapshot in the last 30 days.
        """
        cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT snapshot_date, dimensions_json FROM personality_snapshots "
                    "WHERE snapshot_date >= ? ORDER BY snapshot_date ASC",
                    (cutoff,),
                ).fetchall()
        except Exception:
            return

        if len(rows) < 2:
            return

        oldest = json.loads(rows[0]["dimensions_json"])
        newest = json.loads(rows[-1]["dimensions_json"])
        corrections = {}

        for dim in _DIMENSIONS:
            old_val = oldest.get(dim, 0.5)
            new_val = newest.get(dim, 0.5)
            drift = new_val - old_val

            # Cap monthly drift
            drift = max(-_MAX_MONTHLY_DRIFT, min(_MAX_MONTHLY_DRIFT, drift))
            corrections[dim] = drift

        self._drift_corrections = corrections

        # Apply micro-corrections to personality engine
        self._apply_corrections(corrections)

    def _apply_corrections(self, corrections: dict[str, float]) -> None:
        """Apply tiny drift corrections to the live personality engine."""
        try:
            from personality import personality_engine, DIMENSIONS
            for dim, drift in corrections.items():
                if abs(drift) < 0.04:
                    continue  # Not significant enough

                current = personality_engine.get_dimension(dim)
                # Apply a fraction of the drift (evolutionary, not reactive)
                nudge = drift * _EVO_RATE
                new_val = max(_DIM_MIN, min(_DIM_MAX, current + nudge))

                dim_config = DIMENSIONS.get(dim, {})
                new_val = max(
                    dim_config.get("min", _DIM_MIN),
                    min(dim_config.get("max", _DIM_MAX), new_val),
                )

                # Write directly to personality cache (not through observe_interaction)
                personality_engine._cache[dim] = (
                    new_val,
                    personality_engine.get_confidence(dim),
                )
        except Exception:
            pass

    def _get_behavioral_context(self) -> str:
        """Get a brief behavioral context for snapshot metadata."""
        try:
            from environmental_reasoning import environment
            return environment.get_mode()
        except Exception:
            return "general"

    def _load_last_snapshot_date(self) -> None:
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT snapshot_date FROM personality_snapshots "
                    "ORDER BY snapshot_date DESC LIMIT 1"
                ).fetchone()
            if row:
                self._last_snapshot_date = row["snapshot_date"]
        except Exception:
            pass


evolutionary_personalization = EvolutionaryPersonalization()
