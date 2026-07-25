"""
Aisha Service Layer (Phase 11 -- Production Integration Layer).

Eight thin, dependency-injected facades over existing subsystems, giving new
backend code (the REST API, Electron-facing endpoints) one obvious, testable
seam to call through -- the same role :mod:`providers` plays for LLM backends
and :mod:`plugins` plays for extensions.

    ConfigurationService  -- layered app config (defaults < file < env < runtime)
    ProviderService        -- facade over the LLM provider registry
    PluginService          -- facade over the plugin manager
    MemoryService          -- facade over short/long-term memory
    NotificationService    -- facade over the notification center
    WorkspaceService       -- facade over the cognitive workspace
    AgentService           -- facade over the distributed agent coordinator
    DesktopService         -- READ-ONLY facade over desktop awareness

This is an *additive* layer: existing modules keep their direct imports.
Rewiring ~60 already-working modules through a new layer in one pass is how
regressions get introduced into a production codebase, so it wasn't done.
New code should prefer the service layer; existing code is untouched.

Quick start::

    from services import get_services

    services = get_services()
    result = services.plugins.invoke("calculator", "evaluate", "2+2")
    print(result.data)                # -> 4
    print(services.health_report())   # fleet-wide health snapshot
"""

from __future__ import annotations

from .base import BaseService, ServiceHealth, ServiceResult, ServiceState
from .configuration_service import ConfigurationService
from .provider_service import ProviderService
from .plugin_service import PluginService
from .memory_service import MemoryService
from .notification_service import NotificationService, NotificationBackend
from .workspace_service import WorkspaceService
from .agent_service import AgentService
from .desktop_service import DesktopService
from .container import (
    ServiceContainer,
    build_default_container,
    get_services,
    reset_services,
)

__all__ = [
    # base
    "BaseService",
    "ServiceResult",
    "ServiceHealth",
    "ServiceState",
    # services
    "ConfigurationService",
    "ProviderService",
    "PluginService",
    "MemoryService",
    "NotificationService",
    "NotificationBackend",
    "WorkspaceService",
    "AgentService",
    "DesktopService",
    # container
    "ServiceContainer",
    "build_default_container",
    "get_services",
    "reset_services",
]
