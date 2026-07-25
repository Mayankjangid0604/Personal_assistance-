"""
Plugin Configuration Store for Aisha's Plugin Platform (Phase 10).

A simple, in-memory per-plugin key/value store with optional JSON persistence.
The manager hands each plugin its slice of config at activation, so plugins
never read global state directly.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class PluginConfigStore:
    """Per-plugin configuration with optional file backing."""

    def __init__(self, initial: dict[str, dict[str, Any]] | None = None, path: str | Path | None = None) -> None:
        self._data: dict[str, dict[str, Any]] = deepcopy(initial) if initial else {}
        self._path = Path(path) if path else None
        if self._path and self._path.exists():
            self.load_file()

    def get(self, plugin: str) -> dict[str, Any]:
        return dict(self._data.get(plugin, {}))

    def get_value(self, plugin: str, key: str, default: Any = None) -> Any:
        return self._data.get(plugin, {}).get(key, default)

    def set(self, plugin: str, config: dict[str, Any]) -> None:
        self._data[plugin] = dict(config)

    def update(self, plugin: str, **values: Any) -> None:
        self._data.setdefault(plugin, {}).update(values)

    def clear(self, plugin: str | None = None) -> None:
        if plugin is None:
            self._data.clear()
        else:
            self._data.pop(plugin, None)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self._data)

    # -- Persistence ------------------------------------------------------

    def load_file(self) -> None:
        if self._path and self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    self._data = json.load(fh)
            except Exception:
                pass

    def save_file(self) -> None:
        if self._path:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._path, "w", encoding="utf-8") as fh:
                    json.dump(self._data, fh, indent=2)
            except Exception:
                pass
