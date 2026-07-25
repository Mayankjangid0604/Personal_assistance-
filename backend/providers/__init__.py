"""
Aisha Provider Platform (Phase 9 -- Local LLM Platform).

A vendor-neutral abstraction over language-model backends.  The rest of Aisha
never imports a concrete provider; it talks to the registry, which routes to
Ollama (local), Gemini (cloud fallback), or the offline rule-based generator
based on capability, health and latency -- all driven by config.

Quick start::

    from providers import get_registry, TaskType

    reg = get_registry()
    resp = reg.generate("Write a binary search in Python", task=TaskType.CODING)
    print(resp.text, "via", resp.provider)
"""

from __future__ import annotations

from .base import (
    Capability,
    HealthReport,
    LatencyTracker,
    LLMProvider,
    ProviderResponse,
    ProviderStatus,
    TaskType,
    coerce_capability,
    coerce_task,
)
from .config import (
    DEFAULT_CONFIG,
    get_config,
    load_config,
    reset_config,
    route_for_task,
)
from .local_provider import LocalProvider
from .gemini_provider import GeminiProvider
from .ollama_provider import OllamaProvider, UrllibTransport
from .registry import (
    ProviderRegistry,
    RouteDecision,
    build_default_registry,
    get_registry,
    reset_registry,
)

__all__ = [
    # base
    "Capability",
    "TaskType",
    "ProviderStatus",
    "ProviderResponse",
    "HealthReport",
    "LatencyTracker",
    "LLMProvider",
    "coerce_capability",
    "coerce_task",
    # config
    "DEFAULT_CONFIG",
    "get_config",
    "load_config",
    "reset_config",
    "route_for_task",
    # providers
    "LocalProvider",
    "GeminiProvider",
    "OllamaProvider",
    "UrllibTransport",
    # registry
    "ProviderRegistry",
    "RouteDecision",
    "build_default_registry",
    "get_registry",
    "reset_registry",
]
