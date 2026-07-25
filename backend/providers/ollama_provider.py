"""
Ollama Local Provider for Aisha AI Assistant (Phase 9).

Talks to a locally running Ollama daemon over HTTP using only the Python
standard library (``urllib``) -- no new runtime dependencies.  This is the
heart of the local-first platform: when Ollama is up, Aisha routes coding,
reasoning, planning and conversation to the appropriate on-device model.

Testability
-----------
All network I/O goes through a small :class:`Transport` object.  Tests inject
a fake transport, so the full provider (health, model discovery, generation,
streaming, routing) is verified without a live daemon.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Iterator, Protocol

from . import config as provider_config
from .base import (
    Capability,
    HealthReport,
    LLMProvider,
    ProviderStatus,
)


# ---------------------------------------------------------------------------
# Transport abstraction
# ---------------------------------------------------------------------------

class Transport(Protocol):
    """Minimal HTTP surface the provider needs.  Injectable for tests."""

    def get(self, path: str) -> dict[str, Any]: ...

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def post_stream(self, path: str, payload: dict[str, Any]) -> Iterator[dict[str, Any]]: ...


class UrllibTransport:
    """Default transport backed by :mod:`urllib` (stdlib only)."""

    def __init__(self, host: str, timeout: float) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.host}{path}"

    def get(self, path: str) -> dict[str, Any]:
        import urllib.request

        req = urllib.request.Request(self._url(path), method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        import urllib.request

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url(path), data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post_stream(self, path: str, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        import urllib.request

        data = json.dumps({**payload, "stream": True}).encode("utf-8")
        req = urllib.request.Request(
            self._url(path), data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            for line in resp:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    """Local models served by an Ollama daemon."""

    name = "ollama"
    priority = 10          # most preferred when healthy (local-first)
    local = True

    def __init__(
        self,
        host: str | None = None,
        timeout: float | None = None,
        transport: Transport | None = None,
        model_capabilities: dict[str, list[Capability]] | None = None,
    ) -> None:
        super().__init__()
        settings = provider_config.ollama_settings()
        self.host = host or settings.get("host", "http://127.0.0.1:11434")
        self.timeout = timeout if timeout is not None else settings.get("timeout", 60)
        self._transport = transport
        # model -> [capabilities]; defaults to the configured catalogue.
        self._model_caps = model_capabilities or provider_config.ollama_model_capabilities()

    # -- Transport (lazy real transport unless one was injected) ----------

    @property
    def transport(self) -> Transport:
        if self._transport is None:
            self._transport = UrllibTransport(self.host, self.timeout)
        return self._transport

    # -- Introspection ----------------------------------------------------

    def capabilities(self) -> set[Capability]:
        caps: set[Capability] = set()
        for cap_list in self._model_caps.values():
            caps.update(cap_list)
        return caps or {Capability.GENERAL}

    def models(self) -> list[str]:
        return list(self._model_caps.keys())

    def installed_models(self) -> list[str]:
        """Query the daemon for models actually pulled locally."""
        try:
            data = self.transport.get("/api/tags")
        except Exception:
            return []
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]

    def model_for(self, capability: Capability) -> str | None:
        """First catalogue model that advertises *capability*."""
        for model, caps in self._model_caps.items():
            if capability in caps:
                return model
        models = self.models()
        return models[0] if models else None

    # -- Health -----------------------------------------------------------

    def check_health(self) -> HealthReport:
        try:
            data = self.transport.get("/api/tags")
        except Exception as exc:  # noqa: BLE001
            return HealthReport(
                provider=self.name,
                status=ProviderStatus.UNAVAILABLE,
                detail=f"daemon unreachable: {exc}",
            )
        installed = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        if not installed:
            return HealthReport(
                provider=self.name,
                status=ProviderStatus.UNAVAILABLE,
                detail="daemon reachable but no models installed",
            )
        # Degraded if some catalogue models aren't pulled yet.
        catalogue = set(self.models())
        present = catalogue & set(installed)
        status = ProviderStatus.HEALTHY if present else ProviderStatus.DEGRADED
        return HealthReport(
            provider=self.name,
            status=status,
            detail=f"{len(present)}/{len(catalogue)} catalogue models installed",
            models=sorted(present) or installed,
            avg_latency_ms=self.latency.avg,
        )

    # -- Generation -------------------------------------------------------

    def _generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        chosen = model or self.model_for(Capability.GENERAL)
        if not chosen:
            raise RuntimeError("no Ollama model available")
        payload: dict[str, Any] = {"model": chosen, "prompt": prompt, "stream": False}
        if system_prompt:
            payload["system"] = system_prompt
        data = self.transport.post("/api/generate", payload)
        return (data.get("response") or "").strip()

    def generate_stream(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        chosen = model or self.model_for(Capability.GENERAL)
        if not chosen:
            return
        payload: dict[str, Any] = {"model": chosen, "prompt": prompt}
        if system_prompt:
            payload["system"] = system_prompt
        try:
            for chunk in self.transport.post_stream("/api/generate", payload):
                piece = chunk.get("response")
                if piece:
                    yield piece
                if chunk.get("done"):
                    return
        except Exception:  # noqa: BLE001
            return
