"""
Provider Registry & Router for Aisha AI Assistant (Phase 9).

The single place the rest of the app asks "who should answer this?".  The
registry:

* holds the set of registered providers (no provider is named in code -- they
  are registered by :func:`build_default_registry` from config),
* maintains a **capability registry** (capability -> providers that serve it),
* performs **automatic provider selection** by task type, honouring a
  **manual override**, provider health, latency, and priority,
* exposes **health monitoring** and **latency tracking** for the whole fleet.

Selection order for a task
--------------------------
1. Manual override (explicit provider/model) if healthy.
2. The config ``task_routing`` hint's provider, if healthy.
3. Any other healthy provider that advertises the task's capability,
   ordered by (local-first, priority, avg latency).
4. The configured cloud fallback provider, if healthy.
5. The last-resort local provider (always available).
"""

from __future__ import annotations

import time
from typing import Any, Iterator

from . import config as provider_config
from .base import (
    Capability,
    HealthReport,
    LLMProvider,
    ProviderResponse,
    ProviderStatus,
    TaskType,
    coerce_capability,
    coerce_task,
)


# ---------------------------------------------------------------------------
# Task -> capability mapping
# ---------------------------------------------------------------------------

_TASK_CAPABILITY = {
    TaskType.CODING: Capability.CODING,
    TaskType.REASONING: Capability.REASONING,
    TaskType.PLANNING: Capability.PLANNING,
    TaskType.CONVERSATION: Capability.CONVERSATION,
    TaskType.GENERAL: Capability.GENERAL,
}


