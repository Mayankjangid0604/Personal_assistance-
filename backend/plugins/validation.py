"""
Plugin Validation & Version Utilities for Aisha (Phase 10).

Validates manifests before a plugin is admitted to the registry, and provides
lightweight semantic-version comparison for dependency resolution.  Keeping
this separate keeps the manager focused on lifecycle.
"""

from __future__ import annotations

import re
from typing import Any

from .base import Capability, Permission, Plugin, PluginManifest


_NAME_RE = re.compile(r"^[a-z][a-z0-9_\-]{1,39}$")
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


class ValidationError(Exception):
    """Raised when a plugin or manifest fails validation."""


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse a semver-ish string into a comparable ``(major, minor, patch)``."""
    m = _SEMVER_RE.match(version or "")
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def version_satisfies(installed: str, required: str) -> bool:
    """
    Return True if *installed* satisfies *required*.

    Supports ``>=x.y.z``, ``>x.y.z``, ``==x.y.z``, ``<=``, ``<`` and a bare
    version (treated as ``>=``).  Unknown formats default to True (permissive).
    """
    required = (required or "").strip()
    if not required:
        return True
    for op in (">=", "<=", "==", ">", "<"):
        if required.startswith(op):
            want = parse_version(required[len(op):].strip())
            have = parse_version(installed)
            if op == ">=":
                return have >= want
            if op == "<=":
                return have <= want
            if op == "==":
                return have == want
            if op == ">":
                return have > want
            if op == "<":
                return have < want
    return parse_version(installed) >= parse_version(required)


def validate_manifest(manifest: PluginManifest) -> list[str]:
    """Return a list of problems with *manifest* (empty == valid)."""
    problems: list[str] = []

    if not manifest.name or not _NAME_RE.match(manifest.name):
        problems.append(
            f"invalid name {manifest.name!r} (lowercase, 2-40 chars, [a-z0-9_-])"
        )
    if parse_version(manifest.version) == (0, 0, 0) and manifest.version != "0.0.0":
        problems.append(f"invalid version {manifest.version!r} (want semver x.y.z)")
    if not manifest.capabilities:
        problems.append("manifest declares no capabilities")
    for cap in manifest.capabilities:
        if not isinstance(cap, Capability):
            problems.append(f"capability {cap!r} is not a Capability")
    for perm in manifest.permissions:
        if not isinstance(perm, Permission):
            problems.append(f"permission {perm!r} is not a Permission")
    return problems


def validate_plugin(plugin: Plugin) -> list[str]:
    """Validate a plugin instance: manifest + action wiring."""
    problems: list[str] = []
    try:
        manifest = plugin.manifest()
    except Exception as exc:  # noqa: BLE001
        return [f"manifest() raised: {exc}"]

    problems.extend(validate_manifest(manifest))

    try:
        actions = plugin.actions()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"actions() raised: {exc}")
        actions = {}

    if not actions:
        problems.append("plugin exposes no actions")
    for name, fn in actions.items():
        if not callable(fn):
            problems.append(f"action {name!r} is not callable")
    return problems


def assert_valid(plugin: Plugin) -> None:
    """Raise :class:`ValidationError` if *plugin* is invalid."""
    problems = validate_plugin(plugin)
    if problems:
        raise ValidationError(
            f"{getattr(plugin, 'name', plugin.__class__.__name__)}: "
            + "; ".join(problems)
        )
