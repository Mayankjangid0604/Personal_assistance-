"""
Local Rule-Based Provider for Aisha AI Assistant (Phase 9).

Wraps the existing offline :mod:`response_generator` as a first-class
provider.  It has no dependencies, never fails, and is therefore the
guaranteed last-resort in every routing decision -- preserving Aisha's
original "always answers something" behaviour.
"""

from __future__ import annotations

from typing import Any

from .base import (
    Capability,
    HealthReport,
    LLMProvider,
    ProviderStatus,
)


class LocalProvider(LLMProvider):
    """Offline, instant, rule-based responses.  Always healthy."""

    name = "local"
    priority = 90          # low preference, but never unavailable
    local = True

    def capabilities(self) -> set[Capability]:
        return {Capability.CONVERSATION, Capability.GENERAL}

    def models(self) -> list[str]:
        return ["rule-based"]

    def check_health(self) -> HealthReport:
        return HealthReport(
            provider=self.name,
            status=ProviderStatus.HEALTHY,
            detail="offline rule-based generator",
            models=self.models(),
            avg_latency_ms=self.latency.avg,
        )

    def _generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        # Imported lazily so this module stays import-cheap.
        from response_generator import generate_response

        role = "assistant"
        if context:
            role = context.get("role", role)
        return generate_response(prompt, role).response
