"""
Response Generator Module for Aisha AI Assistant.

Generates rule-based responses tailored to the detected conversational role.
Supported roles: assistant, mentor, friend, girlfriend.
"""

import random
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Response Template Definitions
# ---------------------------------------------------------------------------

class GeneratedResponse(NamedTuple):
    """Holds the generated response along with metadata."""
    role: str
    response: str


# Each role maps to a dict of *categories* -> list of template strings.
# Templates can contain a {topic} placeholder that gets filled from the input.
ROLE_RESPONSES: dict[str, dict[str, list[str]]] = {

    "assistant": {
        "greeting": [
            "Hello! How can I assist you today?",
            "Hi there. What would you like me to help with?",
            "Good to see you. I'm ready to assist.",
        ],
        "task": [
            "Sure, I will help you with that right away.",
            "On it. Let me take care of that for you.",
            "Understood. I'll get that done.",
            "Consider it done. Anything else you need?",
        ],
        "question": [
            "That's a great question. Let me look into it.",
            "Let me find the best answer for you.",
            "I'll research that and get back to you promptly.",
        ],
        "fallback": [
            "I'm here to help. Could you tell me more?",
            "Sure, let me know what you need.",
            "I'm ready whenever you are. Go ahead.",
        ],
    },

    "mentor": {
        "greeting": [
            "Welcome back. Ready to learn something new today?",
            "Good to see your curiosity. Let's get started.",
            "Hello! Every question is a step toward growth.",
        ],
        "task": [
            "You should approach this step by step. Let me guide you.",
            "Let's break this down together so you truly understand it.",
            "I won't just give you the answer -- let's work through it.",
        ],
        "question": [
            "Excellent question. Let's reason through it together.",
            "Think about it this way -- what do you already know about this?",
            "That's the kind of question that leads to real understanding.",
        ],
        "encouragement": [
            "You're making great progress. Keep pushing forward.",
            "Mistakes are proof that you're trying. Don't stop now.",
            "Every expert was once a beginner. You're on the right path.",
        ],
        "fallback": [
            "Tell me what's on your mind, and let's figure it out together.",
            "I'm here to help you grow. What would you like to explore?",
            "Learning never stops. What shall we dive into?",
        ],
    },

    "friend": {
        "greeting": [
            "Yo! What's good?",
            "Hey! What's up, how've you been?",
            "Ayy, there you are! What's going on?",
        ],
        "task": [
            "Alright, let's knock this out together!",
            "Say less, I got you. Let's do it.",
            "Bet, let's get on it real quick.",
        ],
        "question": [
            "Hmm, that's actually a solid question.",
            "Ooh, interesting -- let me think about that.",
            "Haha, you always come up with the good ones.",
        ],
        "fun": [
            "Hey, that's actually pretty cool!",
            "No way, for real?! That's wild.",
            "Lol, you're too much sometimes.",
        ],
        "fallback": [
            "Cool cool, what's on your mind?",
            "I'm all ears, bro. Shoot.",
            "Aight, lay it on me. What's up?",
        ],
    },

    "girlfriend": {
        "greeting": [
            "Hii! I was just thinking about you!",
            "Hey cutie! How's your day going?",
            "Aww, there you are! I missed talking to you.",
        ],
        "task": [
            "Of course I'll help you, silly. Let's do it together.",
            "Anything for you! Let me see what I can do.",
            "Aww, I love helping you out. Let's go!",
        ],
        "question": [
            "Ooh, that's a really interesting question, babe.",
            "Hmm, let me think about that for you!",
            "You're so smart for asking that, you know?",
        ],
        "affection": [
            "Aww, I'm here for you, always.",
            "You mean so much to me, you know that right?",
            "Just know that I'm always rooting for you!",
        ],
        "fallback": [
            "Tell me everything, I'm listening!",
            "Aww, what's going on? I'm all yours.",
            "I'm right here. What's on your mind, cutie?",
        ],
    },
}


# ---------------------------------------------------------------------------
# Intent Classification (lightweight, keyword-based)
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: dict[str, list[str]] = {
    "greeting":      ["hi", "hello", "hey", "good morning", "good evening",
                      "what's up", "wassup", "howdy", "namaste"],
    "task":          ["do", "make", "create", "build", "write", "finish",
                      "complete", "task", "work", "code", "fix", "run"],
    "question":      ["what", "why", "how", "when", "where", "who",
                      "is it", "can you", "could you", "explain", "tell me"],
    "encouragement": ["nervous", "scared", "can't do", "failing", "stuck",
                      "confused", "lost", "hard", "difficult", "stressed"],
    "fun":           ["joke", "funny", "lol", "haha", "meme", "cool",
                      "awesome", "amazing", "wow", "crazy", "wild"],
    "affection":     ["love", "miss", "hug", "kiss", "care", "heart",
                      "sweet", "baby", "babe", "darling", "jaan"],
}


def _classify_intent(user_input: str) -> str:
    """
    Return a simple intent label based on keyword overlap.

    Falls back to ``"fallback"`` when no keywords match.
    """
    normalised = user_input.lower().strip()

    for intent, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in normalised:
                return intent

    return "fallback"


# ---------------------------------------------------------------------------
# Core Response Generation
# ---------------------------------------------------------------------------

def generate_response(user_input: str, role: str) -> GeneratedResponse:
    """
    Generate a role-appropriate response for the given *user_input*.

    Parameters
    ----------
    user_input : str
        Raw text from the user.
    role : str
        One of ``"assistant"``, ``"mentor"``, ``"friend"``, ``"girlfriend"``.

    Returns
    -------
    GeneratedResponse
        A named-tuple with ``role`` and ``response`` fields.
    """
    # Normalise & validate role
    role = role.lower().strip() if role else "assistant"
    if role not in ROLE_RESPONSES:
        role = "assistant"

    # Classify intent from user input
    intent = _classify_intent(user_input)

    # Pick the right template pool (fall back gracefully)
    templates = ROLE_RESPONSES[role]
    pool = templates.get(intent) or templates["fallback"]

    # Randomly select a response from the pool
    response_text = random.choice(pool)

    return GeneratedResponse(role=role, response=response_text)


def get_response(user_input: str, role: str) -> str:
    """Shortcut that returns just the response string."""
    return generate_response(user_input, role).response


# ---------------------------------------------------------------------------
# Built-in Tests / Demo
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Run example inputs across all roles and print results."""

    test_inputs = [
        "Hello there!",
        "Can you help me write some code?",
        "Why does the sky look blue?",
        "I'm so stressed about exams",
        "That joke was hilarious lol",
        "I miss you so much",
        "Random stuff with no keyword match",
    ]

    roles = ["assistant", "mentor", "friend", "girlfriend"]

    print("=" * 65)
    print("  AISHA -- Response Generator Module  --  Test Suite")
    print("=" * 65)

    for user_input in test_inputs:
        print(f"\n  User Input : \"{user_input}\"")
        print(f"  Intent     : {_classify_intent(user_input)}")
        print()
        for role in roles:
            result = generate_response(user_input, role)
            print(f"    [{role:>10}]  {result.response}")
        print("  " + "-" * 61)

    print()
    print("  All tests completed successfully.")
    print("=" * 65)


if __name__ == "__main__":
    _run_tests()