class RouteDecision:
    """Explains how a request was routed (for observability / UI)."""

    def __init__(self, provider: str, model: str | None, reason: str, task: str) -> None:
        self.provider = provider
        self.model = model
        self.reason = reason
        self.task = task

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "reason": self.reason,
            "task": self.task,
        }

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<RouteDecision provider={self.provider} model={self.model} reason={self.reason}>"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ProviderRegistry:
    """Holds providers and routes requests.  No provider names are hardcoded."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._override: str | None = None
        self._health_cache: dict[str, HealthReport] = {}
        self._health_ttl = 15.0  # seconds

    # -- Registration -----------------------------------------------------

    def register(self, provider: LLMProvider) -> LLMProvider:
        self._providers[provider.name] = provider
        return provider

    def unregister(self, name: str) -> None:
        self._providers.pop(name, None)
        self._health_cache.pop(name, None)

    def get(self, name: str) -> LLMProvider | None:
        return self._providers.get(name)

    def all(self) -> list[LLMProvider]:
        return list(self._providers.values())

    def names(self) -> list[str]:
        return list(self._providers.keys())

    def clear(self) -> None:
        self._providers.clear()
        self._health_cache.clear()
        self._override = None

    # -- Manual override --------------------------------------------------

    def set_override(self, name: str | None) -> None:
        """Force a specific provider (or clear with ``None``)."""
        if name is not None and name not in self._providers:
            raise ValueError(f"unknown provider: {name!r}")
        self._override = name

    @property
    def override(self) -> str | None:
        return self._override

    # -- Capability registry ---------------------------------------------

    def providers_for(self, capability: Capability | str) -> list[LLMProvider]:
        cap = coerce_capability(capability)
        matches = [p for p in self._providers.values() if p.supports(cap)]
        return sorted(matches, key=lambda p: (not p.local, p.priority, p.latency.avg))

    def capability_registry(self) -> dict[str, list[str]]:
        """Return ``{capability: [provider names]}`` across the fleet."""
        out: dict[str, list[str]] = {}
        for cap in Capability:
            provs = [p.name for p in self.providers_for(cap)]
            if provs:
                out[cap.value] = provs
        return out

    # -- Health -----------------------------------------------------------

    def health(self, name: str, *, force: bool = False) -> HealthReport:
        provider = self._providers.get(name)
        if provider is None:
            return HealthReport(provider=name, status=ProviderStatus.UNKNOWN, detail="not registered")
        cached = self._health_cache.get(name)
        if cached and not force and (time.time() - cached.checked_at) < self._health_ttl:
            return cached
        report = provider.check_health()
        self._health_cache[name] = report
        return report

    def is_healthy(self, name: str, *, force: bool = False) -> bool:
        return self.health(name, force=force).available

    def health_report(self, *, force: bool = False) -> dict[str, dict[str, Any]]:
        """Health snapshot for every provider (for a status dashboard)."""
        return {name: self.health(name, force=force).to_dict() for name in self._providers}

    def latency_report(self) -> dict[str, dict[str, float]]:
        return {name: p.latency.stats() for name, p in self._providers.items()}

    # -- Routing ----------------------------------------------------------

    def route(
        self,
        task: TaskType | str = TaskType.GENERAL,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> RouteDecision:
        """
        Decide which provider/model should serve *task* without generating.

        Deterministic and side-effect free (apart from cached health probes),
        so it doubles as the "explain routing" primitive for the UI.
        """
        task = coerce_task(task)
        capability = _TASK_CAPABILITY.get(task, Capability.GENERAL)

        # 1. Manual override (call arg beats registry-level override).
        forced = provider or self._override
        if forced:
            p = self._providers.get(forced)
            if p is not None and self.is_healthy(forced):
                chosen_model = model or p.model_for(capability)
                return RouteDecision(forced, chosen_model, "manual_override", task.value)

        # 2. Config task-routing hint.
        hint = provider_config.route_for_task(task)
        hint_provider = hint.get("provider")
        if hint_provider and hint_provider in self._providers and self.is_healthy(hint_provider):
            p = self._providers[hint_provider]
            if p.supports(capability):
                chosen_model = model or hint.get("model") or p.model_for(capability)
                return RouteDecision(hint_provider, chosen_model, "task_routing", task.value)

        # 3. Any healthy provider advertising the capability.
        for p in self.providers_for(capability):
            if self.is_healthy(p.name):
                return RouteDecision(p.name, model or p.model_for(capability), "capability_match", task.value)

        # 4. Configured cloud fallback.
        fb = provider_config.fallback_provider()
        if fb in self._providers and self.is_healthy(fb):
            p = self._providers[fb]
            return RouteDecision(fb, model or p.model_for(capability), "fallback", task.value)

        # 5. Last-resort local provider (always available).
        lr = provider_config.last_resort_provider()
        if lr in self._providers:
            p = self._providers[lr]
            return RouteDecision(lr, model or p.model_for(capability), "last_resort", task.value)

        # Nothing registered at all.
        return RouteDecision("none", None, "no_provider", task.value)

    # -- Generation -------------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        task: TaskType | str = TaskType.GENERAL,
        provider: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """
        Route and generate.  If the chosen provider fails at call time, fall
        through to the cloud fallback and then the last-resort provider so a
        caller ALWAYS gets a usable response (never raises).
        """
        decision = self.route(task, provider=provider, model=model)
        tried: list[str] = []

        # Build the ordered attempt chain: chosen -> fallback -> last resort.
        chain: list[tuple[str, str | None]] = [(decision.provider, decision.model)]
        fb = provider_config.fallback_provider()
        lr = provider_config.last_resort_provider()
        for name in (fb, lr):
            if name in self._providers and name not in [c[0] for c in chain]:
                chain.append((name, None))

        last: ProviderResponse | None = None
        for name, chosen_model in chain:
            p = self._providers.get(name)
            if p is None:
                continue
            tried.append(name)
            result = p.generate(
                prompt,
                system_prompt=system_prompt,
                model=chosen_model,
                context=context,
            )
            if result.ok and result.text:
                result.meta["route"] = decision.to_dict()
                result.meta["tried"] = tried
                return result
            last = result

        if last is not None:
            last.meta["route"] = decision.to_dict()
            last.meta["tried"] = tried
            return last
        return ProviderResponse.failure("registry", "no providers registered")

    def generate_stream(
        self,
        prompt: str,
        *,
        task: TaskType | str = TaskType.GENERAL,
        provider: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        """Stream from the chosen provider, falling back to last-resort text."""
        decision = self.route(task, provider=provider, model=model)
        p = self._providers.get(decision.provider)
        produced = False
        if p is not None:
            for chunk in p.generate_stream(
                prompt, system_prompt=system_prompt,
                model=decision.model, context=context,
            ):
                produced = True
                yield chunk
        if produced:
            return
        # Nothing streamed -> guarantee a response from the last resort.
        lr = provider_config.last_resort_provider()
        lp = self._providers.get(lr)
        if lp is not None:
            result = lp.generate(prompt, system_prompt=system_prompt, context=context)
            if result.text:
                yield result.text


# ---------------------------------------------------------------------------
# Default registry builder
# ---------------------------------------------------------------------------

_REGISTRY: ProviderRegistry | None = None


def build_default_registry() -> ProviderRegistry:
    """
    Construct a registry from config's ``provider_order``.

    Providers are imported and instantiated by name from a small dispatch
    table -- adding a provider is a config + table entry, never a change to
    routing logic.
    """
    from .local_provider import LocalProvider
    from .gemini_provider import GeminiProvider
    from .ollama_provider import OllamaProvider

    builders = {
        "local": LocalProvider,
        "gemini": GeminiProvider,
        "ollama": OllamaProvider,
    }

    registry = ProviderRegistry()
    for name in provider_config.provider_order():
        builder = builders.get(name)
        if builder is not None:
            try:
                registry.register(builder())
            except Exception:
                # A provider that can't even construct is simply skipped.
                continue
    # Guarantee the last-resort provider is always present.
    lr = provider_config.last_resort_provider()
    if registry.get(lr) is None and lr in builders:
        registry.register(builders[lr]())
    return registry


def get_registry() -> ProviderRegistry:
    """Return the process-wide registry, building it on first use."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_default_registry()
    return _REGISTRY


def reset_registry() -> None:
    """Drop the cached registry (tests / config reloads)."""
    global _REGISTRY
    _REGISTRY = None
