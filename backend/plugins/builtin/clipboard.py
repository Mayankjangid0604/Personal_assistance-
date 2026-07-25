"""
Clipboard Plugin (Phase 10, built-in).

Permission-gated clipboard access with a pluggable backend.  Real clipboard
access needs an OS backend (pyperclip, pbcopy/xclip, win32clipboard); when none
is available the plugin degrades gracefully to an in-memory buffer so it stays
testable and never crashes on a headless machine.
"""

from __future__ import annotations

from typing import Any, Callable

from ..base import Capability, HealthState, PluginHealth, PluginManifest, Permission
from ..sdk import SimplePlugin, action


class ClipboardPlugin(SimplePlugin):
    def __init__(self, backend_get: Callable[[], str] | None = None,
                 backend_set: Callable[[str], None] | None = None) -> None:
        super().__init__()
        # Injectable backend (tests / real OS adapters).  Defaults to memory.
        self._buffer = ""
        self._backend_get = backend_get
        self._backend_set = backend_set

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="clipboard",
            version="1.0.0",
            capabilities=[Capability.CLIPBOARD],
            permissions=[Permission.CLIPBOARD_READ, Permission.CLIPBOARD_WRITE],
            description="Read and write the system clipboard (memory fallback).",
            documentation="actions: copy(text), paste() -> text",
            tags=["clipboard", "io"],
        )

    @property
    def _has_os_backend(self) -> bool:
        return self._backend_get is not None and self._backend_set is not None

    @action
    def copy(self, text: str) -> dict[str, Any]:
        self.require(Permission.CLIPBOARD_WRITE)
        if self._has_os_backend:
            self._backend_set(text)  # type: ignore[misc]
        else:
            self._buffer = text
        return {"bytes": len(text), "backend": "os" if self._has_os_backend else "memory"}

    @action
    def paste(self) -> str:
        self.require(Permission.CLIPBOARD_READ)
        if self._has_os_backend:
            return self._backend_get()  # type: ignore[misc]
        return self._buffer

    def health(self) -> PluginHealth:
        if self._has_os_backend:
            return self.health_of(HealthState.HEALTHY, "os backend")
        return self.health_of(HealthState.DEGRADED, "in-memory fallback (no OS clipboard backend)")
