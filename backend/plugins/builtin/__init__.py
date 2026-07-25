"""
Built-in Plugin Catalogue for Aisha (Phase 10).

Exposes the concrete built-in plugins and a helper to register the whole
catalogue with a :class:`PluginManager`.
"""

from __future__ import annotations

from .calculator import CalculatorPlugin
from .filesystem import FilesystemPlugin
from .clipboard import ClipboardPlugin
from .system_info import SystemInfoPlugin
from .git import GitPlugin
from .planned import PLANNED_PLUGINS

#: Fully working, offline-testable built-in plugins.
IMPLEMENTED_PLUGINS = [
    CalculatorPlugin,
    FilesystemPlugin,
    ClipboardPlugin,
    SystemInfoPlugin,
    GitPlugin,
]

#: Every built-in plugin class (implemented + declared-but-planned).
ALL_BUILTIN_PLUGINS = IMPLEMENTED_PLUGINS + PLANNED_PLUGINS


def register_builtins(manager, *, include_planned: bool = True, load: bool = False):
    """
    Register the built-in catalogue with *manager*.

    Parameters
    ----------
    include_planned : bool
        Also register the declared-but-not-implemented catalogue members.
    load : bool
        Immediately load (activate) everything after registration.
    """
    classes = ALL_BUILTIN_PLUGINS if include_planned else IMPLEMENTED_PLUGINS
    for cls in classes:
        try:
            manager.register(cls())
        except Exception:
            continue
    if load:
        manager.load_all()
    return manager


__all__ = [
    "CalculatorPlugin",
    "FilesystemPlugin",
    "ClipboardPlugin",
    "SystemInfoPlugin",
    "GitPlugin",
    "IMPLEMENTED_PLUGINS",
    "ALL_BUILTIN_PLUGINS",
    "register_builtins",
]
