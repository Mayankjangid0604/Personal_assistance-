"""
Plugin SDK for Aisha's Plugin Platform (Phase 10).

Ergonomic helpers for authoring plugins with minimal boilerplate.  Third-party
and built-in plugins alike should build on :class:`SimplePlugin`, which turns
a manifest plus a set of ``@action`` methods into a full :class:`Plugin`.

Example
-------
    from plugins.sdk import SimplePlugin, action
    from plugins.base import PluginManifest, Capability, Permission

    class Hello(SimplePlugin):
        def manifest(self):
            return PluginManifest(
                name="hello", version="1.0.0",
                capabilities=[Capability.CALCULATOR],
                description="says hi",
            )

        @action
        def greet(self, name="world"):
            return f"hello {name}"
"""

from __future__ import annotations

from typing import Any, Callable

from .base import (
    Capability,
    HealthState,
    Permission,
    Plugin,
    PluginHealth,
    PluginManifest,
    PluginResult,
)


def action(fn: Callable) -> Callable:
    """Mark a method as a plugin action (auto-discovered by SimplePlugin)."""
    fn._is_plugin_action = True  # type: ignore[attr-defined]
    return fn


class SimplePlugin(Plugin):
    """
    Convenience base: methods decorated with :func:`action` become actions.

    Subclasses only need to implement :meth:`manifest` and one or more
    ``@action`` methods.  Override :meth:`health` for custom health logic.
    """

    def actions(self) -> dict[str, Callable[..., Any]]:
        found: dict[str, Callable[..., Any]] = {}
        for attr in dir(self):
            if attr.startswith("_"):
                continue
            fn = getattr(self, attr, None)
            if callable(fn) and getattr(fn, "_is_plugin_action", False):
                found[attr] = fn
        return found

    def health(self) -> PluginHealth:  # override point
        return super().check_health()

    def check_health(self) -> PluginHealth:
        return self.health()

    # -- result helpers ---------------------------------------------------

    @staticmethod
    def ok(data: Any = None, **meta: Any) -> PluginResult:
        return PluginResult.success(data, meta=meta)

    @staticmethod
    def err(message: str, **meta: Any) -> PluginResult:
        return PluginResult.failure(message, meta=meta)

    @staticmethod
    def healthy(detail: str = "") -> PluginHealth:
        return PluginHealth("", HealthState.HEALTHY, detail)

    def health_of(self, state: HealthState, detail: str = "") -> PluginHealth:
        return PluginHealth(self.name, state, detail)


# Re-export the common symbols so authors import everything from the SDK.
__all__ = [
    "SimplePlugin",
    "action",
    "PluginManifest",
    "PluginResult",
    "PluginHealth",
    "Capability",
    "Permission",
    "HealthState",
]
