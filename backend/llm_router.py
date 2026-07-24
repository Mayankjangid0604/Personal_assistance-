"""
LLM Router for Aisha AI Assistant.

Gemini-primary with local fallback.  Two-tier decision:

    Tier 1 -- Simple queries (greetings, short text, casual chat)
              are handled instantly by the local response_generator.
              No API call is made.

    Tier 2 -- Complex queries (explanations, questions, learning,
              coding, long-form input) are sent to Google Gemini.
              If Gemini fails, the system falls back to the local
              response_generator automatically.

Setup:
    Add your Gemini key(s) to ``.env`` in the project root::

        GEMINI_API_KEY=your_key_here
        GEMINI_API_KEY_1=your_key_here
        GEMINI_API_KEY_2=optional_backup_key

Usage::

    from llm_router import generate_ai_response

    response = generate_ai_response(
        user_input="Explain recursion in detail",
        context={"user_name": "Mayank", "emotion": "curious"},
    )
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Environment Setup
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)


# ---------------------------------------------------------------------------
# Gemini Key Loading  (multi-key support)
# ---------------------------------------------------------------------------

def _is_real_key(key: str | None) -> bool:
    """Return True only if *key* is set and isn't a placeholder."""
    if not key:
        return False
    placeholders = {"", "your_gemini_key_here", "YOUR_KEY_HERE", "sk-xxx"}
    return key.strip() not in placeholders


def _load_gemini_keys(max_slots: int = 10) -> list[str]:
    """
    Load all valid Gemini API keys from environment variables.

    Checks ``GEMINI_API_KEY`` (legacy) and ``GEMINI_API_KEY_1`` through
    ``GEMINI_API_KEY_{max_slots}``.  Returns a de-duplicated list.
    """
    seen: set[str] = set()
    keys: list[str] = []

    # Legacy single-key variable
    legacy = os.environ.get("GEMINI_API_KEY")
    if _is_real_key(legacy) and legacy.strip() not in seen:
        keys.append(legacy.strip())
        seen.add(legacy.strip())

    # Numbered slots
    for i in range(1, max_slots + 1):
        val = os.environ.get(f"GEMINI_API_KEY_{i}")
        if _is_real_key(val) and val.strip() not in seen:
            keys.append(val.strip())
            seen.add(val.strip())

    return keys


GEMINI_KEYS: list[str] = _load_gemini_keys()


# ---------------------------------------------------------------------------
# Simple-Query Detection
# ---------------------------------------------------------------------------

_SIMPLE_EXACT: set[str] = {
    # Greetings
    "hi", "hello", "hey", "yo", "sup", "hii", "hiii",
    "namaste", "salam", "howdy", "wassup", "what's up",
    # Thanks
    "thanks", "thank you", "thankyou", "thx", "ty",
    # Acknowledgements
    "ok", "okay", "k", "kk", "sure", "yes", "no", "yep", "nope",
    # Farewells
    "bye", "goodbye", "good night", "good morning", "good evening",
    "gm", "gn", "good afternoon",
    # Fillers / reactions
    "hmm", "hm", "ah", "oh", "wow", "lol", "haha", "hehe",
    "nice", "cool", "great", "awesome", "amazing",
}

_SIMPLE_MAX_WORDS = 4

# Keywords that signal a complex query even if the message is short.
_COMPLEX_SIGNALS: set[str] = {
    "code", "program", "debug", "explain", "algorithm",
    "function", "error", "fix", "write", "build", "create",
    "python", "javascript", "java", "html", "css", "sql",
    "why", "how does", "compare", "difference", "define",
    "what is", "teach", "learn", "tutorial", "guide",
}


def is_simple_query(user_input: str) -> bool:
    """
    Determine whether *user_input* is simple enough to answer locally.

    Returns ``True`` (use local) when:
    - Input exactly matches a known greeting / filler, OR
    - Input is very short (<= 4 words) with no complex-signal keywords.
    """
    normalised = user_input.lower().strip().rstrip("!?.,'\"")

    if normalised in _SIMPLE_EXACT:
        return True

    words = normalised.split()
    if len(words) <= _SIMPLE_MAX_WORDS:
        if not any(sig in normalised for sig in _COMPLEX_SIGNALS):
            return True

    return False


