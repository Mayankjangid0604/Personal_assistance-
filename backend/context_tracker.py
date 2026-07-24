"""
Context Tracker for Aisha AI Assistant (Phase 2 Step 6).

Maintains persistent conversational awareness across sessions:
  - Topic tracking (what the user is talking about)
  - Session summaries (automatic end-of-session digests)
  - Active goal tracking (ongoing user objectives)
  - Emotional continuity (emotional state across sessions)
  - Conversation context windows (recent context for LLM prompts)

All data persisted in SQLite via the personality_repo.

Usage::

    from context_tracker import context_tracker

    # Track a conversation turn
    context_tracker.track_turn(session_id, user_input, response, emotion)

    # Get context for LLM prompt
    context = context_tracker.get_context_window()

    # Get active topics
    topics = context_tracker.get_active_topics()
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from database.repositories import personality_repo


# ---------------------------------------------------------------------------
# Topic Extraction
# ---------------------------------------------------------------------------

# Common topics that AISHA should track
_TOPIC_KEYWORDS = {
    "coding":       ["code", "coding", "programming", "debug", "python", "javascript",
                     "function", "class", "variable", "algorithm", "api", "git"],
    "work":         ["work", "job", "office", "meeting", "deadline", "project",
                     "boss", "colleague", "career", "salary"],
    "study":        ["study", "exam", "assignment", "homework", "class", "lecture",
                     "college", "university", "school", "test", "grade"],
    "health":       ["health", "exercise", "workout", "diet", "sleep", "medical",
                     "doctor", "gym", "fitness", "weight", "calories"],
    "relationship": ["relationship", "friend", "family", "partner", "parents",
                     "girlfriend", "boyfriend", "marriage", "love", "breakup"],
    "finance":      ["money", "budget", "savings", "invest", "expense", "salary",
                     "loan", "debt", "payment", "finance"],
    "hobby":        ["music", "movie", "game", "book", "travel", "cook", "art",
                     "photography", "sport", "garden"],
    "planning":     ["plan", "goal", "schedule", "organize", "priority", "todo",
                     "roadmap", "milestone", "timeline"],
    "emotion":      ["feel", "feeling", "mood", "happy", "sad", "stressed",
                     "angry", "anxious", "worried", "excited"],
}

_STOPWORDS = {
    "i", "me", "my", "we", "you", "your", "it", "its", "the", "a", "an",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "can", "may",
    "to", "of", "in", "for", "on", "at", "by", "with", "from", "and", "or",
    "but", "not", "no", "so", "if", "as", "up", "out", "about", "into",
    "that", "this", "what", "which", "who", "how", "when", "where", "why",
    "all", "each", "every", "some", "any", "just", "also", "than", "then",
    "very", "too", "much", "more", "most", "only", "own", "other",
    "hey", "hi", "hello", "thanks", "thank", "please", "ok", "okay",
    "yes", "no", "yeah", "yep", "nah", "nope",
}


def extract_topics(user_input: str) -> list[str]:
    """Extract topic categories from user input."""
    lower = user_input.lower()
    found = []

    for topic, keywords in _TOPIC_KEYWORDS.items():
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", lower):
                found.append(topic)
                break

    return found


def extract_key_terms(user_input: str, max_terms: int = 5) -> list[str]:
    """Extract significant terms from user input (non-stopword content words)."""
    words = re.findall(r'\b[a-z]{3,}\b', user_input.lower())
    content_words = [w for w in words if w not in _STOPWORDS]
    counts = Counter(content_words)
    return [w for w, _ in counts.most_common(max_terms)]


# ---------------------------------------------------------------------------
# Context Tracker
# ---------------------------------------------------------------------------

class ContextTracker:
    """
    Tracks conversational context across sessions.

    Maintains running awareness of:
    - Current topics being discussed
    - Session-level summaries
    - Active user goals
    - Emotional trajectory
    """

    def __init__(self) -> None:
        self._session_turns: dict[str, int] = {}      # session_id -> turn count
        self._session_topics: dict[str, list[str]] = {}  # session_id -> topics
        self._session_emotions: dict[str, list[str]] = {}  # session_id -> emotions
        self._active_topics: list[str] = []             # current conversation topics
        print("  [Context] Tracker initialized")

    def track_turn(
        self,
        session_id: str,
        user_input: str,
        response: str,
        emotion: str = "neutral",
        handler: str = "general",
    ) -> dict[str, Any]:
        """
        Process a conversation turn and update context.

        Returns a dict with:
        - topics: list of detected topics
        - key_terms: significant terms
        - turn_number: which turn in the session
        - is_topic_shift: whether the topic changed
        """
        # Update turn counter
        self._session_turns[session_id] = self._session_turns.get(session_id, 0) + 1
        turn_number = self._session_turns[session_id]

        # Extract topics
        topics = extract_topics(user_input)
        key_terms = extract_key_terms(user_input)

        # Track topics for this session
        if session_id not in self._session_topics:
            self._session_topics[session_id] = []
        prev_topics = self._session_topics[session_id][-3:] if self._session_topics[session_id] else []
        self._session_topics[session_id].extend(topics)

        # Track emotions for this session
        if session_id not in self._session_emotions:
            self._session_emotions[session_id] = []
        self._session_emotions[session_id].append(emotion)

        # Detect topic shift
        is_topic_shift = bool(topics) and bool(prev_topics) and not set(topics).intersection(prev_topics)

        # Update active topics
        self._active_topics = topics if topics else self._active_topics

        # Persist context to SQLite
        for topic in (topics or ["general"]):
            personality_repo.save_context(
                session_id=session_id,
                topic=topic,
                summary=user_input[:100],
                emotion=emotion,
                turn_count=turn_number,
            )

        return {
            "topics": topics,
            "key_terms": key_terms,
            "turn_number": turn_number,
            "is_topic_shift": is_topic_shift,
        }

    def get_active_topics(self) -> list[str]:
        """Return the currently active conversation topics."""
        return list(self._active_topics)

    def get_session_topics(self, session_id: str) -> list[str]:
        """Return all topics discussed in a session."""
        return list(set(self._session_topics.get(session_id, [])))

    def get_emotional_trajectory(self, session_id: str) -> dict[str, Any]:
        """
        Return the emotional trajectory for a session.

        Returns:
        - emotions: list of emotions in order
        - dominant: most frequent emotion
        - trend: "improving", "declining", or "stable"
        """
        emotions = self._session_emotions.get(session_id, [])
        if not emotions:
            return {"emotions": [], "dominant": "neutral", "trend": "stable"}

        counts = Counter(emotions)
        dominant = counts.most_common(1)[0][0]

        # Determine trend from last 5 emotions
        negative = {"sad", "stressed", "angry"}
        positive = {"happy", "excited"}
        recent = emotions[-5:]

        neg_count = sum(1 for e in recent if e in negative)
        pos_count = sum(1 for e in recent if e in positive)

        if neg_count >= 3:
            trend = "declining"
        elif pos_count >= 3:
            trend = "improving"
        else:
            trend = "stable"

        return {
            "emotions": emotions[-10:],
            "dominant": dominant,
            "trend": trend,
        }

    def finalize_session(self, session_id: str) -> dict | None:
        """
        Generate and save a session summary.

        Called when a session ends (time gap detected or explicit close).
        Returns the summary dict, or None if no turns.
        """
        turn_count = self._session_turns.get(session_id, 0)
        if turn_count == 0:
            return None

        topics = self.get_session_topics(session_id)
        trajectory = self.get_emotional_trajectory(session_id)

        summary_parts = []
        if topics:
            summary_parts.append(f"Topics: {', '.join(topics)}")
        summary_parts.append(f"Turns: {turn_count}")
        summary_parts.append(f"Mood: {trajectory['dominant']} ({trajectory['trend']})")

        summary_text = " | ".join(summary_parts)

        personality_repo.save_session_summary(
            session_id=session_id,
            summary=summary_text,
            topics=topics,
            dominant_emotion=trajectory["dominant"],
            turn_count=turn_count,
        )

        return {
            "session_id": session_id,
            "summary": summary_text,
            "topics": topics,
            "dominant_emotion": trajectory["dominant"],
            "turn_count": turn_count,
        }

    def get_context_window(self, max_sessions: int = 3) -> str:
        """
        Generate a context window string for LLM prompts.

        Includes recent session summaries and active topics to provide
        conversational continuity.
        """
        parts = []

        # Recent session summaries
        summaries = personality_repo.get_recent_summaries(max_sessions)
        if summaries:
            parts.append("Recent conversations:")
            for s in summaries:
                topics = ", ".join(s.get("topics", []))
                parts.append(f"  - {topics} (mood: {s.get('dominant_emotion', 'neutral')})")

        # Active topics
        if self._active_topics:
            parts.append(f"Current topics: {', '.join(self._active_topics)}")

        # Active goals
        goals = personality_repo.get_active_goals()
        if goals:
            parts.append("Active goals:")
            for g in goals[:3]:
                progress = int(g.get("progress", 0) * 100)
                parts.append(f"  - {g['goal']} ({progress}% done)")

        return "\n".join(parts) if parts else ""

    # -- Goal Management ----------------------------------------------------

    def add_goal(self, goal: str, context: str | None = None) -> int:
        """Create a new tracked goal. Returns the goal ID."""
        return personality_repo.save_goal(goal, context)

    def update_goal(self, goal_id: int, progress: float, status: str | None = None) -> None:
        """Update a goal's progress (0.0-1.0)."""
        personality_repo.update_goal_progress(goal_id, progress, status)

    def get_goals(self) -> list[dict]:
        """Return all active goals."""
        return personality_repo.get_active_goals()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

context_tracker = ContextTracker()
