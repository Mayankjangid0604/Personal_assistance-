"""
Project Cognition Layer for Aisha AI Assistant (Phase 7 Step 1).

Understands evolving long-term projects with milestone cognition,
dependency awareness, blocker detection, and strategic trajectory
understanding.  Provides unfinished-work continuity across sessions.

Project types:
    software     -- software development projects
    research     -- academic or personal research
    study        -- study goals and exam preparation
    creative     -- writing, art, music, design
    startup      -- entrepreneurial ventures
    personal     -- fitness, habits, life goals
    general      -- catch-all

Trajectory states:
    on_track      -- milestones progressing as expected
    accelerating  -- ahead of schedule / recent burst
    stalling      -- progress slowed significantly
    blocked       -- explicit blockers detected
    completed     -- all milestones done

Design principles:
    - Track *conceptual* progress, not invasive monitoring
    - Never guilt users about stalled projects
    - Surfaces context for LLM enrichment, not reminders
    - Language is invitational: "You were working on..." not "You should finish..."

Usage::

    from project_cognition import project_cognition

    project_cognition.create_project("AISHA Phase 7", domain="software")
    project_cognition.add_milestone(1, "Project Cognition Layer")
    projects = project_cognition.get_active_projects()
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_DOMAINS = {
    "software", "research", "study", "creative",
    "startup", "personal", "general",
}

_VALID_STATUSES = {"active", "paused", "completed", "archived"}

_VALID_TRAJECTORIES = {
    "on_track", "accelerating", "stalling", "blocked", "completed",
}

_MILESTONE_STATUSES = {"pending", "in_progress", "completed", "blocked"}

# Blocker detection: milestones stalled this many days trigger detection
_STALL_THRESHOLD_DAYS = 7

# Domain detection keywords
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "software": [
        "code", "coding", "programming", "app", "website", "api",
        "bug", "feature", "deploy", "database", "frontend", "backend",
        "git", "repo", "library", "framework", "test", "debug",
    ],
    "research": [
        "research", "paper", "thesis", "hypothesis", "experiment",
        "data", "analysis", "literature", "review", "methodology",
        "findings", "publication", "citation",
    ],
    "study": [
        "exam", "study", "course", "class", "lecture", "assignment",
        "homework", "grade", "semester", "syllabus", "revision",
        "quiz", "test", "chapter", "textbook",
    ],
    "creative": [
        "write", "writing", "novel", "story", "poem", "art",
        "music", "design", "painting", "sketch", "compose",
        "creative", "film", "video", "animation",
    ],
    "startup": [
        "startup", "business", "launch", "product", "market",
        "customer", "revenue", "funding", "pitch", "investor",
        "mvp", "growth", "scaling",
    ],
    "personal": [
        "fitness", "health", "diet", "exercise", "meditation",
        "habit", "routine", "goal", "self-improvement", "wellness",
    ],
}

# Input patterns for project references
_PROJECT_REF_PATTERNS = [
    re.compile(r"(?:working on|building|developing|creating|writing)\s+(.+?)(?:\.|$)", re.I),
    re.compile(r"(?:my|the|our)\s+(\w+\s+)?project\b", re.I),
    re.compile(r"(?:progress on|update on|status of)\s+(.+?)(?:\.|$)", re.I),
]


# ---------------------------------------------------------------------------
# Project Cognition Engine
# ---------------------------------------------------------------------------

class ProjectCognition:
    """
    Long-term project understanding with milestone tracking and trajectory
    analysis.

    Writes directly to ``projects`` and ``project_milestones`` tables.
    Provides context enrichment for the conversation pipeline.
    """

    def __init__(self) -> None:
        self._project_cache: dict[int, dict] = {}
        print("  [ProjectCognition] Initialized")

    # ----- CRUD Operations ------------------------------------------------

    def create_project(
        self,
        title: str,
        description: str = "",
        domain: str = "general",
    ) -> dict[str, Any]:
        """Create a new project and return its details."""
        domain = domain if domain in _VALID_DOMAINS else "general"
        now = datetime.now().isoformat(timespec="seconds")

        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO projects "
                "(title, description, domain, status, trajectory, progress, "
                "blockers_json, context_json, created_at, updated_at) "
                "VALUES (?, ?, ?, 'active', 'on_track', 0.0, '[]', '{}', ?, ?)",
                (title, description, domain, now, now),
            )
            project_id = cursor.lastrowid

        self._invalidate_cache(project_id)

        return {
            "status": "created",
            "id": project_id,
            "title": title,
            "domain": domain,
        }

    def update_project(
        self, project_id: int, **kwargs: Any,
    ) -> dict[str, Any]:
        """Update project fields. Accepts: title, description, domain, status, trajectory, progress."""
        allowed = {"title", "description", "domain", "status", "trajectory", "progress"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}

        if not updates:
            return {"status": "no_changes"}

        # Validate enum fields
        if "status" in updates and updates["status"] not in _VALID_STATUSES:
            return {"status": "error", "error": f"Invalid status: {updates['status']}"}
        if "trajectory" in updates and updates["trajectory"] not in _VALID_TRAJECTORIES:
            return {"status": "error", "error": f"Invalid trajectory: {updates['trajectory']}"}
        if "domain" in updates and updates["domain"] not in _VALID_DOMAINS:
            updates["domain"] = "general"
        if "progress" in updates:
            updates["progress"] = max(0.0, min(1.0, float(updates["progress"])))

        updates["updated_at"] = datetime.now().isoformat(timespec="seconds")

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [project_id]

        with get_connection() as conn:
            conn.execute(
                f"UPDATE projects SET {set_clause} WHERE id = ?",
                values,
            )

        self._invalidate_cache(project_id)
        return {"status": "updated", "id": project_id, "changes": list(kwargs.keys())}

    def add_milestone(
        self,
        project_id: int,
        title: str,
        order_idx: int = 0,
        notes: str = "",
    ) -> dict[str, Any]:
        """Add a milestone to a project."""
        now = datetime.now().isoformat(timespec="seconds")

        with get_connection() as conn:
            # Verify project exists
            project = conn.execute(
                "SELECT id FROM projects WHERE id = ?", (project_id,),
            ).fetchone()
            if not project:
                return {"status": "error", "error": "Project not found"}

            cursor = conn.execute(
                "INSERT INTO project_milestones "
                "(project_id, title, status, progress, notes, order_idx, "
                "created_at, completed_at) "
                "VALUES (?, ?, 'pending', 0.0, ?, ?, ?, NULL)",
                (project_id, title, notes, order_idx, now),
            )
            milestone_id = cursor.lastrowid

        self._invalidate_cache(project_id)
        return {"status": "created", "id": milestone_id, "project_id": project_id}

    def update_milestone(
        self, milestone_id: int, **kwargs: Any,
    ) -> dict[str, Any]:
        """Update a milestone. Accepts: title, status, progress, notes."""
        allowed = {"title", "status", "progress", "notes"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}

        if not updates:
            return {"status": "no_changes"}

        if "status" in updates and updates["status"] not in _MILESTONE_STATUSES:
            return {"status": "error", "error": f"Invalid status: {updates['status']}"}
        if "progress" in updates:
            updates["progress"] = max(0.0, min(1.0, float(updates["progress"])))

        # Auto-set completed_at
        if updates.get("status") == "completed":
            updates["completed_at"] = datetime.now().isoformat(timespec="seconds")

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [milestone_id]

        with get_connection() as conn:
            conn.execute(
                f"UPDATE project_milestones SET {set_clause} WHERE id = ?",
                values,
            )
            # Get project_id for cache invalidation
            row = conn.execute(
                "SELECT project_id FROM project_milestones WHERE id = ?",
                (milestone_id,),
            ).fetchone()
            if row:
                self._invalidate_cache(row["project_id"])
                # Recalculate project progress
                self._recalculate_progress(conn, row["project_id"])

        return {"status": "updated", "id": milestone_id}

    # ----- Retrieval -------------------------------------------------------

    def get_project(self, project_id: int) -> dict[str, Any] | None:
        """Get a project with all its milestones."""
        if project_id in self._project_cache:
            return self._project_cache[project_id]

        with get_connection() as conn:
            project = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,),
            ).fetchone()
            if not project:
                return None

            milestones = conn.execute(
                "SELECT * FROM project_milestones "
                "WHERE project_id = ? ORDER BY order_idx",
                (project_id,),
            ).fetchall()

        result = dict(project)
        result["blockers_json"] = json.loads(result.get("blockers_json", "[]"))
        result["context_json"] = json.loads(result.get("context_json", "{}"))
        result["milestones"] = [dict(m) for m in milestones]

        self._project_cache[project_id] = result
        return result

    def get_active_projects(self) -> list[dict[str, Any]]:
        """Return all active projects (status = 'active')."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE status = 'active' "
                "ORDER BY updated_at DESC",
            ).fetchall()

        results = []
        for row in rows:
            d = dict(row)
            d["blockers_json"] = json.loads(d.get("blockers_json", "[]"))
            d["context_json"] = json.loads(d.get("context_json", "{}"))
            results.append(d)
        return results

    # ----- Blocker Detection -----------------------------------------------

    def detect_blockers(self, project_id: int) -> list[str]:
        """
        Analyze a project's milestones to detect potential blockers.

        A blocker is detected when:
        - A milestone has been 'in_progress' for > _STALL_THRESHOLD_DAYS
        - A milestone has < 50% progress and is past expected timeline
        - Earlier milestones block later ones (sequential dependency)
        """
        project = self.get_project(project_id)
        if not project:
            return []

        blockers: list[str] = []
        now = datetime.now()

        for ms in project.get("milestones", []):
            if ms["status"] in ("completed", "pending"):
                continue

            # Check stall duration
            try:
                created = datetime.fromisoformat(ms["created_at"])
                age_days = (now - created).days
            except (ValueError, TypeError):
                age_days = 0

            if ms["status"] == "in_progress" and age_days > _STALL_THRESHOLD_DAYS:
                progress = ms.get("progress", 0.0)
                if progress < 0.5:
                    blockers.append(
                        f"'{ms['title']}' has been in progress for {age_days} days "
                        f"with {progress:.0%} progress"
                    )

            # Check sequential dependency (earlier milestones incomplete)
            if ms["status"] in ("in_progress", "blocked"):
                earlier = [
                    m for m in project["milestones"]
                    if m["order_idx"] < ms["order_idx"]
                    and m["status"] != "completed"
                ]
                if earlier:
                    names = ", ".join(f"'{m['title']}'" for m in earlier[:2])
                    blockers.append(
                        f"'{ms['title']}' may be waiting on: {names}"
                    )

        # Update blockers in the project record
        if blockers:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE projects SET blockers_json = ?, trajectory = 'blocked', "
                    "updated_at = ? WHERE id = ?",
                    (json.dumps(blockers), now.isoformat(timespec="seconds"), project_id),
                )
            self._invalidate_cache(project_id)

        return blockers

    # ----- Trajectory Analysis ---------------------------------------------

    def get_project_trajectory(self, project_id: int) -> dict[str, Any]:
        """
        Analyze a project's progress trend.

        Returns trajectory state, velocity, and time context.
        """
        project = self.get_project(project_id)
        if not project:
            return {"trajectory": "unknown", "velocity": 0.0}

        milestones = project.get("milestones", [])
        if not milestones:
            return {
                "trajectory": project.get("trajectory", "on_track"),
                "velocity": 0.0,
                "total_milestones": 0,
                "completed_milestones": 0,
            }

        completed = [m for m in milestones if m["status"] == "completed"]
        in_progress = [m for m in milestones if m["status"] == "in_progress"]
        blocked = [m for m in milestones if m["status"] == "blocked"]

        # Calculate velocity (completions per week)
        try:
            created = datetime.fromisoformat(project["created_at"])
            weeks = max(1, (datetime.now() - created).days / 7)
            velocity = len(completed) / weeks
        except (ValueError, TypeError):
            velocity = 0.0

        # Determine trajectory
        if len(completed) == len(milestones):
            trajectory = "completed"
        elif blocked:
            trajectory = "blocked"
        elif velocity > 0.5:
            trajectory = "accelerating"
        elif in_progress and velocity < 0.1:
            trajectory = "stalling"
        else:
            trajectory = "on_track"

        # Update trajectory in DB
        with get_connection() as conn:
            conn.execute(
                "UPDATE projects SET trajectory = ?, updated_at = ? WHERE id = ?",
                (trajectory, datetime.now().isoformat(timespec="seconds"), project_id),
            )
        self._invalidate_cache(project_id)

        return {
            "trajectory": trajectory,
            "velocity": round(velocity, 2),
            "total_milestones": len(milestones),
            "completed_milestones": len(completed),
            "in_progress_milestones": len(in_progress),
            "blocked_milestones": len(blocked),
            "progress": project.get("progress", 0.0),
        }

    # ----- Conversation Integration ----------------------------------------

    def get_context_for_conversation(self, user_input: str) -> str:
        """
        Generate project-aware context for LLM prompt enrichment.

        Returns a concise summary of relevant active projects.
        Invitational language only — never prescriptive.
        """
        active = self.get_active_projects()
        if not active:
            return ""

        # Find project most relevant to current input
        relevant = self.infer_project_from_input(user_input)

        parts: list[str] = []

        if relevant:
            p = relevant
            parts.append(
                f"The user has been working on '{p['title']}' "
                f"({p['domain']}, {p.get('progress', 0):.0%} complete)."
            )
            blockers = json.loads(p.get("blockers_json", "[]")) if isinstance(p.get("blockers_json"), str) else p.get("blockers_json", [])
            if blockers:
                parts.append(f"Potential blockers: {blockers[0]}")
        elif len(active) <= 3:
            names = ", ".join(f"'{p['title']}'" for p in active)
            parts.append(f"Active projects: {names}.")

        return " ".join(parts)

    def infer_project_from_input(self, user_input: str) -> dict[str, Any] | None:
        """
        Try to detect which project the user is referencing in conversation.

        Uses keyword matching against project titles and domains.
        """
        lower = user_input.lower()
        active = self.get_active_projects()

        best_match: dict | None = None
        best_score = 0

        for project in active:
            score = 0
            title_words = project["title"].lower().split()

            # Check title word overlap
            for word in title_words:
                if len(word) >= 3 and word in lower:
                    score += 2

            # Check domain keywords
            domain = project.get("domain", "general")
            for kw in _DOMAIN_KEYWORDS.get(domain, []):
                if kw in lower:
                    score += 1

            if score > best_score:
                best_score = score
                best_match = project

        # Only return if confidence is reasonable
        return best_match if best_score >= 2 else None

    # ----- Conversation Engine Hooks --------------------------------------

    def detect_project_signal(
        self, user_input: str, emotion: str = "neutral",
    ) -> dict[str, Any]:
        """
        Detect project-related signals in user input.

        Called by ``conversation_engine`` on each turn.
        Returns any detected project reference and context.
        """
        inferred = self.infer_project_from_input(user_input)
        if inferred:
            return {
                "detected": True,
                "project_id": inferred.get("id"),
                "project_title": inferred.get("title"),
                "domain": inferred.get("domain"),
                "progress": inferred.get("progress", 0.0),
            }
        return {"detected": False}

    def get_project_context(self) -> str:
        """
        Get concise project context for response enrichment.

        Called by ``conversation_engine`` to enrich collaborative context.
        """
        active = self.get_active_projects()
        if not active:
            return ""

        parts = []
        for p in active[:3]:
            parts.append(
                f"{p['title']} ({p['domain']}, {p.get('progress', 0):.0%})"
            )
        return "Active projects: " + "; ".join(parts)

    # ----- Diagnostics -----------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return project cognition diagnostic summary."""
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM projects",
            ).fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM projects WHERE status = 'active'",
            ).fetchone()[0]
            total_milestones = conn.execute(
                "SELECT COUNT(*) FROM project_milestones",
            ).fetchone()[0]
            completed_milestones = conn.execute(
                "SELECT COUNT(*) FROM project_milestones WHERE status = 'completed'",
            ).fetchone()[0]

        return {
            "total_projects": total,
            "active_projects": active,
            "total_milestones": total_milestones,
            "completed_milestones": completed_milestones,
            "cache_size": len(self._project_cache),
        }

    # ----- Internal Helpers ------------------------------------------------

    def _recalculate_progress(self, conn: Any, project_id: int) -> None:
        """Recalculate overall project progress from milestone progress."""
        rows = conn.execute(
            "SELECT progress FROM project_milestones WHERE project_id = ?",
            (project_id,),
        ).fetchall()

        if not rows:
            return

        avg_progress = sum(r["progress"] for r in rows) / len(rows)
        conn.execute(
            "UPDATE projects SET progress = ?, updated_at = ? WHERE id = ?",
            (round(avg_progress, 4), datetime.now().isoformat(timespec="seconds"), project_id),
        )

    def _invalidate_cache(self, project_id: int) -> None:
        """Remove a project from the in-memory cache."""
        self._project_cache.pop(project_id, None)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

project_cognition = ProjectCognition()
