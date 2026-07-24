"""
Main Brain Controller for Aisha AI Assistant.

Orchestrates the full pipeline through the **Skill Registry**:

    Request
    → Phase 1: Context Gathering (profile, emotion, role, style)
    → Phase 2: registry.dispatch() — priority-ordered skill resolution
    → Phase 3: Post-Processing (emotion layering, personalisation, trimming)
    → Phase 4: Memory Storage + Logging
    → BrainResult

Priority Order (defined by each skill's ``priority`` attribute):

    1   SAFETY      Crisis keywords intercepted first.
    2   DATA        Delete / export user data.
    3   TASK        System commands (open app, lock screen).
    4   REMINDER    Scheduling / reminder management.
    5   EMOTION     Deep emotional response (only when strong emotion).
    6   JOURNAL     Journal save / view commands.
    7   SUMMARY     Daily summary request.
    8   LEARNING    Practice, plans, suggestions, interests.
    9   POWER       Automations, habits, routines, shortcuts.
   10   RECALL      Chat history queries.
  100   GENERAL     LLM Router → rule-based fallback.

Capabilities:
- Exactly ONE skill handles each request (no overlap/conflict).
- Every conversation is stored in short-term memory.
- Passive tracking (topics, behaviour) runs on every message.
- Structured logging shows which skill handled each request.
- DEBUG mode (set DEBUG=True or env AISHA_DEBUG=1) prints the full decision path.

Public API (consumed by server.py, main.py):
- ``process_input(user_input)`` → BrainResult
- ``handle_input(user_input)`` → str
- ``aisha_memory`` — shared Memory instance
- ``get_emotion_trend()`` — emotion history analytics
"""

import logging
import os
import random
import re
import sys
import time
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — allow imports from sibling packages (database/, core/, skills/)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATABASE_DIR = os.path.join(_PROJECT_ROOT, "database")
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

for _p in (_DATABASE_DIR, _BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Internal imports
# ---------------------------------------------------------------------------

from role_detector import detect_role, RoleMatch
from response_generator import generate_response, GeneratedResponse
from memory import Memory
from emotion_engine import detect_emotion, detect_emotion_cause
from learning import track_topics
from power_tools import record_behaviour
from notifications import add_notification

# Skill Registry — auto-discover and register all skills on import
import skills  # noqa: F401  (triggers auto-discovery in skills/__init__.py)
from core.skill_registry import registry
from skills.base import SkillContext


# Shared memory instance used across the application
aisha_memory = Memory()


# ---------------------------------------------------------------------------
# Debug & Logging Configuration
# ---------------------------------------------------------------------------

DEBUG: bool = os.environ.get("AISHA_DEBUG", "").strip() in ("1", "true", "True")

_log = logging.getLogger("aisha.brain")
if not _log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "  [%(asctime)s] %(levelname)s  %(message)s", datefmt="%H:%M:%S"
    ))
    _log.addHandler(_handler)
    _log.setLevel(logging.DEBUG if DEBUG else logging.INFO)


# Module label constants (used in logging + BrainResult.handler)
MOD_SAFETY   = "safety"
MOD_TASK     = "task"
MOD_REMINDER = "reminder"
MOD_EMOTION  = "emotion"
MOD_JOURNAL  = "journal"
MOD_SUMMARY  = "summary"
MOD_LEARNING = "learning"
MOD_POWER    = "power"
MOD_RECALL   = "recall"
MOD_GENERAL  = "general"
MOD_DATA     = "data_control"


# ---------------------------------------------------------------------------
# User Profile Extraction
# ---------------------------------------------------------------------------

_NAME_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bmy name is\s+([A-Z][a-z]+)",  re.IGNORECASE),
    re.compile(r"\bi am\s+([A-Z][a-z]+)",        re.IGNORECASE),
    re.compile(r"\bi'm\s+([A-Z][a-z]+)",         re.IGNORECASE),
    re.compile(r"\bcall me\s+([A-Z][a-z]+)",     re.IGNORECASE),
]

