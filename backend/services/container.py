"""
ServiceContainer for Aisha AI Assistant (Phase 11).

A minimal dependency-injection container: constructs and holds the eight
service facades, wiring each to its real subsystem by default while allowing
every one to be swapped out (for tests, or for a future multi-profile
deployment).  This is the single object the REST API layer imports.

Usage::

    from services import get_services

    services = get_services()
    services.providers.generate("hello", task="conversation")
    services.plugins.invoke("calculator", "evaluate", "2+2")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agent_service import AgentService
from .configuration_service import ConfigurationService
from .desktop_service import DesktopService
from .memory_service import MemoryService
from .notification_service import NotificationService
from .plugin_service import PluginService
from .provider_service import ProviderService
from .workspace_service import WorkspaceService


@dataclass
class ServiceContainer:
    """Holds one instance of every Phase-11 service."""

    config: ConfigurationService
    providers: ProviderService
    plugins: PluginService
    memory: MemoryService
    notifications: NotificationService
    workspace: WorkspaceService
    agents: AgentService
    desktop: DesktopService

    def health_report(self) -> dict[str, dict[str, Any]]:
        """Fleet-wide health -- the seam for a future Performance Dashboard."""
        services = {
            "configuration": self.config,
            "provider": self.providers,
            "plugin": self.plugins,
            "memory": self.memory,
            "notification": self.notifications,
            "workspace": self.workspace,
            "agent": self.agents,
            "desktop": self.desktop,
        }
        report: dict[str, dict[str, Any]] = {}
        for name, svc in services.items():
            try:
                report[name] = svc.health().to_dict()
            except Exception as exc:  # noqa: BLE001
                report[name] = {"service": name, "state": "unavailable", "detail": str(exc), "available": False}
        return report


def build_default_container() -> ServiceContainer:
    """Construct a container with every service wired to its real default."""
    return ServiceContainer(
        config=ConfigurationService(),
        providers=ProviderService(),
        plugins=PluginService(),
        memory=MemoryService(),
        notifications=NotificationService(),
        workspace=WorkspaceService(),
        agents=AgentService(),
        desktop=DesktopService(),
    )


_CONTAINER: ServiceContainer | None = None


def get_services() -> ServiceContainer:
    """Return the process-wide service container, building it on first use."""
    global _CONTAINER
    if _CONTAINER is None:
        _CONTAINER = build_default_container()
    return _CONTAINER


def reset_services() -> None:
    """Drop the cached container (tests / reconfiguration)."""
    global _CONTAINER
    _CONTAINER = None
