"""
ConfigurationService for Aisha AI Assistant (Phase 11).

A single, namespaced, layered configuration surface for application-level
settings (as distinct from :mod:`providers.config`, which stays focused on
LLM routing).  Layering, low to high precedence:

    built-in defaults  <  JSON file  <  ``AISHA_*`` environment variables  <  runtime overrides

Keys are dotted (``"voice.enabled"``, ``"ui.theme"``).  This is the seam
Milestone 9 (config import/export, backup/restore) will build on.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from .base import BaseService, ServiceHealth, ServiceResult, ServiceState

_ENV_PREFIX = "AISHA_"

_DEFAULTS: dict[str, Any] = {
    "ui.theme": "dark",
    "voice.enabled": False,
    "voice.mode": "text",
    "automation.require_approval": True,
    "logging.level": "info",
}


def _flatten_env(prefix: str = _ENV_PREFIX) -> dict[str, str]:
    """``AISHA_UI_THEME=light`` -> ``{"ui.theme": "light"}``."""
    out: dict[str, str] = {}
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        dotted = key[len(prefix):].lower().replace("__", ".").replace("_", ".")
        out[dotted] = value
    return out


def _coerce(raw: str) -> Any:
    """Best-effort scalar coercion for env-sourced string values."""
    low = raw.strip().lower()
    if low in ("true", "1", "yes", "on"):
        return True
    if low in ("false", "0", "no", "off"):
        return False
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


class ConfigurationService(BaseService):
    """Layered app configuration: defaults < file < env < runtime overrides."""

    name = "configuration"

    def __init__(self, path: str | Path | None = None, defaults: dict[str, Any] | None = None) -> None:
        self._path = Path(path) if path else None
        self._defaults = deepcopy(defaults) if defaults is not None else deepcopy(_DEFAULTS)
        self._file: dict[str, Any] = {}
        self._overrides: dict[str, Any] = {}
        if self._path and self._path.exists():
            self._load_file()

    # -- Resolution ---------------------------------------------------------

    def _layers(self) -> list[dict[str, Any]]:
        env = {k: _coerce(v) for k, v in _flatten_env().items()}
        return [self._defaults, self._file, env, self._overrides]

    def get(self, key: str, default: Any = None) -> Any:
        value = default
        for layer in self._layers():
            if key in layer:
                value = layer[key]
        return value

    def get_result(self, key: str, default: Any = None) -> ServiceResult:
        return self._ok(self.get(key, default), action="get")

    def set(self, key: str, value: Any, *, persist: bool = False) -> ServiceResult:
        self._overrides[key] = value
        if persist:
            self._file[key] = value
            self._save_file()
        return self._ok({"key": key, "value": value}, action="set")

    def unset(self, key: str) -> ServiceResult:
        self._overrides.pop(key, None)
        self._file.pop(key, None)
        return self._ok({"key": key}, action="unset")

    def all(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for layer in self._layers():
            merged.update(layer)
        return merged

    # -- Import / export (Milestone 9 seam) ----------------------------------

    def export_dict(self) -> dict[str, Any]:
        """Everything except environment (env belongs to the deployment, not the export)."""
        merged: dict[str, Any] = {}
        for layer in (self._defaults, self._file, self._overrides):
            merged.update(layer)
        return deepcopy(merged)

    def import_dict(self, data: dict[str, Any], *, persist: bool = False) -> ServiceResult:
        for key, value in data.items():
            self.set(key, value, persist=persist)
        return self._ok({"imported": len(data)}, action="import")

    # -- Persistence ----------------------------------------------------------

    def _load_file(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                self._file = json.load(fh)
        except Exception:
            self._file = {}

    def _save_file(self) -> None:
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._file, fh, indent=2)
        except Exception:
            pass

    # -- Health ---------------------------------------------------------------

    def health(self) -> ServiceHealth:
        detail = f"{len(self.all())} effective keys"
        return ServiceHealth(self.name, ServiceState.HEALTHY, detail)