_NAME_STOPWORDS: set[str] = {
    "a", "an", "the",
    "so", "very", "really", "too", "much", "quite", "pretty", "rather",
    "extremely", "totally", "absolutely", "completely", "utterly",
    "just", "only", "also", "even", "still", "already", "always", "never",
    "almost", "nearly", "barely", "hardly", "merely",
    "fine", "good", "great", "okay", "ok", "bad", "well",
    "happy", "sad", "angry", "mad", "upset", "depressed",
    "tired", "stressed", "exhausted", "bored", "lonely",
    "confused", "lost", "stuck", "worried", "anxious", "nervous",
    "excited", "thrilled", "scared", "afraid", "terrified",
    "sick", "ill", "hungry", "thirsty", "sleepy",
    "sorry", "sure", "ready", "able", "unable",
    "new", "old", "young", "free", "busy", "late", "early",
    "interested", "impressed", "amazed", "surprised", "shocked",
    "pleased", "satisfied", "disappointed", "frustrated",
    "here", "there", "now", "back", "home", "done", "finished",
    "going", "doing", "feeling", "looking", "trying", "getting",
    "having", "making", "coming", "leaving", "working", "learning",
    "running", "writing", "thinking", "wondering", "hoping",
    "planning", "starting", "beginning", "waiting",
    "not", "all", "about", "from", "with", "like",
}

_MIN_NAME_LENGTH = 3

_GOAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bi want to\s+(.+)",           re.IGNORECASE),
    re.compile(r"\bmy goal is(?:\s+to)?\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi wish to\s+(.+)",           re.IGNORECASE),
    re.compile(r"\bi aim to\s+(.+)",            re.IGNORECASE),
]


def _is_valid_name(candidate: str) -> bool:
    """Validate that *candidate* looks like a real name."""
    if not candidate.isalpha():
        return False
    if len(candidate) < _MIN_NAME_LENGTH:
        return False
    if candidate.lower() in _NAME_STOPWORDS:
        return False
    return True


def _extract_and_store_profile(user_input: str) -> dict[str, str]:
    """Scan for name / goal declarations and persist in memory."""
    detected: dict[str, str] = {}

    for pat in _NAME_PATTERNS:
        m = pat.search(user_input)
        if m:
            candidate = m.group(1).strip().title()
            if not _is_valid_name(candidate):
                continue
            aisha_memory.save_user_info("name", candidate)
            detected["name"] = candidate
            break

    for pat in _GOAL_PATTERNS:
        m = pat.search(user_input)
        if m:
            goal = m.group(1).strip().rstrip(".!")
            aisha_memory.save_user_info("goal", goal)
            detected["goal"] = goal
            break

    return detected


# ---------------------------------------------------------------------------
# Emotion History Tracking
# ---------------------------------------------------------------------------

def _record_emotion_history(emotion: str) -> None:
    """Append current emotion to rolling history (last 20)."""
    from datetime import datetime
    history = aisha_memory.get_user_info("emotion_history") or []
    history.append({
        "emotion": emotion,
        "time": datetime.now().isoformat(timespec="seconds"),
    })
    aisha_memory.save_user_info("emotion_history", history[-20:])


def get_emotion_trend() -> dict[str, Any]:
    """
    Analyse the emotion history and return a trend summary.

    Returns
    -------
    dict
        ``dominant`` (str), ``streak`` (int), ``counts`` (dict),
        ``is_declining`` (bool), ``recent`` (list[str]),
        ``direction`` (str).
    """
    history = aisha_memory.get_user_info("emotion_history") or []
    if not history:
        return {
            "dominant": "neutral", "streak": 0, "counts": {},
            "is_declining": False, "recent": [], "direction": "stable",
        }

    from collections import Counter
    emotions = [e["emotion"] for e in history]
    counts = dict(Counter(emotions).most_common())
    dominant = max(counts, key=counts.get)

    # Current streak
    streak = 1
    for i in range(len(emotions) - 2, -1, -1):
        if emotions[i] == emotions[-1]:
            streak += 1
        else:
            break

    # Declining = 3+ negative in last 5
    negative = {"sad", "stressed", "angry"}
    recent_5 = emotions[-5:]
    neg_count = sum(1 for e in recent_5 if e in negative)
    is_declining = neg_count >= 3

    # Trend direction for frontend
    if is_declining:
        direction = "declining"
    elif len(emotions) >= 3 and all(e in {"happy"} for e in emotions[-3:]):
        direction = "improving"
    else:
        direction = "stable"

    return {
        "dominant": dominant,
        "streak": streak,
        "counts": counts,
        "is_declining": is_declining,
        "recent": emotions[-10:],
        "direction": direction,
    }


# ---------------------------------------------------------------------------
# Response Style Detection & Adaptation
# ---------------------------------------------------------------------------

_STYLE_SHORT_KW: list[str] = [
    "short answer", "brief", "quick", "concise", "in short",
    "tldr", "tl;dr", "summarize", "summarise", "keep it short",
]

_STYLE_DETAILED_KW: list[str] = [
    "explain", "detailed", "in detail", "elaborate", "tell me more",
    "go deeper", "more info", "long answer", "full explanation",
]

