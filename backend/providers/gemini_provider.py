"""
Gemini Cloud Provider for Aisha AI Assistant (Phase 9).

Wraps Google Gemini with the multi-key rotation Aisha already used, exposed
through the :class:`LLMProvider` interface.  This is the cloud fallback in a
local-first deployment: preferred only when no local model is healthy, or
when explicitly requested.

The key-loading and prompt-building helpers live here (the lowest layer) so
``llm_router`` can re-export them for backward compatibility without a
circular import.
"""

from __future__ import annotations

import os
from typing import Any, Iterator

from .base import (
    Capability,
    HealthReport,
    LLMProvider,
    ProviderStatus,
)

# Default cloud model.  Config-overridable via GEMINI_MODEL.
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


# ---------------------------------------------------------------------------
# Key loading (multi-key, placeholder-safe)
# ---------------------------------------------------------------------------

def is_real_key(key: str | None) -> bool:
    """Return True only if *key* is set and isn't a placeholder."""
    if not key:
        return False
    placeholders = {"", "your_gemini_key_here", "YOUR_KEY_HERE", "sk-xxx"}
    return key.strip() not in placeholders


def load_gemini_keys(max_slots: int = 10) -> list[str]:
    """
    Load all valid Gemini API keys from the environment.

    Checks ``GEMINI_API_KEY`` (legacy) and ``GEMINI_API_KEY_1``..
    ``GEMINI_API_KEY_{max_slots}``.  Returns a de-duplicated list.
    """
    seen: set[str] = set()
    keys: list[str] = []

    legacy = os.environ.get("GEMINI_API_KEY")
    if is_real_key(legacy) and legacy.strip() not in seen:
        keys.append(legacy.strip())
        seen.add(legacy.strip())

    for i in range(1, max_slots + 1):
        val = os.environ.get(f"GEMINI_API_KEY_{i}")
        if is_real_key(val) and val.strip() not in seen:
            keys.append(val.strip())
            seen.add(val.strip())

    return keys


# ---------------------------------------------------------------------------
# Prompt builder (identical to the legacy router prompt)
# ---------------------------------------------------------------------------

def build_gemini_prompt(user_input: str, context: dict[str, Any] | None) -> str:
    """Build a single prompt string for Gemini from user input + context."""
    context = context or {}
    name = context.get("user_name", "User")
    emotion = context.get("emotion", "neutral")
    role = context.get("role", "assistant")

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
# Provider
# ---------------------------------------------------------------------------

class GeminiProvider(LLMProvider):
    """Google Gemini with API-key rotation and native streaming."""

    name = "gemini"
    priority = 50          # preferred over local, below healthy Ollama
    local = False

    def __init__(self, keys: list[str] | None = None, model: str | None = None) -> None:
        super().__init__()
        # Keys are loaded lazily/refreshably; an explicit list is for tests.
        self._explicit_keys = keys
        self.model_name = model or DEFAULT_GEMINI_MODEL

    # -- Keys -------------------------------------------------------------

    @property
    def keys(self) -> list[str]:
        if self._explicit_keys is not None:
            return self._explicit_keys
        return load_gemini_keys()

    # -- Introspection ----------------------------------------------------

    def capabilities(self) -> set[Capability]:
        return {
            Capability.CODING,
            Capability.REASONING,
            Capability.PLANNING,
            Capability.CONVERSATION,
            Capability.GENERAL,
            Capability.STREAMING,
        }

    def models(self) -> list[str]:
        return [self.model_name]

    # -- Health -----------------------------------------------------------

    def check_health(self) -> HealthReport:
        keys = self.keys
        if not keys:
            return HealthReport(
                provider=self.name,
                status=ProviderStatus.UNAVAILABLE,
                detail="no valid Gemini API keys",
            )
        try:
            import google.generativeai  # noqa: F401
        except ImportError:
            return HealthReport(
                provider=self.name,
                status=ProviderStatus.UNAVAILABLE,
                detail="google-generativeai not installed",
                models=self.models(),
            )
        return HealthReport(
            provider=self.name,
            status=ProviderStatus.HEALTHY,
            detail=f"{len(keys)} key(s) available",
            models=self.models(),
            avg_latency_ms=self.latency.avg,
        )

    # -- Generation -------------------------------------------------------

    def _resolve_prompt(self, prompt: str, system_prompt: str | None, context: dict | None) -> str:
        if system_prompt:
            return f"{system_prompt}\n\nUser: {prompt}\nAisha:"
        return build_gemini_prompt(prompt, context)

    def _generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        keys = self.keys
        if not keys:
            raise RuntimeError("no Gemini keys")

        import google.generativeai as genai

        full_prompt = self._resolve_prompt(prompt, system_prompt, context)
        last_error: Exception | None = None
        for idx, key in enumerate(keys):
            try:
                genai.configure(api_key=key)
                gm = genai.GenerativeModel(model or self.model_name)
                response = gm.generate_content(full_prompt)
                return response.text.strip()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        raise RuntimeError(f"all Gemini keys failed: {last_error}")

    def generate_stream(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        keys = self.keys
        if not keys:
            return
        try:
            import google.generativeai as genai
        except ImportError:
            return

        full_prompt = self._resolve_prompt(prompt, system_prompt, context)
        for key in keys:
            try:
                genai.configure(api_key=key)
                gm = genai.GenerativeModel(model or self.model_name)
                response = gm.generate_content(full_prompt, stream=True)
                for chunk in response:
                    if getattr(chunk, "text", None):
                        yield chunk.text
                return
            except Exception:  # noqa: BLE001
                continue
