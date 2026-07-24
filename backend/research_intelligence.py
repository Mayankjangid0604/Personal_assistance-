"""
Research Intelligence System for Aisha AI Assistant (Phase 7 Step 4).

Assists deep exploration and learning with research session tracking,
source relationship mapping, topic evolution tracking, exploratory
questioning, and research continuity across sessions.

Design principles:
    - Encourage curiosity, exploration, and independent reasoning
    - Never tell the user what conclusions to draw
    - Track depth of exploration, not correctness of conclusions
    - Support research continuity across long time spans
    - Suggest under-explored angles, not authoritative directions

Usage::

    from research_intelligence import research_intelligence

    session = research_intelligence.start_session("Quantum Computing", "research")
    research_intelligence.add_finding(session["id"], "Qubits use superposition")
    research_intelligence.add_question(session["id"], "How does decoherence work?")
    depth = research_intelligence.calculate_depth_score(session["id"])
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
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
    "general", "science", "technology", "mathematics", "philosophy",
    "history", "literature", "art", "business", "health",
    "engineering", "social_science", "law",
}

_VALID_STATUSES = {"active", "paused", "completed", "archived"}

# Depth scoring weights
_DEPTH_WEIGHTS = {
    "findings": 0.3,       # Each finding contributes 0.3 / max_findings
    "questions": 0.25,     # Questions show intellectual curiosity
    "sources": 0.2,        # Sources show rigor
    "branching": 0.25,     # Topic branching shows depth of exploration
}

_MAX_FINDINGS_FOR_DEPTH = 20
_MAX_QUESTIONS_FOR_DEPTH = 10
_MAX_SOURCES_FOR_DEPTH = 10

# Question generation templates (invitational)
_QUESTION_TEMPLATES = [
    "What aspects of '{topic}' haven't you explored yet?",
    "How does '{topic}' connect to what you already know?",
    "What assumptions are you making about '{topic}'?",
    "What would change if '{topic}' worked differently?",
    "Who else has thought about '{topic}' from a different angle?",
    "What's the most surprising thing you've found about '{topic}'?",
    "Where does your understanding of '{topic}' feel incomplete?",
    "What would you need to know to feel confident about '{topic}'?",
]


# ---------------------------------------------------------------------------
# Research Intelligence Engine
# ---------------------------------------------------------------------------

class ResearchIntelligence:
    """
    Deep research session tracking with continuity and depth analysis.

    Writes directly to ``research_sessions`` table.
    """

    def __init__(self) -> None:
        print("  [ResearchIntelligence] Initialized")

    # ----- Session Management ----------------------------------------------

    def start_session(
        self,
        topic: str,
        domain: str = "general",
    ) -> dict[str, Any]:
        """Start a new research session."""
        domain = domain if domain in _VALID_DOMAINS else "general"
        now = datetime.now().isoformat(timespec="seconds")

        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO research_sessions "
                "(topic, domain, status, findings_json, questions_json, "
                "sources_json, depth_score, created_at, updated_at) "
                "VALUES (?, ?, 'active', '[]', '[]', '[]', 0.0, ?, ?)",
                (topic, domain, now, now),
            )
            session_id = cursor.lastrowid

        return {
            "status": "created",
            "id": session_id,
            "topic": topic,
            "domain": domain,
        }

    def close_session(self, session_id: int) -> dict[str, Any]:
        """Close a research session."""
        now = datetime.now().isoformat(timespec="seconds")
        depth = self.calculate_depth_score(session_id)

        with get_connection() as conn:
            conn.execute(
                "UPDATE research_sessions SET status = 'completed', "
                "depth_score = ?, updated_at = ? WHERE id = ?",
                (depth, now, session_id),
            )

        return {"status": "closed", "id": session_id, "depth_score": depth}

    # ----- Findings, Questions, Sources ------------------------------------

    def add_finding(
        self,
        session_id: int,
        finding: str,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Record a discovery in a research session."""
        now = datetime.now().isoformat(timespec="seconds")

        with get_connection() as conn:
            session = self._get_session_row(conn, session_id)
            if not session:
                return {"status": "error", "error": "Session not found"}

            findings = json.loads(session["findings_json"])
            findings.append({
                "text": finding,
                "source": source,
                "added_at": now,
            })

            conn.execute(
                "UPDATE research_sessions SET findings_json = ?, updated_at = ? "
                "WHERE id = ?",
                (json.dumps(findings), now, session_id),
            )

        return {
            "status": "added",
            "session_id": session_id,
            "finding_count": len(findings),
        }

    def add_question(
        self,
        session_id: int,
        question: str,
    ) -> dict[str, Any]:
        """Record an exploratory question."""
        now = datetime.now().isoformat(timespec="seconds")

        with get_connection() as conn:
            session = self._get_session_row(conn, session_id)
            if not session:
                return {"status": "error", "error": "Session not found"}

            questions = json.loads(session["questions_json"])
            questions.append({
                "text": question,
                "added_at": now,
                "explored": False,
            })

            conn.execute(
                "UPDATE research_sessions SET questions_json = ?, updated_at = ? "
                "WHERE id = ?",
                (json.dumps(questions), now, session_id),
            )

        return {
            "status": "added",
            "session_id": session_id,
            "question_count": len(questions),
        }

    def add_source(
        self,
        session_id: int,
        source_info: dict[str, str],
    ) -> dict[str, Any]:
        """Track a source (title, url, type, etc.)."""
        now = datetime.now().isoformat(timespec="seconds")

        with get_connection() as conn:
            session = self._get_session_row(conn, session_id)
            if not session:
                return {"status": "error", "error": "Session not found"}

            sources = json.loads(session["sources_json"])
            source_info["added_at"] = now
            sources.append(source_info)

            conn.execute(
                "UPDATE research_sessions SET sources_json = ?, updated_at = ? "
                "WHERE id = ?",
                (json.dumps(sources), now, session_id),
            )

        return {
            "status": "added",
            "session_id": session_id,
            "source_count": len(sources),
        }

    # ----- Retrieval -------------------------------------------------------

    def get_session(self, session_id: int) -> dict[str, Any] | None:
        """Get full session details."""
        with get_connection() as conn:
            row = self._get_session_row(conn, session_id)

        if not row:
            return None

        return self._row_to_dict(row)

    def get_active_sessions(self) -> list[dict[str, Any]]:
        """Return all active research sessions."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM research_sessions WHERE status = 'active' "
                "ORDER BY updated_at DESC",
            ).fetchall()

        return [self._row_to_dict(r) for r in rows]

    # ----- Depth Analysis --------------------------------------------------

    def calculate_depth_score(self, session_id: int) -> float:
        """
        Calculate how deeply a topic has been explored (0.0 - 1.0).

        Based on: number of findings, questions asked, sources consulted,
        and topic branching (question diversity).
        """
        with get_connection() as conn:
            session = self._get_session_row(conn, session_id)
            if not session:
                return 0.0

        findings = json.loads(session["findings_json"])
        questions = json.loads(session["questions_json"])
        sources = json.loads(session["sources_json"])

        # Findings score
        findings_score = min(1.0, len(findings) / _MAX_FINDINGS_FOR_DEPTH)

        # Questions score (curiosity indicator)
        questions_score = min(1.0, len(questions) / _MAX_QUESTIONS_FOR_DEPTH)

        # Sources score (rigor indicator)
        sources_score = min(1.0, len(sources) / _MAX_SOURCES_FOR_DEPTH)

        # Branching score: how diverse are the questions?
        branching_score = 0.0
        if questions:
            from semantic_memory import tokenize
            unique_terms: set[str] = set()
            for q in questions:
                unique_terms.update(tokenize(q.get("text", "")))
            # More unique terms = more branching
            branching_score = min(1.0, len(unique_terms) / 20)

        depth = (
            _DEPTH_WEIGHTS["findings"] * findings_score +
            _DEPTH_WEIGHTS["questions"] * questions_score +
            _DEPTH_WEIGHTS["sources"] * sources_score +
            _DEPTH_WEIGHTS["branching"] * branching_score
        )

        # Update in DB
        now = datetime.now().isoformat(timespec="seconds")
        with get_connection() as conn:
            conn.execute(
                "UPDATE research_sessions SET depth_score = ?, updated_at = ? "
                "WHERE id = ?",
                (round(depth, 4), now, session_id),
            )

        return round(depth, 4)

    # ----- Evolution & Continuity ------------------------------------------

    def get_session_evolution(self, session_id: int) -> dict[str, Any]:
        """
        Analyze how a research session has evolved.

        Shows the sequence of findings and questions over time.
        """
        session = self.get_session(session_id)
        if not session:
            return {"session_id": session_id, "phases": []}

        findings = session.get("findings", [])
        questions = session.get("questions", [])

        # Interleave findings and questions by timestamp
        events = []
        for f in findings:
            events.append({
                "type": "finding",
                "text": f["text"],
                "timestamp": f.get("added_at", ""),
            })
        for q in questions:
            events.append({
                "type": "question",
                "text": q["text"],
                "timestamp": q.get("added_at", ""),
            })

        events.sort(key=lambda e: e.get("timestamp", ""))

        return {
            "session_id": session_id,
            "topic": session.get("topic", ""),
            "depth_score": session.get("depth_score", 0.0),
            "events": events,
            "finding_count": len(findings),
            "question_count": len(questions),
        }

    def get_research_continuity(self, topic: str) -> dict[str, Any]:
        """
        Find related past research sessions for topic continuity.

        Returns past sessions that share topic similarity.
        """
        with get_connection() as conn:
            # Exact topic match
            rows = conn.execute(
                "SELECT * FROM research_sessions "
                "WHERE topic LIKE ? ORDER BY updated_at DESC LIMIT 5",
                (f"%{topic}%",),
            ).fetchall()

        past_sessions = [self._row_to_dict(r) for r in rows]

        # Semantic similarity check
        try:
            from semantic_memory import semantic_memory, tokenize
            topic_tokens = set(tokenize(topic))

            with get_connection() as conn:
                all_sessions = conn.execute(
                    "SELECT id, topic FROM research_sessions "
                    "ORDER BY updated_at DESC LIMIT 20",
                ).fetchall()

            for session in all_sessions:
                if any(s["id"] == session["id"] for s in past_sessions):
                    continue
                session_tokens = set(tokenize(session["topic"]))
                overlap = len(topic_tokens & session_tokens)
                if overlap >= 1:
                    full = self.get_session(session["id"])
                    if full:
                        past_sessions.append(full)
        except Exception:
            pass

        return {
            "topic": topic,
            "related_sessions": past_sessions[:5],
            "has_prior_research": len(past_sessions) > 0,
        }

    # ----- Exploratory Question Generation ---------------------------------

    def suggest_questions(self, session_id: int) -> list[str]:
        """
        Generate exploratory questions based on session content.

        Encourages curiosity and deeper exploration.
        """
        session = self.get_session(session_id)
        if not session:
            return []

        topic = session.get("topic", "this topic")
        findings = session.get("findings", [])
        questions = session.get("questions", [])

        suggestions: list[str] = []

        # Template-based questions
        import random
        templates = random.sample(
            _QUESTION_TEMPLATES,
            min(3, len(_QUESTION_TEMPLATES)),
        )
        for template in templates:
            suggestions.append(template.format(topic=topic))

        # Finding-based questions: explore implications
        for finding in findings[-3:]:
            text = finding.get("text", "")
            if len(text) > 20:
                short = text[:50].rstrip()
                suggestions.append(
                    f"What are the implications of '{short}...'?"
                )

        # Identify unexplored angles
        if findings and not questions:
            suggestions.append(
                f"You have findings but no open questions yet — "
                f"what's still uncertain about '{topic}'?"
            )

        return suggestions[:5]

    # ----- Conversation Engine Hooks ----------------------------------------

    _RESEARCH_SIGNALS = [
        "research", "study", "explore", "investigate", "analyze",
        "learn about", "understand", "look into", "deep dive",
        "reading about", "curious about", "wondering about",
    ]

    def detect_research_signal(
        self, user_input: str,
    ) -> dict[str, Any]:
        """
        Detect research-related signals in user input.

        Called by ``conversation_engine`` on each turn.
        """
        lower = user_input.lower()
        detected = any(s in lower for s in self._RESEARCH_SIGNALS)

        result: dict[str, Any] = {"detected": detected}

        if detected:
            # Check for active sessions on a related topic
            active = self.get_active_sessions()
            for session in active:
                topic = session.get("topic", "").lower()
                if topic and any(w in lower for w in topic.split()):
                    result["active_session_id"] = session["id"]
                    result["active_topic"] = session.get("topic")
                    break

        return result

    def get_research_context(self) -> str:
        """
        Get concise research context for response enrichment.

        Called by ``conversation_engine`` to enrich collaborative context.
        """
        active = self.get_active_sessions()
        if not active:
            return ""

        parts = []
        for s in active[:3]:
            depth = s.get("depth_score", 0.0)
            parts.append(
                f"{s.get('topic', 'unknown')} (depth: {depth:.1%})"
            )
        return "Active research: " + "; ".join(parts)

    # ----- Diagnostics -----------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return research intelligence diagnostic summary."""
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM research_sessions",
            ).fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM research_sessions WHERE status = 'active'",
            ).fetchone()[0]
            avg_depth = conn.execute(
                "SELECT AVG(depth_score) FROM research_sessions",
            ).fetchone()[0] or 0.0

        return {
            "total_sessions": total,
            "active_sessions": active,
            "average_depth": round(avg_depth, 3),
        }

    # ----- Helpers ---------------------------------------------------------

    @staticmethod
    def _get_session_row(conn, session_id: int):
        """Get a raw session row from DB."""
        return conn.execute(
            "SELECT * FROM research_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any]:
        """Convert a research_sessions row to a dict with parsed JSON."""
        d = dict(row)
        d["findings"] = json.loads(d.get("findings_json", "[]"))
        d["questions"] = json.loads(d.get("questions_json", "[]"))
        d["sources"] = json.loads(d.get("sources_json", "[]"))
        return d


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

research_intelligence = ResearchIntelligence()
