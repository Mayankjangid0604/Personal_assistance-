"""
ProviderService for Aisha AI Assistant (Phase 11).

Thin facade over :mod:`providers` (Phase 9).  This is the surface the REST
API and Electron Provider Manager should call -- it never talks to Ollama or
Gemini directly, and it never changes routing behaviour; it just exposes the
registry through the service-layer's uniform ``ServiceResult``/``health()``
contract.
"""

from __future__ import annotations

from typing import Any, Iterator

from .base import BaseService, ServiceHealth, ServiceResult, ServiceState


class ProviderService(BaseService):
    """Facade over the provider registry (:mod:`providers`)."""

    name = "provider"

    def __init__(self, registry: Any | None = None) -> None:
        self._registry = registry  # lazily resolved if None

    @property
    def registry(self) -> Any:
        if self._registry is None:
            from providers import get_registry
            self._registry = get_registry()
        return self._registry

    # -- Generation -----------------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        task: str = "general",
        provider: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ServiceResult:
        try:
            resp = self.registry.generate(
                prompt, task=task, provider=provider, model=model,
                system_prompt=system_prompt, context=context,
            )
        except Exception as exc:  # noqa: BLE001
            return self._err(str(exc), action="generate")
        if resp.ok:
            return self._ok(resp.text, action="generate", provider=resp.provider,
                             model=resp.model, latency_ms=resp.latency_ms)
        return self._err(resp.error or "generation failed", action="generate")

    def stream(
        self,
        prompt: str,
        *,
        task: str = "general",
        provider: str | None = None,
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        yield from self.registry.generate_stream(
            prompt, task=task, provider=provider, model=model, context=context,
        )

    # -- Discovery / control ----------------------------------------------------

    def route(self, task: str = "general") -> ServiceResult:
        return self._call("route", self.registry.route, task)

    def set_override(self, provider: str | None) -> ServiceResult:
        return self._call("set_override", self.registry.set_override, provider)

    def capability_registry(self) -> ServiceResult:
        return self._call("capability_registry", self.registry.capability_registry)

    def latency_report(self) -> ServiceResult:
        return self._call("latency_report", self.registry.latency_report)

    def provider_health(self, *, force: bool = False) -> ServiceResult:
        return self._call("provider_health", self.registry.health_report, force=force)

    def names(self) -> list[str]:
        try:
            return self.registry.names()
        except Exception:
            return []

    # -- Health -----------------------------------------------------------------

    def health(self) -> ServiceHealth:
        try:
            names = self.registry.names()
        except Exception as exc:  # noqa: BLE001
            return ServiceHealth(self.name, ServiceState.UNAVAILABLE, str(exc))
        if not names:
            return ServiceHealth(self.name, ServiceState.UNAVAILABLE, "no providers registered")
        healthy = 0
        for n in names:
            try:
                if self.registry.is_healthy(n):
                    healthy += 1
            except Exception:
                continue
        state = ServiceState.HEALTHY if healthy else ServiceState.DEGRADED
        return ServiceHealth(self.name, state, f"{healthy}/{len(names)} providers healthy")
