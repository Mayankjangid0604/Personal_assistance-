"""
Filesystem Plugin (Phase 10, built-in).

Permission-gated file access confined to a configurable set of allowed root
directories (a "path jail").  Every operation:

* requires the appropriate permission (``fs.read`` / ``fs.write``) via the
  broker, and
* resolves the target and verifies it stays inside an allowed root, defeating
  ``..`` traversal and symlink escapes.

Configure allowed roots via plugin config ``{"roots": ["/path/one", ...]}``.
With no roots configured it defaults to the current working directory.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from ..base import Capability, HealthState, PluginHealth, PluginManifest, Permission
from ..sdk import SimplePlugin, action


class FilesystemPlugin(SimplePlugin):
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="filesystem",
            version="1.0.0",
            capabilities=[Capability.FILESYSTEM],
            permissions=[Permission.FS_READ, Permission.FS_WRITE],
            description="Sandboxed file read/write/list confined to allowed roots.",
            documentation=(
                "config: {roots: [dir,...]}. actions: list(dir), read(path), "
                "write(path, content), delete(path), mkdir(path), exists(path)"
            ),
            config_schema={"roots": "list[str] of allowed directories"},
            tags=["files", "io"],
        )

    # -- path jail --------------------------------------------------------

    def _roots(self) -> list[Path]:
        roots = self.config("roots") or [os.getcwd()]
        return [Path(r).resolve() for r in roots]

    def _resolve(self, path: str) -> Path:
        roots = self._roots()
        p = Path(path)
        # Relative paths are anchored to the first allowed root (the working
        # root), never to the process cwd.
        if not p.is_absolute():
            base = roots[0] if roots else Path.cwd().resolve()
            target = (base / p).resolve()
        else:
            target = p.resolve()
        for root in roots:
            try:
                target.relative_to(root)
                return target
            except ValueError:
                continue
        raise PermissionError(f"path {path!r} is outside allowed roots")

    # -- actions ----------------------------------------------------------

    @action
    def list(self, directory: str = ".") -> list[dict[str, Any]]:
        self.require(Permission.FS_READ)
        target = self._resolve(directory)
        if not target.is_dir():
            raise NotADirectoryError(f"{directory!r} is not a directory")
        entries = []
        for child in sorted(target.iterdir()):
            entries.append({
                "name": child.name,
                "is_dir": child.is_dir(),
                "size": child.stat().st_size if child.is_file() else None,
            })
        return entries

    @action
    def read(self, path: str, max_bytes: int = 1_000_000) -> str:
        self.require(Permission.FS_READ)
        target = self._resolve(path)
        with open(target, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(max_bytes)

    @action
    def exists(self, path: str) -> bool:
        self.require(Permission.FS_READ)
        try:
            return self._resolve(path).exists()
        except PermissionError:
            return False

    @action
    def write(self, path: str, content: str) -> dict[str, Any]:
        self.require(Permission.FS_WRITE)
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(content)
        return {"path": str(target), "bytes": len(content.encode("utf-8"))}

    @action
    def mkdir(self, path: str) -> dict[str, Any]:
        self.require(Permission.FS_WRITE)
        target = self._resolve(path)
        target.mkdir(parents=True, exist_ok=True)
        return {"path": str(target), "created": True}

    @action
    def delete(self, path: str) -> dict[str, Any]:
        self.require(Permission.FS_WRITE)
        target = self._resolve(path)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        else:
            return {"path": str(target), "deleted": False}
        return {"path": str(target), "deleted": True}

    def health(self) -> PluginHealth:
        roots = self._roots()
        ok = all(r.exists() for r in roots) if roots else True
        detail = f"{len(roots)} allowed root(s)"
        return self.health_of(HealthState.HEALTHY if ok else HealthState.DEGRADED, detail)
