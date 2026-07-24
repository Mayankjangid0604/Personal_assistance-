"""
Emotion Skill — Priority 5.

Handles messages that are primarily emotional with no other intent.
Uses the full emotional response builder from brain.py legacy logic:
  - Natural acknowledgement
  - Cause-aware responses
  - Reflection prompts (~35%)
  - Multi-perspective (~30%)
  - Self-care suggestions (declining trend)
"""

from __future__ import annotations

import random
import re

from skills.base import BaseSkill, SkillContext
from core.skill_registry import registry

from emotion_engine import detect_emotion, detect_emotion_cause
from notifications import is_journal_command, is_summary_command
from learning import is_learning_command
from power_tools import is_power_command
from scheduler import is_reminder_command


# ---------------------------------------------------------------------------
# Intent overlap detection (same logic as legacy brain.py)
# ---------------------------------------------------------------------------

_RECALL_RE = re.compile(
    r"\b(what did i say|show history|last conversation|recent conversation"
    r"|previous chat|chat history|remember what|what we talked)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Natural Response Templates (ported from brain.py)
# ---------------------------------------------------------------------------

_NATURAL_RESPONSES: dict[str, list[str]] = {
    "sad": [
        "I'm sorry you're feeling this way.",
        "That's rough. I'm here.",
        "I hear you.",
        "You don't have to go through this alone.",
    ],
    "happy": [
        "Love that for you!",
        "That's awesome!",
        "Yesss, you deserve that!",
        "That just made my day too.",
    ],
    "stressed": [
        "That's a lot. Take a breath.",
        "I get it, that sounds heavy.",
        "One thing at a time. You've got this.",
        "It's okay to feel overwhelmed.",
    ],
    "angry": [
        "That's valid. I'd be upset too.",
        "I hear you, that's frustrating.",
        "Your feelings make total sense.",
        "Anyone would feel that way.",
    ],
}

_NATURAL_WITH_CAUSE: dict[str, list[str]] = {
    "sad": [
        "{cause} sounds really hard.",
        "I get why {cause} is getting to you.",
    ],
    "happy": [
        "{cause} must feel amazing!",
        "So glad {cause} is going well.",
    ],
    "stressed": [
        "{cause} is a lot -- I get it.",
        "Dealing with {cause} would stress anyone out.",
    ],
    "angry": [
        "{cause} would frustrate anyone.",
        "I totally see why {cause} has you feeling this way.",
    ],
}

_REFLECTION_PROMPTS: dict[str, list[str]] = {
    "sad": [
        "What do you think is making you feel this way?",
        "Is there something specific that triggered this?",
        "What would make today a little better for you?",
    ],
    "stressed": [
        "What's the one thing weighing on you the most right now?",
        "If you could fix just one thing today, what would it be?",
        "Have you been able to take any breaks today?",
    ],
    "angry": [
        "What happened that got you to this point?",
        "Is this about one thing, or has it been building up?",
        "What would help you feel heard right now?",
    ],
}

_SELF_CARE_SUGGESTIONS: list[str] = [
    "Hey, have you had water recently? Hydration helps more than you'd think.",
    "When's the last time you stood up and stretched? Even 30 seconds helps.",
    "Quick idea: close your eyes, take 3 deep breaths. I'll be here when you're back.",
    "Have you eaten recently? Low blood sugar can sneak up on you.",
    "A 5-minute walk can reset your whole mood. Just saying.",
    "You've been going hard. It's okay to rest -- seriously.",
]


# ---------------------------------------------------------------------------
# Multi-Perspective System
# ---------------------------------------------------------------------------

def _get_perspectives(emotion: str, cause: str | None) -> str | None:
    """For problem-based emotions, offer 2-3 short perspectives (~30%)."""
    if emotion == "happy" or not cause:
        return None
    if random.random() > 0.30:
        return None

    logical = [
        f"Logically, {cause} is temporary -- it won't feel this heavy forever.",
        f"Step back for a sec: what's the actual worst case with {cause}?",
        f"If a friend told you about {cause}, what would you say to them?",
    ]
    emotional = [
        "It's totally valid to feel this way. You don't have to 'fix' it right now.",
        "Sometimes just sitting with the feeling helps more than fighting it.",
        "You're allowed to not be okay for a bit.",
    ]
    practical = [
        f"One small step you could take with {cause} -- even tiny -- what would it be?",
        "Sometimes writing it down helps. Want me to save this as a journal entry?",
        "Breaking it into smaller pieces usually makes it feel less impossible.",
    ]
    return " ".join([
        random.choice(logical),
        random.choice(emotional),
        random.choice(practical),
    ])


def _check_self_care(memory) -> str | None:
    """Suggest self-care when emotion trend is declining (~40%)."""
    if not memory:
        return None
    history = memory.get_user_info("emotion_history") or []
    if len(history) < 5:
        return None
    negative = {"sad", "stressed", "angry"}
    recent = [e["emotion"] for e in history[-5:]]
    if sum(1 for e in recent if e in negative) < 3:
        return None
    if random.random() > 0.40:
        return None
    return random.choice(_SELF_CARE_SUGGESTIONS)


def _build_emotional_response(
    emotion: str, cause: str | None, memory=None,
) -> str:
    """
    Build a full human-like emotional response (ported from brain.py).

    Modes (randomly combined to feel natural):
      - Direct comfort (always)
      - Reflection prompt (~35% for negative emotions)
      - Multi-perspective (~30% when cause is known)
      - Self-care suggestion (when trend is declining)
    """
    if emotion not in _NATURAL_RESPONSES:
        return "I sense some strong feelings. I'm here for you."

    parts: list[str] = []

    # 1. Short, natural acknowledgement
    parts.append(random.choice(_NATURAL_RESPONSES[emotion]))

    # 2. Mention cause naturally
    if cause and emotion in _NATURAL_WITH_CAUSE:
        template = random.choice(_NATURAL_WITH_CAUSE[emotion])
        parts.append(template.format(cause=cause))

    # 3. Reflection prompt (~35%, not for happy)
    if emotion != "happy" and emotion in _REFLECTION_PROMPTS:
        if random.random() < 0.35:
            parts.append(random.choice(_REFLECTION_PROMPTS[emotion]))

    # 4. Multi-perspective
    perspective = _get_perspectives(emotion, cause)
    if perspective:
        parts.append(perspective)

    # 5. Self-care (declining trend)
    care = _check_self_care(memory)
    if care:
        parts.append(care)

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Skill Implementation
# ---------------------------------------------------------------------------

class EmotionSkill(BaseSkill):
    name = "emotion"
    priority = 5

    def can_handle(self, user_input: str, context: SkillContext) -> bool:
        if context.emotion == "neutral":
            return False

        # Only handle if no other intent is detected
        has_other = any([
            is_journal_command(user_input),
            is_summary_command(user_input),
            is_learning_command(user_input),
            is_power_command(user_input),
            is_reminder_command(user_input),
            bool(_RECALL_RE.search(user_input)),
        ])
        return not has_other

    def handle(self, user_input: str, context: SkillContext) -> str:
        return _build_emotional_response(
            context.emotion, context.emotion_cause, context.memory,
        )


registry.register(EmotionSkill())