_DETAIL_EXPANSIONS: list[str] = [
    "Let me explain a bit more --",
    "Here's some more context --",
    "To elaborate further --",
    "Breaking it down --",
    "In more detail --",
]


def detect_response_style(user_input: str) -> str:
    """Detect preferred response length: short, detailed, or normal."""
    normalised = user_input.lower().strip()

    for kw in _STYLE_SHORT_KW:
        if kw in normalised:
            aisha_memory.save_user_info("response_style", "short")
            return "short"

    for kw in _STYLE_DETAILED_KW:
        if kw in normalised:
            aisha_memory.save_user_info("response_style", "detailed")
            return "detailed"

    stored = aisha_memory.get_user_info("response_style")
    return stored if stored else "normal"


def _adapt_response_style(response: str, style: str) -> str:
    """Trim or expand response based on style."""
    if style == "short":
        first_sentence = re.split(r'(?<=[.!?])\s+', response, maxsplit=1)[0]
        if first_sentence and first_sentence[-1] not in '.!?':
            first_sentence += '.'
        return first_sentence

    if style == "detailed":
        expansion = random.choice(_DETAIL_EXPANSIONS)
        extra = (
            "this is an important topic and I'd love to help you "
            "understand it thoroughly. Feel free to ask follow-up questions!"
        )
        return f"{response} {expansion} {extra}"

    return response


# ---------------------------------------------------------------------------
# Emotion Layering for General Responses
# ---------------------------------------------------------------------------

# Import canonical safety keywords from the skill to avoid divergence
from skills.safety import _SAFETY_KEYWORDS


def _adjust_for_emotion(
    response: str, emotion: str, cause: str | None = None,
    user_input: str = "",
) -> str:
    """
    Replace the base response with a human-like emotional response
    when a non-neutral emotion is detected in general handler context.
    """
    # Safety override (belt-and-suspenders — safety skill should catch first)
    if user_input:
        lower = user_input.lower()
        for kw in _SAFETY_KEYWORDS:
            if kw in lower:
                return (
                    "I hear you, and I want you to know you're not alone. "
                    "Please talk to someone who can help -- you can reach a crisis "
                    "helpline anytime (India: iCall 9152987821, Vandrevala Foundation "
                    "1860-2662-345). I'm here for you, and you matter."
                )

    if emotion == "neutral":
        return response

    # Import from the emotion skill's response builder for consistency
    from skills.emotion import _build_emotional_response
    return _build_emotional_response(emotion, cause, aisha_memory)


# ---------------------------------------------------------------------------
# Soft Emotion Layer
# ---------------------------------------------------------------------------

_SOFT_EMOTION_HANDLERS: frozenset[str] = frozenset({
    MOD_TASK, MOD_REMINDER, MOD_LEARNING, MOD_POWER,
})

_SOFT_ACK: dict[str, list[str]] = {
    "sad":      ["I can see you're feeling down.", "I know things are tough right now."],
    "stressed": ["I know you're feeling stressed.", "I can tell things feel heavy."],
    "angry":    ["I hear your frustration.", "I know you're upset."],
    "happy":    ["Glad you're in a good mood!", "Love that energy!"],
}

_SOFT_ACK_CAUSE: dict[str, list[str]] = {
    "sad":      ["I know {cause} is weighing on you.", "{cause} sounds rough."],
    "stressed": ["I know {cause} is stressing you out.", "{cause} sounds heavy."],
    "angry":    ["I get that {cause} is frustrating.", "{cause} would upset anyone."],
    "happy":    ["Sounds like {cause} is going great!", "{cause} must feel amazing!"],
}


def _soft_emotion_prefix(
    response: str, handler: str, emotion: str, cause: str | None,
) -> str:
    """Prepend a SHORT emotional acknowledgement for non-emotion handlers."""
    if emotion == "neutral":
        return response
    if handler not in _SOFT_EMOTION_HANDLERS:
        return response
    if emotion not in _SOFT_ACK:
        return response

    if cause and emotion in _SOFT_ACK_CAUSE:
        line = random.choice(_SOFT_ACK_CAUSE[emotion]).format(cause=cause)
    else:
        line = random.choice(_SOFT_ACK[emotion])

    return f"{line} {response}"


# ---------------------------------------------------------------------------
# Response Personalisation
# ---------------------------------------------------------------------------

