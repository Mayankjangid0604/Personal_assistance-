"""
LLM Router for Aisha AI Assistant.

Phase 9 update: this module is now a thin, **fully backward-compatible**
facade over the vendor-neutral provider platform in :mod:`providers`.  Every
function that existed before keeps its exact signature and behaviour; the
routing underneath now understands multiple providers and local models.

Two-tier decision (unchanged semantics)
---------------------------------------
    Tier 1 -- Simple queries (greetings, short text, casual chat) are handled
              instantly by the local response_generator.  No model call.

    Tier 2 -- Complex queries are routed by the provider registry:
                  local Ollama model (by task)  ->  Gemini  ->  rule-based.
              With no local models and no Gemini keys this collapses to the
              original "complex -> Gemini, else local fallback" behaviour.

Setup (unchanged)::

        GEMINI_API_KEY=your_key_here
        GEMINI_API_KEY_1=your_key_here
        GEMINI_API_KEY_2=optional_backup_key

Usage (unchanged)::

    from llm_router import generate_ai_response
    response = generate_ai_response("Explain recursion", {"user_name": "Mayank"})

New (Phase 9)::

    from llm_router import llm_router          # singleton facade
    text = llm_router.generate_ai_response(prompt, system_prompt="...", task="reasoning")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv

# Provider platform (lower layer -- no circular import).
from providers import get_registry, TaskType
from providers.gemini_provider import (
    GeminiProvider,
    build_gemini_prompt as _build_gemini_prompt,   # re-exported for compat
    is_real_key as _is_real_key,                    # re-exported for compat
    load_gemini_keys as _load_gemini_keys,          # re-exported for compat
)


# ---------------------------------------------------------------------------
# Environment Setup
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)


# Backward-compatible module-level key list (kept in sync with the provider).
GEMINI_KEYS: list[str] = _load_gemini_keys()


# ---------------------------------------------------------------------------
# Simple-Query Detection (unchanged)
# ---------------------------------------------------------------------------

_SIMPLE_EXACT: set[str] = {
    "hi", "hello", "hey", "yo", "sup", "hii", "hiii",
    "namaste", "salam", "howdy", "wassup", "what's up",
    "thanks", "thank you", "thankyou", "thx", "ty",
    "ok", "okay", "k", "kk", "sure", "yes", "no", "yep", "nope",
    "bye", "goodbye", "good night", "good morning", "good evening",
    "gm", "gn", "good afternoon",
    "hmm", "hm", "ah", "oh", "wow", "lol", "haha", "hehe",
    "nice", "cool", "great", "awesome", "amazing",
}

_SIMPLE_MAX_WORDS = 4

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

    Returns ``True`` when the input exactly matches a known greeting/filler,
    or is very short (<= 4 words) with no complex-signal keywords.
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
# Task Detection (Phase 9 -- picks the right local model)
# ---------------------------------------------------------------------------

_CODING_SIGNALS = {
    "code", "program", "debug", "function", "bug", "error", "fix",
    "python", "javascript", "java", "html", "css", "sql", "regex",
    "compile", "stack trace", "refactor", "unit test", "api",
}
_REASONING_SIGNALS = {
    "why", "explain", "prove", "analyze", "analyse", "reason",
    "compare", "difference", "trade-off", "tradeoff", "evaluate",
    "pros and cons", "logic", "solve",
}
_PLANNING_SIGNALS = {
    "plan", "schedule", "roadmap", "steps", "organize", "organise",
    "strategy", "milestone", "timeline", "break down", "outline",
    "prioritize", "prioritise",
}


def detect_task(user_input: str) -> TaskType:
    """Classify *user_input* into a routing task type (heuristic, cheap)."""
    text = user_input.lower()
    if any(sig in text for sig in _CODING_SIGNALS):
        return TaskType.CODING
    if any(sig in text for sig in _PLANNING_SIGNALS):
        return TaskType.PLANNING
    if any(sig in text for sig in _REASONING_SIGNALS):
        return TaskType.REASONING
    return TaskType.CONVERSATION


# ---------------------------------------------------------------------------
# Legacy Gemini helpers (delegated to the provider -- kept for compat)
# ---------------------------------------------------------------------------

def call_gemini_with_rotation(user_input: str, context: dict[str, Any]) -> str | None:
    """
    Call Google Gemini, rotating through all available keys.

    Returns the response text on success, or ``None`` if every key fails or
    no keys are available.  (Backward-compatible wrapper over GeminiProvider.)
    """
    provider = GeminiProvider()
    if not provider.keys:
        print("  [LLM Router] No valid Gemini keys available.")
        return None
    result = provider.generate(user_input, context=context)
    return result.text if result.ok and result.text else None


# ---------------------------------------------------------------------------
# Local Fallback (unchanged behaviour)
# ---------------------------------------------------------------------------

def _local_response(user_input: str, context: dict[str, Any]) -> str:
    """Generate a response using the offline rule-based response_generator."""
    from response_generator import generate_response
    role = context.get("role", "assistant")
    return generate_response(user_input, role).response


# ---------------------------------------------------------------------------
# Main Entry Point (backward-compatible signature)
# ---------------------------------------------------------------------------

def generate_ai_response(
    user_input: str,
    context: dict[str, Any] | None = None,
    *,
    task: TaskType | str | None = None,
    provider: str | None = None,
) -> str:
    """
    Route *user_input* through the two-tier system.

    1. Simple query  -->  local response (no model call).
    2. Complex query -->  provider registry (Ollama -> Gemini -> local).

    ``task`` and ``provider`` are optional Phase-9 extras; omitting them
    preserves the original behaviour exactly.
    """
    if context is None:
        context = {}

    # -- Tier 1: Simple query --> local response --------------------------
    if is_simple_query(user_input):
        print("  [LLM Router] Simple query --> local response.")
        return _local_response(user_input, context)

    # -- Tier 2: Complex query --> provider registry ----------------------
    routed_task = task or detect_task(user_input)
    print(f"  [LLM Router] Complex query --> registry (task={routed_task}).")
    result = get_registry().generate(
        user_input,
        task=routed_task,
        provider=provider,
        context=context,
    )
    if result.ok and result.text:
        return result.text

    # -- Ultimate fallback ------------------------------------------------
    print("  [LLM Router] Registry produced nothing --> local fallback.")
    return _local_response(user_input, context)


# ---------------------------------------------------------------------------
# Streaming Entry Point (SSE-compatible generator, backward-compatible)
# ---------------------------------------------------------------------------

def generate_ai_response_stream(
    user_input: str,
    context: dict[str, Any] | None = None,
    *,
    task: TaskType | str | None = None,
    provider: str | None = None,
) -> Iterator[str]:
    """
    Stream *user_input* through the two-tier system, yielding text chunks.

    Simple queries yield the full local response as one chunk; complex queries
    stream from the routed provider, falling back to a single local chunk.
    """
    if context is None:
        context = {}

    if is_simple_query(user_input):
        print("  [LLM Router] Simple query --> local response (stream).")
        yield _local_response(user_input, context)
        return

    routed_task = task or detect_task(user_input)
    produced = False
    for chunk in get_registry().generate_stream(
        user_input, task=routed_task, provider=provider, context=context,
    ):
        if chunk:
            produced = True
            yield chunk
    if not produced:
        print("  [LLM Router] Registry stream empty --> local fallback.")
        yield _local_response(user_input, context)


# ---------------------------------------------------------------------------
# Singleton Facade (Phase 9 -- object API used by reflective_cognition)
# ---------------------------------------------------------------------------

class _LLMRouter:
    """Object facade over the module functions and the provider registry."""

    @property
    def registry(self):
        return get_registry()

    def generate_ai_response(
        self,
        user_input: str,
        context: dict[str, Any] | None = None,
        *,
        system_prompt: str | None = None,
        task: TaskType | str | None = None,
        provider: str | None = None,
    ) -> str:
        """
        Generate a response, optionally with an explicit *system_prompt*.

        Previously this call site existed in the codebase but referenced a
        non-existent object and unsupported kwarg (it silently failed).  It is
        now real: with a system prompt we bypass the simple-query shortcut and
        route straight through the registry.
        """
        if context is None:
            context = {}
        if system_prompt is None and is_simple_query(user_input):
            return _local_response(user_input, context)
        routed_task = task or detect_task(user_input)
        result = get_registry().generate(
            user_input,
            task=routed_task,
            provider=provider,
            system_prompt=system_prompt,
            context=context,
        )
        if result.ok and result.text:
            return result.text
        return _local_response(user_input, context)

    def generate_stream(self, *args, **kwargs) -> Iterator[str]:
        return generate_ai_response_stream(*args, **kwargs)

    def explain_routing(self, user_input: str) -> dict[str, Any]:
        return explain_routing(user_input)

    def health(self, *, force: bool = False) -> dict[str, Any]:
        return get_registry().health_report(force=force)


#: Module-level singleton (``from llm_router import llm_router``).
llm_router = _LLMRouter()


# ---------------------------------------------------------------------------
# Diagnostics (backward-compatible + enriched)
# ---------------------------------------------------------------------------

def get_api_status() -> dict[str, str]:
    """
    Return Gemini key availability (legacy key preserved) plus a summary of
    all providers' health.
    """
    keys = _load_gemini_keys()
    if not keys:
        gemini = "NO_KEYS"
    else:
        count = len(keys)
        gemini = f"LIVE ({count} key{'s' if count > 1 else ''})"

    status: dict[str, str] = {"gemini": gemini}
    try:
        for name, report in get_registry().health_report().items():
            status[name] = report["status"].upper()
    except Exception:
        pass
    return status


def explain_routing(user_input: str) -> dict[str, Any]:
    """
    Show how *user_input* would be routed without calling any model.

    Backward-compatible keys ``tier``, ``reason`` and ``input_preview`` are
    preserved; Phase-9 fields ``provider``, ``model`` and ``task`` are added.
    """
    if is_simple_query(user_input):
        return {
            "tier": "local",
            "reason": "simple_query",
            "input_preview": user_input[:80],
            "provider": "local",
            "model": "rule-based",
            "task": "conversation",
        }

    task = detect_task(user_input)
    decision = get_registry().route(task)
    return {
        # legacy label: complex queries historically reported "gemini"
        "tier": "gemini",
        "reason": decision.reason,
        "input_preview": user_input[:80],
        "provider": decision.provider,
        "model": decision.model,
        "task": task.value,
    }


# ---------------------------------------------------------------------------
# Built-in Tests / Demo
# ---------------------------------------------------------------------------

def _run_tests() -> None:  # pragma: no cover - manual demo
    """Demonstrate routing logic and provider status."""
    test_cases = [
        ("hi", "LOCAL"), ("hello", "LOCAL"), ("thanks", "LOCAL"),
        ("ok", "LOCAL"), ("good morning", "LOCAL"), ("lol", "LOCAL"),
        ("how are you", "LOCAL"),
        ("Write a Python function for binary search", "GEMINI"),
        ("Explain why the sky is blue", "GEMINI"),
        ("What is machine learning?", "GEMINI"),
        ("Teach me about recursion step by step", "GEMINI"),
        ("What's the weather like today?", "GEMINI"),
    ]

    status = get_api_status()
    print("=" * 70)
    print("  AISHA -- LLM Router (Provider Platform) -- Test Suite")
    print("=" * 70)
    print(f"\n  .env loaded from : {_ENV_PATH}")
    print(f"  Provider status  : {status}")
    print()

    context = {"user_name": "Mayank", "emotion": "curious", "role": "assistant"}
    for user_input, expected_tier in test_cases:
        routing = explain_routing(user_input)
        actual_tier = routing["tier"].upper()
        match = "OK" if actual_tier == expected_tier else "MISMATCH"
        print(f"  Input    : \"{user_input}\"")
        print(f"  Expected : {expected_tier}  Actual: {actual_tier}  [{match}]")
        print(f"  Route    : {routing['provider']}/{routing['model']} ({routing['reason']})")
        response = generate_ai_response(user_input, context)
        print(f"  Response : {response[:120]}...")
        print("  " + "-" * 66)
    print("\n  All tests completed.")
    print("=" * 70)


if __name__ == "__main__":
    _run_tests()
