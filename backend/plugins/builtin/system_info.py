"""
System Information Plugin (Phase 10, built-in).

Read-only system introspection using only the standard library.  Requires the
``system.info`` permission.  Never mutates anything, so it is safe on any host.
"""

from __future__ import annotations

import os
import platform
import sys
import time
from typing import Any

from ..base import Capability, HealthState, PluginHealth, PluginManifest, Permission
from ..sdk import SimplePlugin, action


class SystemInfoPlugin(SimplePlugin):
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="system_info",
            version="1.0.0",
            capabilities=[Capability.SYSTEM],
            permissions=[Permission.SYSTEM_INFO],
            description="Read-only host information (OS, Python, cpu count, cwd).",
            documentation="actions: info(), cpu_count(), env(name)",
            tags=["system", "diagnostics", "offline"],
        )

    @action
    def info(self) -> dict[str, Any]:
        self.require(Permission.SYSTEM_INFO)
        return {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "cpu_count": os.cpu_count(),
            "cwd": os.getcwd(),
            "pid": os.getpid(),
            "time": time.time(),
        }

    @action
    def cpu_count(self) -> int:
        self.require(Permission.SYSTEM_INFO)
        return os.cpu_count() or 1

    @action
    def env(self, name: str) -> str | None:
        self.require(Permission.SYSTEM_INFO)
        return os.environ.get(name)

    def health(self) -> PluginHealth:
        return self.health_of(HealthState.HEALTHY, platform.system())
