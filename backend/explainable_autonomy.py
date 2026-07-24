"""
Explainable Autonomy System for AISHA AI Assistant (Phase 8 Step 7).

Provides detailed natural language explanations of autonomous decisions,
action attribution summaries, and confidence trace calculations.
"""

from __future__ import annotations

import json
import os
import sys
import logging
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection

_log = logging.getLogger("aisha.explainable_autonomy")


class ExplainabilityEngine:
    """
    Translates database audit logs and agent confidence metrics into explainable summaries.
    """

    def explain_action(self, action_id: str) -> dict[str, Any]:
        """
        Provide a complete natural language explanation for why a specific action occurred.
        Cites requesting agent, evidence, confidence, risk levels, and reversibility.
        """
        with get_connection() as conn:
            audit = conn.execute("SELECT * FROM autonomy_audit_log WHERE action_id = ?", (action_id,)).fetchone()
            rollback = conn.execute("SELECT * FROM rollback_registry WHERE action_id = ?", (action_id,)).fetchone()

        if not audit:
            return {"error": f"No audit records found for action ID '{action_id}'"}

        audit = dict(audit)
        rollback = dict(rollback) if rollback else None

        # Build natural language summary
        action_name = audit["action"]
        attribution = audit["attribution"]
        confidence = audit["confidence"]
        risk = audit["risk_level"]
        status = audit["status"]
        reasoning = audit["reasoning"]

        explanation = (
            f"Action '{action_name}' was initiated with '{attribution}' attribution. "
            f"The system calculated a confidence score of {int(confidence * 100)}% (low risk: '{risk}') "
            f"and the action current status is '{status}'. "
            f"Reasoning trace: '{reasoning}'."
        )

        reversibility = "Action is not programmatically reversible; it requires manual user adjustments."
        if rollback:
            if rollback["status"] == "active":
                reversibility = f"Action is fully reversible. Rollback description: '{rollback['description']}'."
            elif rollback["status"] == "rolled_back":
                reversibility = "Action has already been successfully rolled back."

        return {
            "action_id": action_id,
            "action": action_name,
            "status": status,
            "risk_level": risk,
            "attribution": attribution,
            "confidence": confidence,
            "reversibility": reversibility,
            "reasoning": reasoning,
            "natural_language_explanation": explanation
        }

    def get_decision_traces(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Return recent decision traces with scoring details.
        """
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT action_id, action, attribution, confidence, risk_level, status, reasoning, timestamp "
                "FROM autonomy_audit_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()

        traces = []
        for r in rows:
            traces.append({
                "action_id": r["action_id"],
                "action": r["action"],
                "attribution": r["attribution"],
                "confidence": r["confidence"],
                "uncertainty": round(1.0 - r["confidence"], 2),
                "risk_level": r["risk_level"],
                "status": r["status"],
                "reasoning": r["reasoning"],
                "timestamp": r["timestamp"]
            })
        return traces


# Singleton export
explainability_engine = ExplainabilityEngine()
