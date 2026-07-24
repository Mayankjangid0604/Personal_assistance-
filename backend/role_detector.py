"""
Role Detection Module for Aisha AI Assistant.

Detects the conversational role based on keywords/patterns in user input.
Supported roles: assistant, mentor, friend, girlfriend.
"""

import re
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Role Definitions
# ---------------------------------------------------------------------------

class RoleMatch(NamedTuple):
    """Holds a detected role along with the keyword that triggered it."""
    role: str
    matched_keyword: str | None


# Each role maps to a list of trigger keywords / short phrases.
# Order matters: first match wins.  Add new roles or keywords here.
ROLE_KEYWORDS: dict[str, list[str]] = {
    "mentor": [
        "ma'am", "maam", "guide", "teach", "explain",
        "mentor", "sir", "professor", "learn",
    ],
    "assistant": [
        "help", "do this", "task", "complete", "finish",
        "assist", "work", "schedule", "remind",
    ],
    "friend": [
        "hey", "bro", "friend", "dude", "buddy",
        "chill", "hang out", "what's up", "wassup",
    ],
    "girlfriend": [
        "baby", "love", "miss you", "darling", "sweetheart",
        "babe", "jaan", "jaanu", "cutie",
    ],
}

DEFAULT_ROLE = "assistant"


# ---------------------------------------------------------------------------
# Core Detection Logic
# ---------------------------------------------------------------------------

def detect_role(user_input: str) -> RoleMatch:
    """
    Analyse *user_input* and return the most appropriate ``RoleMatch``.

    Detection strategy
    ------------------
    1. Normalise input to lowercase.
    2. Walk through ``ROLE_KEYWORDS`` in priority order.
    3. Return the first role whose keyword appears in the input.
    4. Fall back to ``DEFAULT_ROLE`` if nothing matches.

    Parameters
    ----------
    user_input : str
        Raw text typed by the user.

    Returns
    -------
    RoleMatch
        A named-tuple with ``role`` and ``matched_keyword`` fields.
    """
    if not user_input or not user_input.strip():
        return RoleMatch(role=DEFAULT_ROLE, matched_keyword=None)

    normalised = user_input.lower().strip()

    for role, keywords in ROLE_KEYWORDS.items():
        for keyword in keywords:
            # Use word-boundary regex so "shell" doesn't match "help" etc.
            pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
            if pattern.search(normalised):
                return RoleMatch(role=role, matched_keyword=keyword)

    return RoleMatch(role=DEFAULT_ROLE, matched_keyword=None)


# ---------------------------------------------------------------------------
# Convenience Helpers
# ---------------------------------------------------------------------------

def get_role(user_input: str) -> str:
    """Shortcut that returns just the role string."""
    return detect_role(user_input).role


# ---------------------------------------------------------------------------
# Built-in Tests / Demo
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Run a quick smoke-test with example inputs and print results."""

    test_cases: list[tuple[str, str]] = [
        # (input_text, expected_role)
        ("Ma'am, can you teach me Python?",        "mentor"),
        ("Please guide me through this topic",     "mentor"),
        ("Help me do this task",                    "assistant"),
        ("Can you complete this work for me?",      "assistant"),
        ("Hey bro, what's up?",                     "friend"),
        ("Let's chill and hang out dude",           "friend"),
        ("I miss you baby",                         "girlfriend"),
        ("Love you darling",                        "girlfriend"),
        ("Tell me a joke",                          "assistant"),   # default
        ("",                                        "assistant"),   # empty
    ]

    print("=" * 60)
    print("  AISHA — Role Detection Module  •  Test Suite")
    print("=" * 60)

    passed = 0
    failed = 0

    for text, expected in test_cases:
        result = detect_role(text)
        status = "[PASS]" if result.role == expected else "[FAIL]"

        if result.role == expected:
            passed += 1
        else:
            failed += 1

        print(f"\n  Input    : \"{text}\"")
        print(f"  Expected : {expected}")
        print(f"  Got      : {result.role}  (keyword: {result.matched_keyword})")
        print(f"  Status   : {status}")

    print("\n" + "-" * 60)
    print(f"  Results: {passed} passed, {failed} failed, {passed + failed} total")
    print("-" * 60)


if __name__ == "__main__":
    _run_tests()
