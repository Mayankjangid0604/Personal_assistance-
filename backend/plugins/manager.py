"""
Plugin Manager for Aisha's Plugin Platform (Phase 10).

Owns the plugin lifecycle end to end:

* **validation** before admission,
* **permission declaration** to the broker,
* **dependency resolution** (topological load order),
* **activation / deactivation** (load / unload),
* **hot-loading and hot-unloading** at runtime,
* **health monitoring**,
* **governed action invocation** -- every action call runs through the
  permission broker and returns a normalised :class:`PluginResult`.

The manager is the single object the rest of Aisha uses to talk to plugins.
"""

from __future__ import annotations

from typing import Any, Callable

from .base import (
    Capability,
    HealthState,
    Permission,
    PermissionDenied,
    Plugin,
    PluginContext,
    PluginHealth,
    PluginResult,
    PluginStatus,
)
from .config import PluginConfigStore
from .permissions import PermissionBroker
from .registry import PluginRegistry
from .validation import ValidationError, assert_valid, version_satisfies


class PluginManager:
    """Lifecycle controller for the plugin ecosystem."""

    def __init__(
        self,
        registry: PluginRegistry | None = None,
        broker: PermissionBroker | None = None,
        config_store: PluginConfigStore | None = None,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.registry = registry or PluginRegistry()
        self.broker = broker or PermissionBroker()
        self.config = config_store or PluginConfigStore()
        self._logger = logger or (lambda msg: None)
        self._status: dict[str, PluginStatus] = {}
        self._errors: dict[str, str] = {}
        # auto-grant declared permissions on load unless the caller manages
        # grants explicitly (safe default for a single-user local platform).
        self.auto_grant = True

    # -- Registration -----------------------------------------------------

    def register(self, plugin: Plugin, *, validate: bool = True) -> Plugin:
        """
        Admit a plugin to the registry (discovered, not yet loaded).

        Validates the manifest/actions and records declared permissions.
        """
        if validate:
            assert_valid(plugin)
        self.registry.register(plugin)
        name = plugin.manifest().name
        self.broker.declare(name, plugin.manifest().permissions)
        self._status[name] = PluginStatus.DISCOVERED
        plugin._status = PluginStatus.DISCOVERED
        self._log(f"registered plugin {name}")
        return plugin

    # -- Dependency resolution -------------------------------------------

    def _resolve_order(self, names: list[str]) -> list[str]:
        """Topologically sort *names* by declared dependencies (Kahn)."""
        graph = {n: set(self._deps_of(n)) & set(names) for n in names}
        order: list[str] = []
        pending = dict(graph)
        while pending:
            ready = [n for n, deps in pending.items() if not deps]
            if not ready:
                # cycle -> fall back to insertion order for the remainder
                ready = list(pending.keys())
            for n in sorted(ready):
                order.append(n)
                pending.pop(n, None)
                for deps in pending.values():
                    deps.discard(n)
        return order

    def _deps_of(self, name: str) -> list[str]:
        plugin = self.registry.get(name)
        if plugin is None:
            return []
        deps: list[str] = []
        for dep in plugin.manifest().dependencies:
            deps.append(dep.split(">")[0].split("=")[0].split("<")[0].strip())
        return deps

    def _check_dependencies(self, plugin: Plugin) -> list[str]:
        """Return unmet dependency messages for *plugin* (empty == ok)."""
        problems: list[str] = []
        for spec in plugin.manifest().dependencies:
            dep_name = spec.split(">")[0].split("=")[0].split("<")[0].strip()
            required = spec[len(dep_name):].strip()
            dep = self.registry.get(dep_name)
            if dep is None:
                problems.append(f"missing dependency {dep_name!r}")
            elif required and not version_satisfies(dep.manifest().version, required):
                problems.append(
                    f"dependency {dep_name} v{dep.manifest().version} does not satisfy {required!r}"
                )
        return problems

    # -- Lifecycle --------------------------------------------------------

    def load(self, name: str) -> PluginResult:
        """Activate a single plugin (grants perms, checks deps, calls activate)."""
        plugin = self.registry.get(name)
        if plugin is None:
            return PluginResult.failure(f"unknown plugin {name!r}", plugin=name)
        if self._status.get(name) in (PluginStatus.LOADED, PluginStatus.ACTIVE):
            return PluginResult.success("already loaded", plugin=name)

        unmet = self._check_dependencies(plugin)
        if unmet:
            self._status[name] = PluginStatus.ERROR
            self._errors[name] = "; ".join(unmet)
            plugin._status = PluginStatus.ERROR
            return PluginResult.failure("; ".join(unmet), plugin=name)

        if self.auto_grant:
            self.broker.grant_all_declared(name)

        ctx = PluginContext(
            config=self.config.get(name),
            require=self.broker.requirer_for(name),
            logger=self._logger,
        )
        try:
            plugin.activate(ctx)
            self._status[name] = PluginStatus.ACTIVE
            plugin._status = PluginStatus.ACTIVE
            self._errors.pop(name, None)
            self._log(f"loaded plugin {name}")
            return PluginResult.success("loaded", plugin=name)
        except Exception as exc:  # noqa: BLE001
            self._status[name] = PluginStatus.ERROR
            self._errors[name] = str(exc)
            plugin._status = PluginStatus.ERROR
            return PluginResult.failure(f"activate failed: {exc}", plugin=name)

    def unload(self, name: str) -> PluginResult:
        """Deactivate a plugin (hot-unload); it stays registered."""
        plugin = self.registry.get(name)
        if plugin is None:
            return PluginResult.failure(f"unknown plugin {name!r}", plugin=name)
        try:
            plugin.deactivate()
        except Exception as exc:  # noqa: BLE001
            self._log(f"deactivate error for {name}: {exc}")
        self.broker.revoke_all(name)
        self._status[name] = PluginStatus.UNLOADED
        plugin._status = PluginStatus.UNLOADED
        self._log(f"unloaded plugin {name}")
        return PluginResult.success("unloaded", plugin=name)

    def reload(self, name: str) -> PluginResult:
        """Hot-reload: unload then load again (picks up new config)."""
        self.unload(name)
        return self.load(name)

    def load_all(self) -> dict[str, PluginResult]:
        """Load every registered plugin in dependency order."""
        results: dict[str, PluginResult] = {}
        for name in self._resolve_order(self.registry.names()):
            results[name] = self.load(name)
        return results

    def unload_all(self) -> None:
        for name in reversed(self._resolve_order(self.registry.names())):
            self.unload(name)

    def enable(self, name: str) -> PluginResult:
        return self.load(name)

    def disable(self, name: str) -> PluginResult:
        res = self.unload(name)
        if res.ok:
            self._status[name] = PluginStatus.DISABLED
            p = self.registry.get(name)
            if p is not None:
                p._status = PluginStatus.DISABLED
        return res

    # -- Invocation -------------------------------------------------------

    def invoke(self, plugin_name: str, action: str, *args, **kwargs) -> PluginResult:
        """
        Call ``plugin.action(*args, **kwargs)`` under governance.

        Permission checks happen inside the plugin via ``ctx.require(...)``;
        any :class:`PermissionDenied` is turned into a failed result rather
        than propagated.  The plugin must be loaded/active.
        """
        plugin = self.registry.get(plugin_name)
        if plugin is None:
            return PluginResult.failure(f"unknown plugin {plugin_name!r}", plugin=plugin_name, action=action)
        if self._status.get(plugin_name) not in (PluginStatus.ACTIVE, PluginStatus.LOADED):
            return PluginResult.failure(f"plugin {plugin_name!r} not loaded", plugin=plugin_name, action=action)

        actions = plugin.actions()
        fn = actions.get(action)
        if fn is None:
            return PluginResult.failure(
                f"unknown action {action!r} (have: {sorted(actions)})",
                plugin=plugin_name, action=action,
            )
        try:
            result = fn(*args, **kwargs)
        except PermissionDenied as exc:
            return PluginResult.failure(f"permission denied: {exc}", plugin=plugin_name, action=action)
        except Exception as exc:  # noqa: BLE001
            return PluginResult.failure(f"action error: {exc}", plugin=plugin_name, action=action)

        # Plugins may return a PluginResult directly, or a bare value.
        if isinstance(result, PluginResult):
            result.plugin = result.plugin or plugin_name
            result.action = result.action or action
            return result
        return PluginResult.success(result, plugin=plugin_name, action=action)

    # -- Health & status --------------------------------------------------

    def health(self, name: str) -> PluginHealth:
        plugin = self.registry.get(name)
        if plugin is None:
            return PluginHealth(name, HealthState.UNAVAILABLE, "not registered")
        if self._status.get(name) not in (PluginStatus.ACTIVE, PluginStatus.LOADED):
            return PluginHealth(name, HealthState.UNKNOWN, f"status={self._status.get(name, PluginStatus.DISCOVERED).value}")
        try:
            return plugin.check_health()
        except Exception as exc:  # noqa: BLE001
            return PluginHealth(name, HealthState.DEGRADED, f"health probe raised: {exc}")

    def health_report(self) -> dict[str, dict[str, Any]]:
        return {n: self.health(n).to_dict() for n in self.registry.names()}

    def status(self, name: str) -> PluginStatus:
        return self._status.get(name, PluginStatus.DISCOVERED)

    def status_report(self) -> dict[str, str]:
        return {n: self.status(n).value for n in self.registry.names()}

    def error(self, name: str) -> str | None:
        return self._errors.get(name)

    def capability_index(self) -> dict[str, list[str]]:
        return self.registry.capability_index()

    def manifests(self) -> list[dict]:
        return self.registry.manifests()

    # -- Internals --------------------------------------------------------

    def _log(self, msg: str) -> None:
        try:
            self._logger(f"[plugins] {msg}")
        except Exception:
            pass
