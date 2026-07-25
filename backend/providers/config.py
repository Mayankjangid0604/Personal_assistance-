"""
Provider & Routing Configuration for Aisha AI Assistant (Phase 9).

All routing knowledge lives here as *data*, not code.  Changing which model
serves which task, or which provider wins, is a config edit -- the registry
logic never names a provider or model literally.  This is what satisfies the
"never hardcode providers" requirement.

The config can be overridden at runtime (e.g. from a settings file or the
Electron settings window) by calling :func:`load_config` with a dict, or by
setting the ``AISHA_PROVIDER_CONFIG`` environment variable to a JSON path.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from .base import Capability, TaskType


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    # Ordered list of provider names to register when auto-building the
    # registry.  Order is the tie-break preference (first = most preferred).
    "provider_order": ["ollama", "gemini", "local"],

    # Ollama model catalogue: model -> capabilities it is good at.
    # These are the locally installed models named in the spec.
    "ollama_models": {
        "qwen2.5-coder:7b": ["coding", "general"],
        "deepseek-r1:8b": ["reasoning", "general"],
        "phi4:latest": ["planning", "reasoning", "general"],
        "gemma2:9b": ["conversation", "general"],
        "qwen2.5:7b": ["general", "conversation", "reasoning"],
    },

    # Task -> preferred (provider, model).  The registry treats this as a
    # *hint*: if that provider/model is unavailable it falls through to
    # capability-based selection and finally the fallback provider.
    "task_routing": {
        "coding":       {"provider": "ollama", "model": "qwen2.5-coder:7b"},
        "reasoning":    {"provider": "ollama", "model": "deepseek-r1:8b"},
        "planning":     {"provider": "ollama", "model": "phi4:latest"},
        "conversation": {"provider": "ollama", "model": "gemma2:9b"},
        "general":      {"provider": "ollama", "model": "qwen2.5:7b"},
    },

    # Provider used when nothing local is healthy.
    "fallback_provider": "gemini",

    # Ultimate fallback that is ALWAYS available (rule-based, offline).
    "last_resort_provider": "local",

    # Connection settings for Ollama.
    "ollama": {
        "host": "http://127.0.0.1:11434",
        "timeout": 60,
    },

    # Which task each capability maps to (inverse of the above, for lookups).
    "capability_for_task": {
        "coding": "coding",
        "reasoning": "reasoning",
        "planning": "planning",
        "conversation": "conversation",
        "general": "general",
    },
}


# ---------------------------------------------------------------------------
# Live config (mutable singleton with reset support)
# ---------------------------------------------------------------------------

_CONFIG: dict[str, Any] = deepcopy(DEFAULT_CONFIG)


def get_config() -> dict[str, Any]:
    """Return the live config dict (mutations persist -- use with care)."""
    return _CONFIG


def load_config(overrides: dict[str, Any] | None = None, *, path: str | Path | None = None) -> dict[str, Any]:
    """
    Merge *overrides* (and/or a JSON file at *path*) onto the defaults.

    Precedence (low -> high): DEFAULT_CONFIG < file < overrides.  Returns the
    new live config.  Passing nothing simply reloads the defaults, honouring
    the ``AISHA_PROVIDER_CONFIG`` env var if set.
    """
    global _CONFIG
    merged = deepcopy(DEFAULT_CONFIG)

    env_path = os.environ.get("AISHA_PROVIDER_CONFIG")
    file_path = path or env_path
    if file_path and Path(file_path).exists():
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                _deep_merge(merged, json.load(fh))
        except Exception:
            pass  # bad config file never breaks startup

    if overrides:
        _deep_merge(merged, overrides)

    _CONFIG = merged
    return _CONFIG


def reset_config() -> dict[str, Any]:
    """Restore the built-in defaults.  Handy for tests."""
    global _CONFIG
    _CONFIG = deepcopy(DEFAULT_CONFIG)
    return _CONFIG


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> None:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------

def route_for_task(task: TaskType | str) -> dict[str, str]:
    """Return the ``{"provider", "model"}`` hint for *task* (may be empty)."""
    key = task.value if isinstance(task, TaskType) else str(task).lower()
    return dict(_CONFIG.get("task_routing", {}).get(key, {}))


def ollama_model_capabilities() -> dict[str, list[Capability]]:
    """Return the Ollama model catalogue as Capability enums."""
    out: dict[str, list[Capability]] = {}
    for model, caps in _CONFIG.get("ollama_models", {}).items():
        out[model] = [Capability(c) for c in caps]
    return out


def fallback_provider() -> str:
    return _CONFIG.get("fallback_provider", "gemini")


def last_resort_provider() -> str:
    return _CONFIG.get("last_resort_provider", "local")


def provider_order() -> list[str]:
    return list(_CONFIG.get("provider_order", []))


def ollama_settings() -> dict[str, Any]:
    return dict(_CONFIG.get("ollama", {}))