def _personalise(response: str) -> str:
    """Prepend user's name for a personal touch."""
    name = aisha_memory.get_user_info("name")
    if not name:
        return response
    if response.lower().startswith(name.lower()):
        return response
    return f"{name}, {response[0].lower()}{response[1:]}"


# ---------------------------------------------------------------------------
# Pipeline Result
# ---------------------------------------------------------------------------

class BrainResult:
    """Bundles every piece of information produced by the pipeline."""

    __slots__ = (
        "user_input", "role_match", "generated_response",
        "is_recall", "profile_updates", "emotion", "response_style",
        "task_detected", "handler",
    )

    def __init__(
        self,
        user_input: str,
        role_match: RoleMatch,
        generated_response: GeneratedResponse,
        is_recall: bool = False,
        profile_updates: dict[str, str] | None = None,
        emotion: str = "neutral",
        response_style: str = "normal",
        task_detected: bool = False,
        handler: str = "general",
    ) -> None:
        self.user_input = user_input
        self.role_match = role_match
        self.generated_response = generated_response
        self.is_recall = is_recall
        self.profile_updates = profile_updates or {}
        self.emotion = emotion
        self.response_style = response_style
        self.task_detected = task_detected
        self.handler = handler

    @property
    def role(self) -> str:
        return self.role_match.role

    @property
    def matched_keyword(self) -> str | None:
        return self.role_match.matched_keyword

    @property
    def response(self) -> str:
        return self.generated_response.response

    def __repr__(self) -> str:
        return (
            f"BrainResult(handler={self.handler!r}, "
            f"role={self.role!r}, "
            f"emotion={self.emotion!r}, "
            f"style={self.response_style!r}, "
            f"task={self.task_detected}, "
            f"response={self.response[:60]!r}...)"
        )


# ---------------------------------------------------------------------------
# Core Handlers
# ---------------------------------------------------------------------------

def handle_input(user_input: str) -> str:
    """
    Process *user_input* through the full Aisha pipeline and return a
    response string.

    This is the simplest entry-point -- it hides all intermediate details.
    """
    result = process_input(user_input)
    return result.response


