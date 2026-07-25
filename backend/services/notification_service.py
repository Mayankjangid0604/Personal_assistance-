"""
NotificationService for Aisha AI Assistant (Phase 11).

Facade over :mod:`notifications` (add/list/read/clear).  The wrapped
functions are injected as a small callable bundle so tests never touch the
real SQLite-backed notification repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .base import BaseService, ServiceHealth, ServiceResult, ServiceState


@dataclass
class NotificationBackend:
    """The four functions this service needs -- swappable for tests."""

    add: Callable[..., dict[str, Any]]
    list: Callable[..., list[dict[str, Any]]]
    unread_count: Callable[[], int]
    mark_all_read: Callable[[], int]
    clear: Callable[[], int]

    @classmethod
    def real(cls) -> "NotificationBackend":
        import notifications as n
        return cls(
            add=n.add_notification,
            list=n.get_notifications,
            unread_count=n.get_unread_count,
            mark_all_read=n.mark_all_read,
            clear=n.clear_notifications,
        )


class NotificationService(BaseService):
    """Facade over the notification center."""

    name = "notification"

    def __init__(self, backend: NotificationBackend | None = None) -> None:
        self._backend = backend

    @property
    def backend(self) -> NotificationBackend:
        if self._backend is None:
            self._backend = NotificationBackend.real()
        return self._backend

    # -- Actions ------------------------------------------------------------------

    def notify(self, message: str, category: str = "general", source: str = "system") -> ServiceResult:
        return self._call("notify", self.backend.add, message, category, source)

    def list(self, *, unread_only: bool = False, limit: int = 20) -> ServiceResult:
        return self._call("list", self.backend.list, unread_only=unread_only, limit=limit)

    def unread_count(self) -> ServiceResult:
        return self._call("unread_count", self.backend.unread_count)

    def mark_all_read(self) -> ServiceResult:
        return self._call("mark_all_read", self.backend.mark_all_read)

    def clear(self) -> ServiceResult:
        return self._call("clear", self.backend.clear)

    # -- Health -----------------------------------------------------------------------

    def health(self) -> ServiceHealth:
        try:
            count = self.backend.unread_count()
        except Exception as exc:  # noqa: BLE001
            return ServiceHealth(self.name, ServiceState.UNAVAILABLE, str(exc))
        return ServiceHealth(self.name, ServiceState.HEALTHY, f"{count} unread")
