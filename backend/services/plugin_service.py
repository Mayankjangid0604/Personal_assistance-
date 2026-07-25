"""
PluginService for Aisha AI Assistant (Phase 11).

Thin facade over :mod:`plugins` (Phase 10).  This is the surface the REST API
and Electron Plugin Manager should call for discovery, lifecycle and invoking
plugin actions -- mirroring :class:`ProviderService`'s role for the provider
platform.
"""

from __future__ import annotations

from typing import Any

from .base import BaseService, ServiceHealth, ServiceResult, ServiceState


class PluginService(BaseService):
    """Facade over a :class:`plugins.PluginManager`."""

    name = "plugin"

    def __init__(self, manager: Any | None = None) -> None:
        self._manager = manager  # lazily resolved if None

    @property
    def manager(self) -> Any:
        if self._manager is None:
            from plugins import build_default_manager
            self._manager = build_default_manager()
        return self._manager

    # -- Discovery --------------------------------------------------------------

    def list_plugins(self) -> ServiceResult:
        return self._call("list_plugins", self.manager.manifests)

    def capability_index(self) -> ServiceResult:
        return self._call("capability_index", self.manager.capability_index)

    def status_report(self) -> ServiceResult:
        return self._call("status_report", self.manager.status_report)

    def plugin_health(self) -> ServiceResult:
        return self._call("plugin_health", self.manager.health_report)

    # -- Lifecycle ----------------------------------------------------------------

    def load(self, name: str) -> ServiceResult:
        return self._call("load", self.manager.load, name)

    def unload(self, name: str) -> ServiceResult:
        return self._call("unload", self.manager.unload, name)

    def reload(self, name: str) -> ServiceResult:
        return self._call("reload", self.manager.reload, name)

    def enable(self, name: str) -> ServiceResult:
        return self._call("enable", self.manager.enable, name)

    def disable(self, name: str) -> ServiceResult:
        return self._call("disable", self.manager.disable, name)

    # -- Invocation -----------------------------------------------------------------

    def invoke(self, plugin: str, action: str, *args: Any, **kwargs: Any) -> ServiceResult:
        try:
            result = self.manager.invoke(plugin, action, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            return self._err(str(exc), action=f"{plugin}.{action}")
        return ServiceResult(
            ok=result.ok, data=result.data, error=result.error,
            service=self.name, action=f"{plugin}.{action}", meta=dict(result.meta),
        )

    # -- Health -------------------------------------------------------------------

    def health(self) -> ServiceHealth:
        try:
            names = self.manager.registry.names()
        except Exception as exc:  # noqa: BLE001
            return ServiceHealth(self.name, ServiceState.UNAVAILABLE, str(exc))
        if not names:
            return ServiceHealth(self.name, ServiceState.UNAVAILABLE, "no plugins registered")
        active = sum(1 for n in names if self.manager.status(n).value == "active")
        state = ServiceState.HEALTHY if active else ServiceState.DEGRADED
        return ServiceHealth(self.name, state, f"{active}/{len(names)} plugins active")