def process_input(user_input: str) -> BrainResult:
    """
    Central Decision Engine — powered by the Skill Registry.

    Routes each request to exactly ONE skill based on priority via
    ``registry.dispatch()``.

    Phase 1: Context Gathering (always runs)
        - Profile extraction (name, goal)
        - Emotion detection + cause analysis
        - Emotion history recording
        - Response style detection
        - Role detection

    Phase 2: Skill Dispatch
        - Build SkillContext from Phase 1 data
        - Call registry.dispatch() — first matching skill handles

    Phase 3: Post-Processing (runs for ALL handlers)
        - Emotion layering (general handler only)
        - Response style adaptation (general + emotion)
        - Soft emotion prefix (task, reminder, learning, power)
        - Personalisation
        - Response length trimming

    Phase 4: Memory + Logging
        - Store conversation in memory
        - Passive tracking (topics + behaviour)
        - Structured logging
    """
    t0 = time.time()

    # ── Phase 1: Context Gathering (always runs) ──────────────────────

    profile_updates = _extract_and_store_profile(user_input)

    emotion = detect_emotion(user_input)
    emotion_cause = detect_emotion_cause(user_input) if emotion != "neutral" else None

    aisha_memory.save_user_info("last_emotion", emotion)
    if emotion_cause:
        aisha_memory.save_user_info("last_emotion_cause", emotion_cause)
    elif emotion == "neutral":
        aisha_memory.save_user_info("last_emotion_cause", None)

    _record_emotion_history(emotion)
    response_style = detect_response_style(user_input)
    role_match: RoleMatch = detect_role(user_input)

    # ── Phase 2: Skill Dispatch ───────────────────────────────────────

    context = SkillContext(
        emotion=emotion,
        emotion_cause=emotion_cause,
        response_style=response_style,
        role_match=role_match,
        profile_updates=list(profile_updates.keys()),
        memory=aisha_memory,
    )

    handler, response_text = registry.dispatch(user_input, context)

    if DEBUG:
        _log.debug(
            "[DISPATCH] skill=%s matched | registry=%s",
            handler, registry,
        )

    # Ensure we always have a response (defensive)
    if not response_text:
        handler = MOD_GENERAL
        gen_result = generate_response(user_input, role_match.role)
        response_text = gen_result.response

    # ── Phase 3: Post-Processing (runs for ALL handlers) ──────────────

    # Emotion layering for general responses (LLM output gets emotion context)
    if handler == MOD_GENERAL:
        response_text = _adjust_for_emotion(
            response_text, emotion, cause=emotion_cause, user_input=user_input,
        )
        response_text = _adapt_response_style(response_text, response_style)

    # Response style adaptation for emotion handler too
    if handler == MOD_EMOTION:
        response_text = _adapt_response_style(response_text, response_style)

    # Soft emotion layer — acknowledge feelings even when another handler
    # responded (task, reminder, learning, power).
    response_text = _soft_emotion_prefix(
        response_text, handler, emotion, emotion_cause,
    )

    # Personalise (skip for recall dumps and data exports)
    is_recall = handler == MOD_RECALL
    if not is_recall and handler != MOD_DATA:
        response_text = _personalise(response_text)

    # Trim excessively long responses (>500 chars) for non-structured output
    if handler in (MOD_GENERAL, MOD_EMOTION) and len(response_text) > 500:
        sentences = re.split(r'(?<=[.!?])\s+', response_text)
        trimmed = ""
        for s in sentences:
            if len(trimmed) + len(s) > 450:
                break
            trimmed += (" " if trimmed else "") + s
        response_text = trimmed or sentences[0]

    gen_response = GeneratedResponse(role=role_match.role, response=response_text)

    # ── Phase 4: Memory + Logging ─────────────────────────────────────

    # Store in memory
    aisha_memory.add_conversation(
        user_input, role_match.role, gen_response.response
    )

    # Passive tracking (topics + behaviour)
    track_topics(user_input)
    record_behaviour(user_input)

    # Structured logging
    elapsed_ms = int((time.time() - t0) * 1000)
    _log.info(
        "[%s] emotion=%s | %dms | %s",
        handler.upper(),
        emotion,
        elapsed_ms,
        response_text[:80].replace("\n", " "),
    )

    return BrainResult(
        user_input=user_input,
        role_match=role_match,
        generated_response=gen_response,
        is_recall=is_recall,
        profile_updates=profile_updates,
        emotion=emotion,
        response_style=response_style,
        task_detected=(handler == MOD_TASK),
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Built-in Tests / Demo
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Run the full pipeline demonstrating all features including tasks."""

    # Reset memory for a clean test
    aisha_memory.clear_short_term()
    aisha_memory.clear_long_term()

    print("=" * 70)
    print("  AISHA -- Brain Controller (Skill Registry) -- Pipeline Test")
    print("=" * 70)
    print(f"\n  Registry: {registry}\n")

    # -- Phase 1: Set name ------------------------------------------------
    print("  [Phase 1] User introduces themselves:\n")

    r_name = process_input("My name is Rahul")
    print(f"  User    : My name is Rahul")
    print(f"  Handler : {r_name.handler}")
    print(f"  Aisha   : {r_name.response}")
    print("  " + "-" * 66)

    # -- Phase 2: Task execution ------------------------------------------
    print("\n  [Phase 2] Task execution:\n")

    for inp in ["Open Notepad", "open chrome", "launch calculator"]:
        result = process_input(inp)
        print(f"  User    : {inp}")
        print(f"  Handler : {result.handler}")
        print(f"  Task?   : {result.task_detected}")
        print(f"  Aisha   : {result.response}")
        print("  " + "-" * 66)

    # -- Phase 3: Emotional input -----------------------------------------
    print("\n  [Phase 3] Emotional input:\n")

    for inp in ["I'm feeling sad today", "I'm stressed about exams"]:
        result = process_input(inp)
        print(f"  User    : {inp}")
        print(f"  Handler : {result.handler}")
        print(f"  Emotion : {result.emotion}")
        print(f"  Aisha   : {result.response}")
        print("  " + "-" * 66)

    # -- Phase 4: Normal conversation -------------------------------------
    print("\n  [Phase 4] General conversation:\n")

    for inp in ["Hey bro, what's up?", "Help me study for my exam"]:
        result = process_input(inp)
        print(f"  User    : {inp}")
        print(f"  Handler : {result.handler}")
        print(f"  Aisha   : {result.response}")
        print("  " + "-" * 66)

    # -- Phase 5: Recall --------------------------------------------------
    print(f"\n  [Phase 5] Memory recall "
          f"(stored: {aisha_memory.short_term_count}/"
          f"{aisha_memory.short_term_capacity}):\n")

    result = process_input("What did I say before?")
    print(f"  User    : What did I say before?")
    print(f"  Handler : {result.handler}")
    for line in result.response.split("\n"):
        print(f"    {line}")

    print()
    print("  " + "-" * 66)
    print("  Full pipeline test completed successfully.")
    print("=" * 70)


if __name__ == "__main__":
    _run_tests()