# ---------------------------------------------------------------------------
# Prompt Builder
# ---------------------------------------------------------------------------

def _build_gemini_prompt(user_input: str, context: dict[str, Any]) -> str:
    """Build a single prompt string for Gemini from user input + context."""
    name = context.get("user_name", "User")
    emotion = context.get("emotion", "neutral")
    role = context.get("role", "assistant")

    # Recent chat history for continuity
    history_block = ""
    chat_history = context.get("chat_history", [])
    if chat_history:
        history_block = "\n\nRecent conversation:\n"
        for turn in chat_history[-3:]:
            history_block += f"User: {turn.get('user', '')}\n"
            history_block += f"Aisha: {turn.get('aisha', '')}\n"

    system = (
        f"You are Aisha, a warm, intelligent, and empathetic AI assistant. "
        f"You adapt your personality based on the role: {role}. "
        f"The user's name is {name} and they seem to be feeling {emotion}. "
        f"Keep responses concise (2-3 sentences) unless asked for detail. "
        f"Respond naturally and helpfully. Do NOT prefix your response with "
        f"any labels like [Gemini] or [AI]."
        f"{history_block}"
    )

    return f"{system}\n\nUser: {user_input}\nAisha:"


# ---------------------------------------------------------------------------
# Gemini API Call  (with key rotation)
# ---------------------------------------------------------------------------

def call_gemini_with_rotation(user_input: str, context: dict[str, Any]) -> str | None:
    """
    Call Google Gemini, rotating through all available keys.

    Returns the response text on success, or ``None`` if every key
    fails or no keys are available.
    """
    if not GEMINI_KEYS:
        print("  [LLM Router] No valid Gemini keys available.")
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        print("  [LLM Router] google-generativeai package not installed.")
        return None

    prompt = _build_gemini_prompt(user_input, context)

    for idx, key in enumerate(GEMINI_KEYS):
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"  [LLM Router] Gemini key #{idx + 1} failed: {e}")
            continue

    return None


# ---------------------------------------------------------------------------
# Local Fallback
# ---------------------------------------------------------------------------

def _local_response(user_input: str, context: dict[str, Any]) -> str:
    """
    Generate a response using the local rule-based response_generator.

    Cost-free and instant -- used for simple queries AND as the
    ultimate fallback when Gemini fails.
    """
    from response_generator import generate_response
    role = context.get("role", "assistant")
    return generate_response(user_input, role).response


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def generate_ai_response(
    user_input: str,
    context: dict[str, Any] | None = None,
) -> str:
    """
    Route *user_input* through the two-tier system.

    1. Simple query  -->  local response (no API cost).
    2. Complex query  -->  Gemini API.
    3. Gemini fails   -->  local response fallback.

    Parameters
    ----------
    user_input : str
        Raw text from the user.
    context : dict, optional
        Metadata (``user_name``, ``emotion``, ``role``, ``chat_history``).

    Returns
    -------
    str
        Natural response text (no "[Gemini]" prefix).
    """
    if context is None:
        context = {}

    # -- Tier 1: Simple query --> local response --------------------------
    if is_simple_query(user_input):
        print("  [LLM Router] Simple query --> local response.")
        return _local_response(user_input, context)

    # -- Tier 2: Complex query --> Gemini API -----------------------------
    print("  [LLM Router] Complex query --> calling Gemini.")
    result = call_gemini_with_rotation(user_input, context)

    if result:
        return result

    # -- Fallback: Gemini failed --> local response -----------------------
    print("  [LLM Router] Gemini failed --> using local fallback.")
    return _local_response(user_input, context)


# ---------------------------------------------------------------------------
# Streaming Entry Point (SSE-compatible generator)
# ---------------------------------------------------------------------------

