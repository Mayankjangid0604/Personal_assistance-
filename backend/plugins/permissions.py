"""
Permission Broker for Aisha's Plugin Platform (Phase 10).

Capability-based access control: a plugin can only exercise a privilege that
(a) it declared in its manifest, AND (b) has been granted for that plugin.
Every privileged operation calls :meth:`PermissionBroker.check`, which raises
:class:`PermissionDenied` when the grant is missing.

This is *capability gating*, the integration seam for Milestone 2's deeper
governance (Human Oversight / Automation Governor / Audit).  It is not OS-level
process isolation -- that is future work and is documented as such.  An
optional ``audit`` hook lets the caller record every decision.
"""

from __future__ import annotations

from typing import Any, Callable

from .base import Permission, PermissionDenied, coerce_permission


class PermissionBroker:
    """Tracks per-plugin permission grants and enforces them at call time."""

    def __init__(self, audit: Callable[[dict[str, Any]], None] | None = None) -> None:
        # plugin name -> set of granted permissions
        self._grants: dict[str, set[Permission]] = {}
        # plugin name -> set of permissions the manifest requested
        self._declared: dict[str, set[Permission]] = {}
        self._audit = audit

    # -- Declaration & granting ------------------------------------------

    def declare(self, plugin: str, permissions: list[Permission]) -> None:
        """Record the permissions a plugin's manifest requests."""
        self._declared[plugin] = {coerce_permission(p) for p in permissions}

    def grant(self, plugin: str, permission: Permission | str) -> None:
        """Grant *permission* to *plugin* (must have been declared)."""
        perm = coerce_permission(permission)
        declared = self._declared.get(plugin, set())
        if perm not in declared:
            raise PermissionDenied(
                f"{plugin}: cannot grant undeclared permission {perm.value!r}"
            )
        self._grants.setdefault(plugin, set()).add(perm)
        self._record(plugin, perm, "grant", True)

    def grant_all_declared(self, plugin: str) -> None:
        """Convenience: grant every permission the plugin declared."""
        for perm in self._declared.get(plugin, set()):
            self._grants.setdefault(plugin, set()).add(perm)

    def revoke(self, plugin: str, permission: Permission | str) -> None:
        perm = coerce_permission(permission)
        self._grants.get(plugin, set()).discard(perm)
        self._record(plugin, perm, "revoke", True)

    def revoke_all(self, plugin: str) -> None:
        self._grants.pop(plugin, None)

    # -- Enforcement ------------------------------------------------------

    def is_granted(self, plugin: str, permission: Permission | str) -> bool:
        perm = coerce_permission(permission)
        return perm in self._grants.get(plugin, set())

    def check(self, plugin: str, permission: Permission | str) -> None:
        """Raise :class:`PermissionDenied` unless *plugin* holds *permission*."""
        perm = coerce_permission(permission)
        granted = self.is_granted(plugin, perm)
        self._record(plugin, perm, "check", granted)
        if not granted:
            raise PermissionDenied(
                f"{plugin}: permission {perm.value!r} not granted"
            )

    def requirer_for(self, plugin: str) -> Callable[[Permission], None]:
        """Return a ``require(permission)`` closure bound to *plugin*."""
        def _require(permission: Permission) -> None:
            self.check(plugin, permission)
        return _require

    # -- Introspection ----------------------------------------------------

    def declared(self, plugin: str) -> set[Permission]:
        return set(self._declared.get(plugin, set()))

    def granted(self, plugin: str) -> set[Permission]:
        return set(self._grants.get(plugin, set()))

    def snapshot(self) -> dict[str, dict[str, list[str]]]:
        out: dict[str, dict[str, list[str]]] = {}
        for plugin in set(self._declared) | set(self._grants):
            out[plugin] = {
                "declared": sorted(p.value for p in self._declared.get(plugin, set())),
                "granted": sorted(p.value for p in self._grants.get(plugin, set())),
            }
        return out

    # -- Audit ------------------------------------------------------------

    def _record(self, plugin: str, permission: Permission, action: str, allowed: bool) -> None:
        if self._audit is None:
            return
        try:
            self._audit({
                "plugin": plugin,
                "permission": permission.value,
                "action": action,
                "allowed": allowed,
            })
        except Exception:
            pass  # auditing must never break enforcement
