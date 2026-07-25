"""
Plugin Registry for Aisha's Plugin Platform (Phase 10).

Holds registered plugin instances and answers discovery queries (by name, by
capability).  Deliberately dumb: lifecycle and permissions live in the manager
and broker.  Mirrors the provider registry so the two platforms feel identical.
"""

from __future__ import annotations

from typing import Iterator

from .base import Capability, Plugin, coerce_capability


class PluginRegistry:
    """A name-keyed collection of plugins with capability lookup."""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> Plugin:
        name = plugin.manifest().name
        self._plugins[name] = plugin
        return plugin

    def unregister(self, name: str) -> None:
        self._plugins.pop(name, None)

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def all(self) -> list[Plugin]:
        return list(self._plugins.values())

    def names(self) -> list[str]:
        return list(self._plugins.keys())

    def __contains__(self, name: object) -> bool:
        return name in self._plugins

    def __iter__(self) -> Iterator[Plugin]:
        return iter(self._plugins.values())

    def __len__(self) -> int:
        return len(self._plugins)

    def clear(self) -> None:
        self._plugins.clear()

    # -- Discovery --------------------------------------------------------

    def with_capability(self, capability: Capability | str) -> list[Plugin]:
        cap = coerce_capability(capability)
        return [p for p in self._plugins.values() if cap in p.manifest().capabilities]

    def capability_index(self) -> dict[str, list[str]]:
        """Return ``{capability: [plugin names]}`` across the registry."""
        index: dict[str, list[str]] = {}
        for plugin in self._plugins.values():
            for cap in plugin.manifest().capabilities:
                index.setdefault(cap.value, []).append(plugin.manifest().name)
        return index

    def manifests(self) -> list[dict]:
        return [p.manifest().to_dict() for p in self._plugins.values()]
