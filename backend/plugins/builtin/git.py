"""
Git Plugin (Phase 10, built-in).

Read-oriented Git integration via the ``git`` CLI.  Requires ``process.spawn``
(it shells out to git).  Commands are constructed as argument lists -- never a
shell string -- so there is no shell-injection surface.  The working directory
is confined to a configured repo path (defaults to cwd).

Read actions (status, log, branch, diff) are safe; this plugin intentionally
does not expose push/commit -- those belong behind Milestone 2 governance.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from ..base import Capability, HealthState, PluginHealth, PluginManifest, Permission
from ..sdk import SimplePlugin, action


class GitPlugin(SimplePlugin):
    def __init__(self, runner: Callable[[list[str], str], subprocess.CompletedProcess] | None = None) -> None:
        super().__init__()
        # Injectable runner for tests; defaults to a real subprocess call.
        self._runner = runner or self._default_runner

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="git",
            version="1.0.0",
            capabilities=[Capability.GIT],
            permissions=[Permission.PROCESS_SPAWN],
            description="Read-only Git operations (status, log, branch, diff).",
            documentation="config: {repo: path}. actions: status(), log(n), branches(), current_branch(), diff()",
            config_schema={"repo": "path to the git repository"},
            tags=["git", "vcs"],
        )

    # -- runner -----------------------------------------------------------

    def _default_runner(self, args: list[str], cwd: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30,
        )

    def _repo(self) -> str:
        return self.config("repo") or "."

    def _git(self, *args: str) -> str:
        self.require(Permission.PROCESS_SPAWN)
        proc = self._runner(list(args), self._repo())
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or "git error").strip())
        return (proc.stdout or "").strip()

    # -- actions ----------------------------------------------------------

    @action
    def status(self) -> list[str]:
        out = self._git("status", "--porcelain")
        return [line for line in out.splitlines() if line]

    @action
    def current_branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD")

    @action
    def branches(self) -> list[str]:
        out = self._git("branch", "--format=%(refname:short)")
        return [b for b in out.splitlines() if b]

    @action
    def log(self, n: int = 10) -> list[dict[str, str]]:
        out = self._git("log", f"-{int(n)}", "--pretty=format:%h\x1f%an\x1f%s")
        rows = []
        for line in out.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 3:
                rows.append({"hash": parts[0], "author": parts[1], "subject": parts[2]})
        return rows

    @action
    def diff(self, path: str | None = None) -> str:
        args = ["diff", "--stat"]
        if path:
            args.append(path)
        return self._git(*args)

    def health(self) -> PluginHealth:
        try:
            self.require(Permission.PROCESS_SPAWN)
        except Exception:
            return self.health_of(HealthState.DEGRADED, "process.spawn not granted")
        try:
            proc = self._runner(["--version"], self._repo())
            if proc.returncode == 0:
                return self.health_of(HealthState.HEALTHY, (proc.stdout or "").strip())
            return self.health_of(HealthState.UNAVAILABLE, "git not available")
        except Exception as exc:  # noqa: BLE001
            return self.health_of(HealthState.UNAVAILABLE, str(exc))
