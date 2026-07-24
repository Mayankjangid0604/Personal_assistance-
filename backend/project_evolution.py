"""
Autonomous Project Evolution for Aisha AI Assistant (Phase 8 Step 3).

Provides predictive forecasting for milestones, blocker anticipation,
trajectory updates, and session transition continuity synthesis.
"""

from __future__ import annotations

import json
import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection

_log = logging.getLogger("aisha.project_evolution")


class ProjectEvolutionEngine:
    """
    Predictive project tracking engine.
    Analyzes project speed, forecasts completion dates, and predicts slips.
    """

    def forecast_milestones(self, project_id: int) -> dict[str, Any]:
        """
        Forecast completion dates for milestones of a project.
        Calculates velocity based on elapsed time and progress.
        """
        with get_connection() as conn:
            project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not project:
                return {"error": "Project not found"}
            
            milestones = conn.execute(
                "SELECT * FROM project_milestones WHERE project_id = ? ORDER BY order_idx ASC",
                (project_id,)
            ).fetchall()

        project = dict(project)
        ms_list = [dict(m) for m in milestones]

        # Calculate project velocity (progress per day)
        created_dt = datetime.fromisoformat(project["created_at"].split("T")[0])
        days_elapsed = (datetime.now() - created_dt).days
        days_elapsed = max(1, days_elapsed)
        
        progress = project.get("progress", 0.0)
        velocity = progress / days_elapsed
        if velocity <= 0.0:
            velocity = 0.02  # Default baseline: 2% progress per day

        forecasts = []
        cumulative_days = 0

        for ms in ms_list:
            if ms["status"] == "completed":
                est_date = ms.get("completed_at") or datetime.now().isoformat()
            else:
                # Estimate remaining days for this milestone
                remaining_progress = 1.0 - ms.get("progress", 0.0)
                ms_velocity = velocity * 1.2 # assume milestone is faster than full project
                ms_velocity = max(0.01, ms_velocity)
                
                est_days = remaining_progress / ms_velocity
                # Adjust for blockers
                blockers = json.loads(project.get("blockers_json", "[]"))
                if blockers or ms["status"] == "blocked":
                    est_days += 7  # Add 7 days slip per blocker
                
                cumulative_days += est_days
                est_dt = datetime.now() + timedelta(days=cumulative_days)
                est_date = est_dt.isoformat(timespec="seconds")

            forecasts.append({
                "milestone_id": ms["id"],
                "title": ms["title"],
                "status": ms["status"],
                "progress": ms["progress"],
                "forecasted_completion": est_date
            })

        # Update trajectory dynamically
        self._update_trajectory(project_id, progress, velocity, forecasts)

        return {
            "project_id": project_id,
            "title": project["title"],
            "progress": progress,
            "velocity_per_day": round(velocity, 4),
            "forecasts": forecasts
        }

    def _update_trajectory(self, project_id: int, progress: float, velocity: float, forecasts: list[dict]) -> None:
        """Dynamically update project trajectory status based on velocity/slips."""
        trajectory = "on_track"
        if velocity < 0.005:
            trajectory = "stalling"
        elif velocity > 0.05:
            trajectory = "accelerating"

        # Check if any non-completed milestone is forecasted far out
        has_slips = False
        for f in forecasts:
            if f["status"] != "completed":
                f_dt = datetime.fromisoformat(f["forecasted_completion"].split("T")[0])
                if (f_dt - datetime.now()).days > 60:
                    has_slips = True

        if has_slips:
            trajectory = "stalling"

        # If explicit blockers exist
        with get_connection() as conn:
            proj = conn.execute("SELECT blockers_json FROM projects WHERE id = ?", (project_id,)).fetchone()
            if proj:
                blockers = json.loads(proj["blockers_json"])
                if blockers:
                    trajectory = "blocked"

        now = datetime.now().isoformat(timespec="seconds")
        with get_connection() as conn:
            conn.execute(
                "UPDATE projects SET trajectory = ?, updated_at = ? WHERE id = ?",
                (trajectory, now, project_id)
            )

    def synthesize_session_continuity(self) -> dict[str, Any]:
        """Prepare active project summary context for cross-device handover continuity."""
        with get_connection() as conn:
            stalling_or_blocked = conn.execute(
                "SELECT id, title, trajectory, progress FROM projects "
                "WHERE status = 'active' AND trajectory IN ('stalling', 'blocked', 'on_track') "
                "ORDER BY updated_at DESC LIMIT 3"
            ).fetchall()

        summary_parts = []
        for p in stalling_or_blocked:
            summary_parts.append(
                f"Project '{p['title']}' is currently {p['trajectory']} at {int(p['progress'] * 100)}% progress."
            )

        return {
            "handover_context": "\n".join(summary_parts) if summary_parts else "No active project context for handover.",
            "timestamp": datetime.now().isoformat(timespec="seconds")
        }


# Singleton export
project_evolution = ProjectEvolutionEngine()
