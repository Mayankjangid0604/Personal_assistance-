"""
Emotion Engine for Aisha AI Assistant.

Provides emotion detection and cause analysis functions that are shared
across the skill system. This module was extracted from brain.py to
allow clean imports from skill modules without circular dependencies.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Emotion Detection
# ---------------------------------------------------------------------------

EMOTION_KEYWORDS: dict[str, list[str]] = {
    "sad":      ["sad", "upset", "depress", "unhappy", "crying",
                 "lonely", "heartbrok", "miserab"],
    "happy":    ["happy", "excited", "great", "awesome", "amazing",
                 "wonderful", "fantastic", "joyful", "thrilled"],
    "stressed": ["stress", "tired", "pressur", "overwhelm",
                 "exhaust", "burnout", "anxious", "worr"],
    "angry":    ["angry", "frustrat", "annoy", "furious",
                 "irritat", "mad", "pissed"],
}


def detect_emotion(user_input: str) -> str:
    """
    Detect the user's emotional state from keyword matching.

    Uses prefix/stem matching so that variations like "stressed",
    "stressing", "frustrating", "annoyed" all match.

    Returns one of: ``"sad"``, ``"happy"``, ``"stressed"``,
    ``"angry"``, or ``"neutral"``.
    """
    normalised = user_input.lower().strip()

    for emotion, keywords in EMOTION_KEYWORDS.items():
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}", normalised):
                return emotion

    return "neutral"


# ---------------------------------------------------------------------------
# Emotion Cause Detection
# ---------------------------------------------------------------------------

_CAUSE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bbecause\s+(?:of\s+)?(.+)",      re.IGNORECASE),
    re.compile(r"\bdue\s+to\s+(.+)",               re.IGNORECASE),
    re.compile(r"\bsince\s+(.+)",                   re.IGNORECASE),
    re.compile(r"\babout\s+(.+)",                    re.IGNORECASE),
    re.compile(r"\bover\s+(.+)",                     re.IGNORECASE),
    re.compile(r"\bwith\s+(my\s+.+)",               re.IGNORECASE),
]

_CAUSE_TOPICS: dict[str, str] = {
    "exam":         "exams",
    "test":         "a test",
    "assignment":   "an assignment",
    "deadline":     "a deadline",
    "work":         "work",
    "job":          "work",
    "boss":         "work",
    "office":       "work",
    "school":       "school",
    "college":      "college",
    "study":        "studies",
    "studies":      "studies",
    "family":       "family",
    "parents":      "family",
    "relationship": "a relationship",
    "breakup":      "a breakup",
    "friend":       "a friend",
    "money":        "finances",
    "health":       "health",
    "sleep":        "sleep",
    "project":      "a project",
}


def detect_emotion_cause(user_input: str) -> str | None:
    """
    Attempt to extract *why* the user feels a certain way.

    First checks for causal connectors ("because", "due to", "since").
    Falls back to topic keyword scanning if no connector is found.

    Returns the cause as a short string, or ``None``.
    """
    normalised = user_input.lower().strip()

    for pat in _CAUSE_PATTERNS:
        m = pat.search(normalised)
        if m:
            cause = m.group(1).strip().rstrip(".,!?")
            cause = re.split(r"\b(and|but|so|then)\b", cause, maxsplit=1)[0].strip()
            if cause and len(cause) > 2:
                return cause

    for keyword, label in _CAUSE_TOPICS.items():
        if re.search(rf"\b{re.escape(keyword)}", normalised):
            return label

    return None


# ---------------------------------------------------------------------------
# Response Style Detection
# ---------------------------------------------------------------------------

def detect_response_style(user_input: str) -> str:
    """
    Detect the user's preferred response style from linguistic cues.

    Returns one of: ``"casual"``, ``"formal"``, or ``"normal"``.
    """
    lower = user_input.lower()

    casual_markers = ["bro", "dude", "lol", "haha", "yo", "man",
                      "wassup", "sup", "yoo", "bruh"]
    formal_markers = ["sir", "ma'am", "maam", "please",
                      "could you", "would you", "kindly"]

    if any(m in lower for m in casual_markers):
        return "casual"
    if any(m in lower for m in formal_markers):
        return "formal"
    return "normal"
