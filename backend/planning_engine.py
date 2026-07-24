"""
Long-Horizon Planning Engine for AISHA AI Assistant (Phase 8 Step 4).

Implements multi-stage strategic roadmap generation, delay scenario simulations,
uncertainty-aware planning, and orchestrator-driven plan revision persistence.
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
from cognitive_orchestrator import orchestrator

_log = logging.getLogger("aisha.planning_engine")


class StrategicPlanningEngine:
    """
    Engine for modeling long-horizon roadmaps and simulating timeline impacts.
    """

    def create_plan(self, goal: str, stages: list[dict[str, Any]], context: str = "") -> dict[str, Any]:
        """
        Create a new multi-stage plan and save it via the cognitive orchestrator.
        Each stage contains steps, dependencies, and duration_days.
        """
        now = datetime.now().isoformat(timespec="seconds")
        plan_data = {
            "goal": goal,
            "steps_json": json.dumps(stages),
            "status": "active",
            "progress": 0.0,
            "adaptations": 0,
            "context": context,
            "created_at": now,
            "updated_at": now
        }

        # Route through orchestrator validation
        intent = {
            "action": "store",
            "table": "cognitive_plans",
            "data": plan_data
        }
        
        orchestrator._commit_intents([intent])

        # Retrieve the plan from DB
        with get_connection() as conn:
            row = conn.execute("SELECT id FROM cognitive_plans WHERE goal = ? ORDER BY id DESC LIMIT 1", (goal,)).fetchone()
            plan_id = row["id"] if row else None

        return {
            "status": "success",
            "plan_id": plan_id,
            "goal": goal,
            "stages": stages
        }

    def simulate_delay(self, plan_id: int, stage_idx: int, delay_days: int) -> dict[str, Any]:
        """
        Simulate the impact of a delay in a specific stage on subsequent dependent stages
        and the overall goal target date.
        """
        with get_connection() as conn:
            plan = conn.execute("SELECT * FROM cognitive_plans WHERE id = ?", (plan_id,)).fetchone()
            if not plan:
                return {"error": "Plan not found"}

        plan = dict(plan)
        stages = json.loads(plan["steps_json"])

        if stage_idx < 0 or stage_idx >= len(stages):
            return {"error": "Invalid stage index"}

        # Simulate timeline slips
        slips = {}
        stage_name = stages[stage_idx].get("name", f"Stage {stage_idx}")
        slips[stage_name] = delay_days

        # Forward propagate delay based on dependencies
        for i in range(stage_idx + 1, len(stages)):
            current = stages[i]
            deps = current.get("dependencies", [])
            
            # If current stage depends on any preceding delayed stages, it slips
            affected = False
            for dep in deps:
                if dep in slips:
                    affected = True
            
            if affected:
                # Stage slips by the maximum delay of its dependencies
                dep_delays = [slips[d] for d in deps if d in slips]
                current_slip = max(dep_delays)
                slips[current.get("name", f"Stage {i}")] = current_slip

        total_goal_slip = max(slips.values()) if slips else 0

        return {
            "plan_id": plan_id,
            "delayed_stage": stage_name,
            "delay_days": delay_days,
            "stage_slips": slips,
            "total_project_delay_days": total_goal_slip,
            "reasoning": f"A delay of {delay_days} days in '{stage_name}' propagates to dependent stages: {list(slips.keys())}."
        }

    def revise_plan(self, plan_id: int, stage_idx: int, progress: float, status: str = "active") -> dict[str, Any]:
        """
        Revise a plan's stage progress or status.
        Registers plan adaptations and updates via the orchestrator.
        """
        with get_connection() as conn:
            plan = conn.execute("SELECT * FROM cognitive_plans WHERE id = ?", (plan_id,)).fetchone()
            if not plan:
                return {"error": "Plan not found"}

        plan = dict(plan)
        stages = json.loads(plan["steps_json"])

        if stage_idx < 0 or stage_idx >= len(stages):
            return {"error": "Invalid stage index"}

        # Update stage info
        stages[stage_idx]["progress"] = progress
        stages[stage_idx]["status"] = status

        # Calculate overall plan progress
        completed_stages = sum(1 for s in stages if s.get("status") == "completed" or s.get("progress", 0.0) >= 1.0)
        overall_progress = completed_stages / len(stages)

        now = datetime.now().isoformat(timespec="seconds")
        updated_data = {
            "id": plan_id,
            "steps_json": json.dumps(stages),
            "progress": overall_progress,
            "adaptations": plan.get("adaptations", 0) + 1,
            "status": "completed" if overall_progress >= 1.0 else plan.get("status", "active"),
            "updated_at": now
        }

        # Commit via orchestrator
        intent = {
            "action": "promote",
            "table": "cognitive_plans",
            "data": updated_data
        }
        orchestrator._commit_intents([intent])

        return {
            "status": "success",
            "plan_id": plan_id,
            "overall_progress": overall_progress,
            "adaptations": updated_data["adaptations"]
        }


# Singleton export
planning_engine = StrategicPlanningEngine()
