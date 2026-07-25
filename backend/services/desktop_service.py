"""
DesktopService for Aisha AI Assistant (Phase 11).

Facade over :mod:`desktop_awareness` (Phase 3/4).  **Read-only** by design:
this service exposes what AISHA can *observe* about the desktop (active
window, activity category, focus session). Governed *actions* -- launching
apps, window management, screenshots, and the rest of Production Milestone
"Computer Control" -- are a separate, larger increment that must be wired
through Human Oversight, the Automation Governor, the Rollback Registry and
Audit Logs before anything here is allowed to touch the OS. Bolting control
actions onto a read-only awareness facade without that governance would
violate the project's own "no action bypasses governance" rule, so it is
deliberately out of scope for this service.
"""

from __future__ import annotations

from typing import Any

from .base import BaseService, ServiceHealth, ServiceResult, ServiceState


class DesktopService(BaseService):
    """Read-only facade over desktop awareness."""

    name = "desktop"

    def __init__(self, awareness: Any | None = None) -> None:
        self._awareness = awareness

    @property
    def awareness(self) -> Any:
        if self._awareness is None:
            from desktop_awareness import desktop_awareness
            self._awareness = desktop_awareness
        return self._awareness

    # -- Queries ------------------------------------------------------------------

    def current_activity(self) -> ServiceResult:
        return self._call("current_activity", self.awareness.get_current_activity)

    def status(self) -> ServiceResult:
        return self._call("status", self.awareness.get_status)

    def session(self) -> ServiceResult:
        return self._call("session", self.awareness.get_session)

    def workflow(self) -> ServiceResult:
        return self._call("workflow", self.awareness.get_workflow)

    def is_coding(self) -> ServiceResult:
        return self._call("is_coding", self.awareness.is_coding)

    def is_deep_work(self) -> ServiceResult:
        return self._call("is_deep_work", self.awareness.is_deep_work)

    def poll(self) -> ServiceResult:
        return self._call("poll", self.awareness.poll)

    # -- Health -----------------------------------------------------------------------

    def health(self) -> ServiceHealth:
        try:
            status = self.awareness.get_status()
        except Exception as exc:  # noqa: BLE001
            return ServiceHealth(self.name, ServiceState.UNAVAILABLE, str(exc))
        return ServiceHealth(self.name, ServiceState.HEALTHY, str(status)[:80])
