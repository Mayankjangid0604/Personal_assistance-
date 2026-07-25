"""
LLM Provider Interface for Aisha AI Assistant (Phase 9 -- Local LLM Platform).

Defines the provider abstraction that decouples Aisha's brain from any
single model vendor.  Every concrete provider (Ollama, Gemini, the local
rule-based generator, and any future backend) implements :class:`LLMProvider`.

Design goals
------------
* **Never hardcode providers.**  The brain talks to the registry, the
  registry talks to providers through this interface.
* **Local-first.**  Providers advertise their capabilities and health; the
  registry prefers healthy local models and falls back to the cloud.
* **Observable.**  Every provider tracks call latency so routing decisions
  can be data-driven.

Nothing here performs network I/O or imports heavy dependencies -- concrete
providers do that lazily so importing this module is always cheap and safe.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Iterator


# ---------------------------------------------------------------------------
# Capabilities & Task Types
# ---------------------------------------------------------------------------

class Capability(str, Enum):
    """What a provider/model is good at.  Used for capability-based routing."""

    CODING = "coding"
    REASONING = "reasoning"
    PLANNING = "planning"
    CONVERSATION = "conversation"
    GENERAL = "general"
    STREAMING = "streaming"
    VISION = "vision"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class TaskType(str, Enum):
    """Kind of work a request represents.  Maps onto a preferred capability."""

    CODING = "coding"
    REASONING = "reasoning"
    PLANNING = "planning"
    CONVERSATION = "conversation"
    GENERAL = "general"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class ProviderStatus(str, Enum):
    """Health state of a provider."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------

@dataclass
class ProviderResponse:
    """Result of a (non-streaming) generation call."""

    text: str
    provider: str
    model: str | None = None
    latency_ms: float = 0.0
    ok: bool = True
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def failure(cls, provider: str, error: str, model: str | None = None) -> "ProviderResponse":
        """Build a failed response object (never raises)."""
        return cls(text="", provider=provider, model=model, ok=False, error=error)


@dataclass
class HealthReport:
    """Snapshot of a provider's availability."""

    provider: str
    status: ProviderStatus
    detail: str = ""
    models: list[str] = field(default_factory=list)
    avg_latency_ms: float = 0.0
    checked_at: float = field(default_factory=time.time)

    @property
    def available(self) -> bool:
        return self.status in (ProviderStatus.HEALTHY, ProviderStatus.DEGRADED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status.value,
            "detail": self.detail,
            "models": list(self.models),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "available": self.available,
            "checked_at": self.checked_at,
        }


# ---------------------------------------------------------------------------
# Latency Tracking
# ---------------------------------------------------------------------------

class LatencyTracker:
    """Rolling latency statistics for a provider (in-memory, thread-light)."""

    def __init__(self, window: int = 50) -> None:
        self._window = window
        self._samples: list[float] = []

    def record(self, ms: float) -> None:
        self._samples.append(float(ms))
        if len(self._samples) > self._window:
            self._samples = self._samples[-self._window:]

    @property
    def count(self) -> int:
        return len(self._samples)

    @property
    def avg(self) -> float:
        return sum(self._samples) / len(self._samples) if self._samples else 0.0

    @property
    def p95(self) -> float:
        if not self._samples:
            return 0.0
        ordered = sorted(self._samples)
        idx = max(0, int(round(0.95 * (len(ordered) - 1))))
        return ordered[idx]

    def stats(self) -> dict[str, float]:
        return {
            "count": self.count,
            "avg_ms": round(self.avg, 2),
            "p95_ms": round(self.p95, 2),
        }

    def reset(self) -> None:
        self._samples.clear()


# ---------------------------------------------------------------------------
# Provider Interface
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """
    Abstract base every LLM backend implements.

    Subclasses must define :attr:`name` and implement :meth:`_generate`,
    :meth:`capabilities`, :meth:`models`, and :meth:`check_health`.  Latency
    tracking and the public :meth:`generate` wrapper are provided here so
    every provider records timing consistently.
    """

    #: Stable identifier (e.g. ``"ollama"``, ``"gemini"``, ``"local"``).
    name: str = "provider"

    #: Lower number = higher preference when capabilities tie.
    priority: int = 100

    #: True for on-device providers (preferred in local-first routing).
    local: bool = False

    def __init__(self) -> None:
        self.latency = LatencyTracker()
        self._last_status: ProviderStatus = ProviderStatus.UNKNOWN

    # -- Introspection ----------------------------------------------------

    @abstractmethod
    def capabilities(self) -> set[Capability]:
        """Return the set of capabilities this provider offers."""

    @abstractmethod
    def models(self) -> list[str]:
        """Return the model identifiers this provider can serve."""

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities()

    def model_for(self, capability: Capability) -> str | None:
        """
        Return the preferred model for *capability*, or ``None``.

        Base implementation returns the first advertised model; providers
        with per-capability model maps override this.
        """
        models = self.models()
        return models[0] if models else None

    # -- Health -----------------------------------------------------------

    @abstractmethod
    def check_health(self) -> HealthReport:
        """Probe the backend and return a fresh :class:`HealthReport`."""

    def is_available(self) -> bool:
        """Convenience wrapper around :meth:`check_health`."""
        try:
            return self.check_health().available
        except Exception:
            return False

    # -- Generation -------------------------------------------------------

    @abstractmethod
    def _generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Provider-specific generation.  May raise on failure."""

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """
        Public generation entry point.  Times the call, records latency, and
        wraps the result (or failure) in a :class:`ProviderResponse` -- never
        raises.
        """
        start = time.perf_counter()
        try:
            text = self._generate(
                prompt,
                system_prompt=system_prompt,
                model=model,
                context=context,
            )
            elapsed = (time.perf_counter() - start) * 1000.0
            self.latency.record(elapsed)
            self._last_status = ProviderStatus.HEALTHY
            return ProviderResponse(
                text=(text or "").strip(),
                provider=self.name,
                model=model or self.model_for(Capability.GENERAL),
                latency_ms=round(elapsed, 2),
                ok=True,
            )
        except Exception as exc:  # noqa: BLE001 - providers never crash callers
            elapsed = (time.perf_counter() - start) * 1000.0
            self.latency.record(elapsed)
            self._last_status = ProviderStatus.DEGRADED
            return ProviderResponse.failure(self.name, str(exc), model=model)

    def generate_stream(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        """
        Stream text chunks.  Default implementation yields the full
        non-streaming result as a single chunk; providers with native
        streaming override this.
        """
        result = self.generate(
            prompt,
            system_prompt=system_prompt,
            model=model,
            context=context,
        )
        if result.ok and result.text:
            yield result.text

    # -- Repr -------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover - trivial
        caps = ",".join(sorted(c.value for c in self.capabilities()))
        return f"<{self.__class__.__name__} name={self.name!r} caps={caps}>"


def coerce_capability(value: Capability | str) -> Capability:
    """Accept a Capability or its string name and return a Capability."""
    if isinstance(value, Capability):
        return value
    return Capability(str(value).lower())


def coerce_task(value: TaskType | str) -> TaskType:
    """Accept a TaskType or its string name and return a TaskType."""
    if isinstance(value, TaskType):
        return value
    return TaskType(str(value).lower())


def _iter_chunks(chunks: Iterable[str]) -> Iterator[str]:  # pragma: no cover
    for chunk in chunks:
        if chunk:
            yield chunk