def generate_ai_response_stream(
    user_input: str,
    context: dict[str, Any] | None = None,
):
    """
    Stream *user_input* through the two-tier system, yielding text chunks.

    Yields str chunks as they arrive from Gemini's streaming API.
    For simple queries, yields the full local response as a single chunk.

    Usage::

        for chunk in generate_ai_response_stream(user_input, context):
            send_sse(chunk)

    Parameters
    ----------
    user_input : str
        Raw text from the user.
    context : dict, optional
        Metadata (``user_name``, ``emotion``, ``role``, ``chat_history``).

    Yields
    ------
    str
        Text chunks.
    """
    if context is None:
        context = {}

    # -- Tier 1: Simple query --> local response (single chunk) -----------
    if is_simple_query(user_input):
        print("  [LLM Router] Simple query --> local response (stream).")
        yield _local_response(user_input, context)
        return

    # -- Tier 2: Complex query --> Gemini Streaming API -------------------
    if GEMINI_KEYS:
        try:
            import google.generativeai as genai
        except ImportError:
            print("  [LLM Router] google-generativeai package not installed.")
            yield _local_response(user_input, context)
            return

        prompt = _build_gemini_prompt(user_input, context)

        for idx, key in enumerate(GEMINI_KEYS):
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel("gemini-2.0-flash")
                response = model.generate_content(prompt, stream=True)

                for chunk in response:
                    if chunk.text:
                        yield chunk.text
                return  # success — exit after first working key
            except Exception as e:
                print(f"  [LLM Router] Gemini streaming key #{idx + 1} failed: {e}")
                continue

    # -- Fallback: Gemini failed --> local response -----------------------
    print("  [LLM Router] Gemini streaming failed --> local fallback.")
    yield _local_response(user_input, context)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def get_api_status() -> dict[str, str]:
    """Return Gemini key availability."""
    if not GEMINI_KEYS:
        return {"gemini": "NO_KEYS"}
    count = len(GEMINI_KEYS)
    return {"gemini": f"LIVE ({count} key{'s' if count > 1 else ''})"}


def explain_routing(user_input: str) -> dict[str, str | None]:
    """Show how *user_input* would be routed without actually calling APIs."""
    if is_simple_query(user_input):
        return {
            "tier": "local",
            "reason": "simple_query",
            "input_preview": user_input[:80],
        }
    return {
        "tier": "gemini",
        "reason": "complex_query",
        "input_preview": user_input[:80],
    }


# ---------------------------------------------------------------------------
# Built-in Tests
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Demonstrate routing logic and key status."""

    test_cases = [
        # Simple --> local (no API)
        ("hi",                                       "LOCAL"),
        ("hello",                                    "LOCAL"),
        ("thanks",                                   "LOCAL"),
        ("ok",                                       "LOCAL"),
        ("good morning",                             "LOCAL"),
        ("lol",                                      "LOCAL"),
        ("how are you",                              "LOCAL"),
        # Complex --> Gemini
        ("Write a Python function for binary search", "GEMINI"),
        ("Explain why the sky is blue",               "GEMINI"),
        ("What is machine learning?",                 "GEMINI"),
        ("Teach me about recursion step by step",     "GEMINI"),
        ("What's the weather like today?",            "GEMINI"),
    ]

    status = get_api_status()

    print("=" * 70)
    print("  AISHA -- LLM Router (Gemini + Local) -- Test Suite")
    print("=" * 70)
    print(f"\n  .env loaded from : {_ENV_PATH}")
    print(f"  Gemini keys      : {status['gemini']}")
    print()

    context = {"user_name": "Mayank", "emotion": "curious", "role": "assistant"}

    for user_input, expected_tier in test_cases:
        routing = explain_routing(user_input)
        actual_tier = routing["tier"].upper()
        match = "OK" if actual_tier == expected_tier else "MISMATCH"

        print(f"  Input    : \"{user_input}\"")
        print(f"  Expected : {expected_tier}")
        print(f"  Actual   : {actual_tier}  [{match}]")

        response = generate_ai_response(user_input, context)
        print(f"  Response : {response[:120]}...")
        print("  " + "-" * 66)
        print()

    print("  All tests completed.")
    print("=" * 70)


if __name__ == "__main__":
    _run_tests()
