"""
Aisha Plugin Platform (Phase 10 -- Plugin Ecosystem).

A permission-gated, hot-loadable plugin system.  The rest of Aisha talks to a
:class:`PluginManager`, which validates plugins, resolves dependencies,
enforces permissions through a :class:`PermissionBroker`, monitors health, and
invokes actions -- all returning a uniform :class:`PluginResult`.

Quick start::

    from plugins import build_default_manager, Permission

    mgr = build_default_manager()          # built-ins registered + loaded
    print(mgr.invoke("calculator", "evaluate", "2 + 2 * 10").data)   # 22
    print(mgr.capability_index())

Design mirrors the provider platform: registry + capability index + health,
config-driven, no hardcoded wiring.  Permission gating is capability-based
access control (the seam for Milestone 2 governance), not OS process isolation.
"""

from __future__ import annotations

from .base import (
    Capability,
    HealthState,
    Permission,
    PermissionDenied,
    Plugin,
    PluginContext,
    PluginHealth,
    PluginManifest,
    PluginResult,
    PluginStatus,
    coerce_capability,
    coerce_permission,
)
from .config import PluginConfigStore
from .permissions import PermissionBroker
from .registry import PluginRegistry
from .manager import PluginManager
from .validation import (
    ValidationError,
    assert_valid,
    parse_version,
    validate_manifest,
    validate_plugin,
    version_satisfies,
)
from .sdk import SimplePlugin, action

__all__ = [
    # base
    "Capability",
    "Permission",
    "PluginStatus",
    "HealthState",
    "Plugin",
    "PluginManifest",
    "PluginResult",
    "PluginHealth",
    "PluginContext",
    "PermissionDenied",
    "coerce_capability",
    "coerce_permission",
    # platform
    "PluginRegistry",
    "PluginManager",
    "PermissionBroker",
    "PluginConfigStore",
    # validation
    "ValidationError",
    "assert_valid",
    "validate_plugin",
    "validate_manifest",
    "parse_version",
    "version_satisfies",
    # sdk
    "SimplePlugin",
    "action",
    # helpers
    "build_default_manager",
]


def build_default_manager(*, include_planned: bool = True, load: bool = True) -> PluginManager:
    """
    Construct a manager with the built-in catalogue registered (and loaded).

    Imported lazily so the built-ins are only pulled in when actually needed.
    """
    from .builtin import register_builtins

    manager = PluginManager()
    register_builtins(manager, include_planned=include_planned, load=load)
    return manager
