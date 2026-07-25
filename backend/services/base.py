"""
Service Layer Foundation for Aisha AI Assistant (Phase 11 -- Production
Integration Layer).

Every service (:class:`ProviderService`, :class:`PluginService`,
:class:`MemoryService`, ...) is a thin, dependency-injected facade over an
existing subsystem.  Services exist so *new* backend code has one obvious,
testable seam to call through instead of importing subsystem internals
directly -- the same role :mod:`providers` plays for LLM backends and
:mod:`plugins` plays for extensions.

Design rules (apply to every service in this package)
-------------------------------------------------------
1. **Constructor injection.**  Every service accepts its wrapped dependency
   as an optional constructor argument.  When omitted, it lazily imports and
   constructs the real default -- so importing the service module is always
   cheap, and tests can inject a fake with zero patching.
2. **Never raise to the caller.**  Public methods catch subsystem exceptions
   and return a :class:`ServiceResult`, mirroring ``PluginResult`` and
   ``ProviderResponse``.
3. **``health()`` is mandatory.**  Every service reports its own health so a
   future Performance/Logs dashboard has one uniform place to query.

Scope note
----------
This is an *additive* facade layer.  Existing modules that already import
subsystems directly (``brain.py``, skills, etc.) are untouched -- rewiring
~60 working modules through a new layer in one pass is how regressions get
introduced into a production codebase.  New backend code (the REST API,
future Electron-facing endpoints) should prefer these services.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ServiceState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass
class ServiceHealth:
    service: str
    state: ServiceState
    detail: str = ""
    checked_at: float = field(default_factory=time.time)

    @property
    def available(self) -> bool:
        return self.state in (ServiceState.HEALTHY, ServiceState.DEGRADED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "state": self.state.value,
            "detail": self.detail,
            "available": self.available,
            "checked_at": self.checked_at,
        }


@dataclass
class ServiceResult:
    """Uniform return type for every service method.  Never raises."""

    ok: bool
    data: Any = None
    error: str | None = None
    service: str | None = None
    action: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, data: Any = None, **kw: Any) -> "ServiceResult":
        return cls(ok=True, data=data, **kw)

    @classmethod
    def failure(cls, error: str, **kw: Any) -> "ServiceResult":
        return cls(ok=False, error=error, **kw)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "service": self.service,
            "action": self.action,
            "meta": self.meta,
        }


class BaseService:
    """
    Optional convenience base: names the service and wraps calls uniformly.

    Services are not *required* to extend this (duck typing is fine), but it
    removes boilerplate for the common case.
    """

    name: str = "service"

    def _ok(self, data: Any = None, **meta: Any) -> ServiceResult:
        return ServiceResult.success(data, service=self.name, meta=meta)

    def _err(self, error: str, **meta: Any) -> ServiceResult:
        return ServiceResult.failure(str(error), service=self.name, meta=meta)

    def _call(self, action: str, fn, *args: Any, **kwargs: Any) -> ServiceResult:
        """Run *fn* and wrap the outcome; never raises to the caller."""
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            return ServiceResult.failure(str(exc), service=self.name, action=action)
        if isinstance(result, ServiceResult):
            result.service = result.service or self.name
            result.action = result.action or action
            return result
        return ServiceResult.success(result, service=self.name, action=action)

    def health(self) -> ServiceHealth:  # pragma: no cover - override point
        return ServiceHealth(self.name, ServiceState.HEALTHY, "default")
