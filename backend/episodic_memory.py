"""
Episodic Memory Engine for Aisha AI Assistant (Phase 3 Step 2).

Tracks life events, emotional arcs, milestones, and recurring patterns.
Provides AISHA with awareness of the user's life trajectory.

Categories of episodes:
    milestone  -- achievements, completions, positive events
    event      -- significant happenings (exams, interviews, trips)
    routine    -- detected recurring behaviors
    struggle   -- difficulties, stress patterns, setbacks

Pattern types:
    stress_cycle -- recurring stress periods
    routine      -- repeated daily/weekly behaviors
    habit        -- ongoing habits (positive or negative)
    burnout      -- prolonged stress/overwork detection

**Orchestrator-only mutation**: This module returns MemoryIntent dicts.
The CognitiveOrchestrator validates and commits them.

Usage::

    from episodic_memory import episodic_memory

    # Extract events from a conversation turn
    intents = episodic_memory.extract_intents(user_input, emotion)

    # Query episodes
    episodes = episodic_memory.get_recent_episodes(limit=10)
    arcs = episodic_memory.get_emotional_arc(days=14)
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection


# ---------------------------------------------------------------------------
# Event Detection Signals
# ---------------------------------------------------------------------------

_MILESTONE_SIGNALS = [
    "passed", "completed", "finished", "achieved", "got accepted",
    "graduated", "promoted", "won", "succeeded", "nailed it",
    "finally done", "made it", "got the job", "got selected",
]

_EVENT_SIGNALS = [
    "exam", "interview", "meeting", "presentation", "trip",
    "wedding", "birthday", "anniversary", "moved", "started",
    "deadline", "submission", "appointment", "surgery",
]

_STRUGGLE_SIGNALS = [
    "failed", "rejected", "lost", "broke up", "fired",
    "can't sleep", "overwhelmed", "burnout", "exhausted",
    "behind schedule", "falling apart", "giving up", "stuck",
    "struggling", "struggling with",
]

_ROUTINE_SIGNALS = [
    "every day", "every morning", "every evening", "every week",
    "usually", "always", "routine", "habit", "regularly",
    "as usual", "like always",
]

# People detection pattern -- simple capitalized names
_PEOPLE_PATTERN = re.compile(
    r"\b(?:my\s+(?:mom|dad|brother|sister|friend|boss|girlfriend|boyfriend"
    r"|wife|husband|partner|teacher|professor|colleague|manager))\b"
    r"|(?:[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)"
)


# ---------------------------------------------------------------------------
# Importance Scoring for Episodes
# ---------------------------------------------------------------------------

def _episode_importance(
    category: str,
    emotion: str,
    text: str,
) -> float:
    """Compute importance for an episode."""
    base = {
        "milestone": 0.8,
        "event":     0.6,
        "routine":   0.3,
        "struggle":  0.7,
    }.get(category, 0.5)

    emotion_boost = {
        "happy": 0.1, "excited": 0.15, "sad": 0.15,
        "stressed": 0.1, "angry": 0.1, "neutral": 0.0,
    }.get(emotion, 0.0)

    return min(1.0, base + emotion_boost)


# ---------------------------------------------------------------------------
# Episodic Memory Engine
# ---------------------------------------------------------------------------

class EpisodicMemory:
    """
    Life event and emotional arc tracker.

    **Read operations** query SQLite directly.
    **Write operations** return MemoryIntent dicts.
    """

    def __init__(self) -> None:
        self._recent_emotions: list[tuple[str, str]] = []  # (emotion, timestamp)
        print("  [EpisodicMemory] Initialized")

    # ----- Event Extraction -----------------------------------------------

    def extract_intents(
        self,
        user_input: str,
        emotion: str = "neutral",
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Analyze user input for life events and return MemoryIntents.

        Does NOT write to the database.
        """
        lower = user_input.lower()
        intents = []
        now = datetime.now().isoformat(timespec="seconds")

        # Track emotion for arc analysis
        self._recent_emotions.append((emotion, now))
        if len(self._recent_emotions) > 100:
            self._recent_emotions = self._recent_emotions[-100:]

        # Detect milestones
        for signal in _MILESTONE_SIGNALS:
            if signal in lower:
                people = self._extract_people(user_input)
                intents.append(self._episode_intent(
                    "milestone", user_input, emotion, people, now,
                ))
                break

        # Detect events (if not already a milestone)
        if not intents:
            for signal in _EVENT_SIGNALS:
                if signal in lower:
                    people = self._extract_people(user_input)
                    intents.append(self._episode_intent(
                        "event", user_input, emotion, people, now,
                    ))
                    break

        # Detect struggles
        for signal in _STRUGGLE_SIGNALS:
            if signal in lower:
                if not any(i["data"]["category"] == "struggle" for i in intents):
                    intents.append(self._episode_intent(
                        "struggle", user_input, emotion,
                        self._extract_people(user_input), now,
                    ))
                break

        # Detect routines
        for signal in _ROUTINE_SIGNALS:
            if signal in lower:
                intents.append(self._pattern_intent(
                    self._summarize_routine(user_input),
                    "routine", now,
                ))
                break

        # Detect stress patterns from emotional trajectory
        stress_intents = self._detect_stress_pattern(now)
        intents.extend(stress_intents)

        return intents

    def _episode_intent(
        self,
        category: str,
        text: str,
        emotion: str,
        people: list[str],
        now: str,
    ) -> dict[str, Any]:
        """Create a MemoryIntent for storing an episode."""
        importance = _episode_importance(category, emotion, text)
        summary = text[:200].strip()

        return {
            "action": "store",
            "table": "episodes",
            "source_module": "episodic_memory",
            "data": {
                "category": category,
                "summary": summary,
                "emotion": emotion,
                "people": json.dumps(people, ensure_ascii=False),
                "importance": round(importance, 4),
                "occurred_at": now,
                "created_at": now,
            },
            "importance": round(importance, 4),
        }

    def _pattern_intent(
        self,
        pattern: str,
        category: str,
        now: str,
    ) -> dict[str, Any]:
        """Create a MemoryIntent for a detected life pattern."""
        return {
            "action": "store",
            "table": "life_patterns",
            "source_module": "episodic_memory",
            "data": {
                "pattern": pattern,
                "category": category,
                "frequency": 1,
                "last_seen": now,
                "context": None,
            },
            "importance": 0.4,
        }

    def _extract_people(self, text: str) -> list[str]:
        """Extract mentioned people from text."""
        matches = _PEOPLE_PATTERN.findall(text)
        # Filter common false positives
        noise = {
            "I", "The", "This", "That", "What", "How", "When",
            "Where", "Why", "But", "And", "Let", "Can", "Did",
            "Hey", "Yes", "Aisha", "AISHA",
        }
        return [m.strip() for m in matches if m.strip() not in noise][:5]

    def _summarize_routine(self, text: str) -> str:
        """Extract a short routine description from text."""
        # Remove routine signal words and clean up
        summary = text[:100].strip()
        for signal in _ROUTINE_SIGNALS:
            summary = summary.replace(signal, "").strip()
        return summary if summary else text[:100]

    def _detect_stress_pattern(self, now: str) -> list[dict[str, Any]]:
        """Check if recent emotions indicate a stress cycle."""
        if len(self._recent_emotions) < 5:
            return []

        recent = self._recent_emotions[-10:]
        stress_emotions = {"sad", "stressed", "angry"}
        stress_count = sum(1 for e, _ in recent if e in stress_emotions)

        if stress_count >= 5:
            # Check if we already recorded a recent stress pattern
            try:
                with get_connection() as conn:
                    existing = conn.execute(
                        "SELECT id FROM life_patterns "
                        "WHERE category = 'stress_cycle' "
                        "AND last_seen > datetime('now', '-1 day')",
                    ).fetchone()
                if existing:
                    return []
            except Exception:
                pass

            return [self._pattern_intent(
                f"Stress cycle: {stress_count}/10 recent interactions showed distress",
                "stress_cycle", now,
            )]

        return []

    # ----- Retrieval (read-only) -------------------------------------------

    def get_recent_episodes(
        self,
        limit: int = 10,
        category: str | None = None,
    ) -> list[dict]:
        """Return recent episodes, optionally filtered by category."""
        with get_connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT id, category, summary, emotion, people, importance, "
                    "occurred_at, created_at FROM episodes "
                    "WHERE category = ? ORDER BY occurred_at DESC LIMIT ?",
                    (category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, category, summary, emotion, people, importance, "
                    "occurred_at, created_at FROM episodes "
                    "ORDER BY occurred_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()

        result = []
        for row in rows:
            d = dict(row)
            try:
                d["people"] = json.loads(d["people"]) if d["people"] else []
            except (json.JSONDecodeError, TypeError):
                d["people"] = []
            result.append(d)
        return result

    def get_emotional_arc(self, days: int = 14) -> dict[str, Any]:
        """
        Return the emotional trajectory over recent days.

        Returns:
            dominant   -- most common emotion
            trend      -- "improving", "declining", "stable"
            counts     -- {emotion: count}
            arc        -- list of (emotion, timestamp) pairs
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT emotion, occurred_at FROM episodes "
                "WHERE occurred_at > ? ORDER BY occurred_at",
                (cutoff,),
            ).fetchall()

        if not rows:
            # Fall back to in-memory recent emotions
            emotions = [e for e, _ in self._recent_emotions[-20:]]
        else:
            emotions = [row["emotion"] for row in rows]

        if not emotions:
            return {
                "dominant": "neutral",
                "trend": "stable",
                "counts": {},
                "arc": [],
            }

        counts = Counter(emotions)
        dominant = counts.most_common(1)[0][0]

        # Trend: compare first half vs second half
        mid = len(emotions) // 2
        if mid > 0:
            negative = {"sad", "stressed", "angry"}
            first_neg = sum(1 for e in emotions[:mid] if e in negative)
            second_neg = sum(1 for e in emotions[mid:] if e in negative)

            if second_neg > first_neg + 1:
                trend = "declining"
            elif first_neg > second_neg + 1:
                trend = "improving"
            else:
                trend = "stable"
        else:
            trend = "stable"

        return {
            "dominant": dominant,
            "trend": trend,
            "counts": dict(counts),
            "arc": [(e, t) for e, t in self._recent_emotions[-20:]],
        }

    def get_patterns(
        self,
        category: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Return detected life patterns."""
        with get_connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM life_patterns WHERE category = ? "
                    "ORDER BY frequency DESC LIMIT ?",
                    (category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM life_patterns ORDER BY frequency DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_people_mentioned(self, limit: int = 10) -> list[str]:
        """Return most frequently mentioned people across all episodes."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT people FROM episodes WHERE people IS NOT NULL",
            ).fetchall()

        all_people: Counter = Counter()
        for row in rows:
            try:
                people = json.loads(row["people"])
                all_people.update(people)
            except (json.JSONDecodeError, TypeError):
                pass

        return [p for p, _ in all_people.most_common(limit)]

    def get_context_summary(self) -> str:
        """
        Generate a brief context summary for LLM prompts.

        Includes recent episodes and emotional arc.
        """
        parts = []

        episodes = self.get_recent_episodes(limit=3)
        if episodes:
            parts.append("Recent life events:")
            for ep in episodes:
                parts.append(f"  - [{ep['category']}] {ep['summary'][:60]}")

        arc = self.get_emotional_arc(days=7)
        if arc["counts"]:
            parts.append(f"Emotional trend: {arc['trend']} (dominant: {arc['dominant']})")

        patterns = self.get_patterns(limit=2)
        if patterns:
            parts.append("Detected patterns:")
            for p in patterns:
                parts.append(f"  - {p['pattern'][:60]}")

        return "\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

episodic_memory = EpisodicMemory()
