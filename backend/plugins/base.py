"""
Plugin Interface & Manifest for Aisha AI Assistant (Phase 10 -- Plugin Platform).

Defines the contract every Aisha plugin implements.  A plugin is a
self-describing, permission-gated, hot-loadable capability provider.  The rest
of the platform (registry, manager, permission broker) only ever talks to a
plugin through this interface, mirroring the provider platform's design.

Nothing here performs privileged I/O or imports heavy dependencies -- concrete
plugins do that lazily and only after their permissions are granted, so
importing this module is always cheap and safe.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Permission(str, Enum):
    """Privileges a plugin may require.  Enforced by the permission broker."""

    FS_READ = "fs.read"
    FS_WRITE = "fs.write"
    CLIPBOARD_READ = "clipboard.read"
    CLIPBOARD_WRITE = "clipboard.write"
    PROCESS_SPAWN = "process.spawn"
    PROCESS_KILL = "process.kill"
    NETWORK = "network"
    SYSTEM_INFO = "system.info"
    SYSTEM_CONTROL = "system.control"
    SCREEN_CAPTURE = "screen.capture"
    CAMERA = "device.camera"
    MICROPHONE = "device.microphone"
    NOTIFY = "system.notify"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class Capability(str, Enum):
    """What a plugin can do.  Used for capability-based discovery."""

    FILESYSTEM = "filesystem"
    TERMINAL = "terminal"
    GIT = "git"
    CLIPBOARD = "clipboard"
    BROWSER = "browser"
    PDF = "pdf"
    OCR = "ocr"
    CALCULATOR = "calculator"
    WEATHER = "weather"
    CALENDAR = "calendar"
    EMAIL = "email"
    CAMERA = "camera"
    MICROPHONE = "microphone"
    IMAGE_GENERATION = "image_generation"
    SYSTEM = "system"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class PluginStatus(str, Enum):
    """Lifecycle state of a plugin instance."""

    DISCOVERED = "discovered"     # registered, not yet loaded
    LOADED = "loaded"             # activate() succeeded
    ACTIVE = "active"             # loaded and healthy
    DEGRADED = "degraded"         # loaded but unhealthy
    DISABLED = "disabled"         # explicitly turned off
    ERROR = "error"              # failed to load/activate
    UNLOADED = "unloaded"        # deactivated

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass
class PluginManifest:
    """Self-description a plugin publishes.  The heart of the ecosystem."""

    name: str
    version: str
    capabilities: list[Capability]
    permissions: list[Permission] = field(default_factory=list)
    description: str = ""
    author: str = "AISHA"
    dependencies: list[str] = field(default_factory=list)
    documentation: str = ""
    config_schema: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "permissions": [p.value for p in self.permissions],
            "description": self.description,
            "author": self.author,
            "dependencies": list(self.dependencies),
            "documentation": self.documentation,
            "config_schema": dict(self.config_schema),
            "tags": list(self.tags),
        }


@dataclass
class PluginHealth:
    """Snapshot of a plugin's operational health."""

    plugin: str
    state: HealthState
    detail: str = ""
    checked_at: float = field(default_factory=time.time)

    @property
    def available(self) -> bool:
        return self.state in (HealthState.HEALTHY, HealthState.DEGRADED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin": self.plugin,
            "state": self.state.value,
            "detail": self.detail,
            "available": self.available,
            "checked_at": self.checked_at,
        }


@dataclass
class PluginResult:
    """Uniform return type for a plugin action.  Never raises to the caller."""

    ok: bool
    data: Any = None
    error: str | None = None
    plugin: str | None = None
    action: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, data: Any = None, **kw) -> "PluginResult":
        return cls(ok=True, data=data, **kw)

    @classmethod
    def failure(cls, error: str, **kw) -> "PluginResult":
        return cls(ok=False, error=error, **kw)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "plugin": self.plugin,
            "action": self.action,
            "meta": self.meta,
        }


class PermissionDenied(Exception):
    """Raised internally when a plugin attempts an ungranted permission."""


@dataclass
class PluginContext:
    """
    Runtime services handed to a plugin at activation.

    ``require`` is the permission-broker hook: a plugin calls
    ``ctx.require(Permission.FS_WRITE)`` before a privileged operation and the
    broker raises :class:`PermissionDenied` if the permission is not granted.
    """

    config: dict[str, Any] = field(default_factory=dict)
    require: Callable[[Permission], None] = lambda p: None
    logger: Callable[[str], None] = lambda msg: None
    workdir: str | None = None


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------

class Plugin(ABC):
    """
    Base class every Aisha plugin extends.

    Subclasses declare a :meth:`manifest` and implement :meth:`actions`
    (a mapping of action name -> callable).  Lifecycle hooks (:meth:`activate`,
    :meth:`deactivate`) are optional.  The manager wraps every action call so
    permissions are enforced and results are normalised.
    """

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None
        self._status: PluginStatus = PluginStatus.DISCOVERED

    # -- Description ------------------------------------------------------

    @abstractmethod
    def manifest(self) -> PluginManifest:
        """Return the plugin's self-description."""

    @property
    def name(self) -> str:
        return self.manifest().name

    @property
    def version(self) -> str:
        return self.manifest().version

    @property
    def status(self) -> PluginStatus:
        return self._status

    # -- Lifecycle --------------------------------------------------------

    def activate(self, ctx: PluginContext) -> None:
        """Called once when the plugin is loaded.  Override to set up state."""
        self._ctx = ctx

    def deactivate(self) -> None:
        """Called when the plugin is unloaded.  Override to release resources."""
        self._ctx = None

    # -- Actions ----------------------------------------------------------

    @abstractmethod
    def actions(self) -> dict[str, Callable[..., Any]]:
        """Return a mapping of action name -> bound callable."""

    def has_action(self, name: str) -> bool:
        return name in self.actions()

    # -- Health -----------------------------------------------------------

    def check_health(self) -> PluginHealth:
        """Probe the plugin.  Default: healthy once activated."""
        state = HealthState.HEALTHY if self._ctx is not None else HealthState.UNKNOWN
        return PluginHealth(self.name, state, detail="default health")

    # -- Convenience ------------------------------------------------------

    def require(self, permission: Permission) -> None:
        """Ask the broker to authorise *permission* (raises if denied)."""
        if self._ctx is None:
            raise PermissionDenied(f"{self.name}: not activated")
        self._ctx.require(permission)

    def config(self, key: str, default: Any = None) -> Any:
        if self._ctx is None:
            return default
        return self._ctx.config.get(key, default)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        m = self.manifest()
        return f"<Plugin {m.name} v{m.version} status={self._status.value}>"


def coerce_permission(value: Permission | str) -> Permission:
    if isinstance(value, Permission):
        return value
    return Permission(str(value))


def coerce_capability(value: Capability | str) -> Capability:
    if isinstance(value, Capability):
        return value
    return Capability(str(value))
