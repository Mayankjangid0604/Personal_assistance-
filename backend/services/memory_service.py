"""
MemoryService for Aisha AI Assistant (Phase 11).

Facade over :class:`database.memory.Memory` (short-term conversation buffer +
long-term user-info key/value store).  Accepts an injected memory object so
callers (including tests) never have to touch the real SQLite-backed
singleton unless they choose to.
"""

from __future__ import annotations

from typing import Any

from .base import BaseService, ServiceHealth, ServiceResult, ServiceState


class MemoryService(BaseService):
    """Facade over a :class:`Memory` instance (short-term + long-term)."""

    name = "memory"

    def __init__(self, memory: Any | None = None) -> None:
        self._memory = memory  # lazily resolved if None

    @property
    def memory(self) -> Any:
        if self._memory is None:
            from memory import Memory
            self._memory = Memory()
        return self._memory

    # -- Conversations ------------------------------------------------------------

    def add_conversation(self, user_input: str, role: str, response: str) -> ServiceResult:
        def _add():
            return self.memory.add_conversation(user_input, role, response).to_dict()
        return self._call("add_conversation", _add)

    def recent_conversations(self) -> ServiceResult:
        def _fetch():
            return [c.to_dict() for c in self.memory.get_recent_conversations()]
        return self._call("recent_conversations", _fetch)

    def last_conversation(self) -> ServiceResult:
        def _fetch():
            last = self.memory.get_last_conversation()
            return last.to_dict() if last else None
        return self._call("last_conversation", _fetch)

    def clear_short_term(self) -> ServiceResult:
        return self._call("clear_short_term", self.memory.clear_short_term)

    # -- User info (long-term) -----------------------------------------------------

    def save_user_info(self, key: str, value: Any) -> ServiceResult:
        return self._call("save_user_info", self.memory.save_user_info, key, value)

    def get_user_info(self, key: str) -> ServiceResult:
        return self._call("get_user_info", self.memory.get_user_info, key)

    def all_user_info(self) -> ServiceResult:
        return self._call("all_user_info", self.memory.get_all_user_info)

    def delete_user_info(self, key: str) -> ServiceResult:
        return self._call("delete_user_info", self.memory.delete_user_info, key)

    def clear_long_term(self) -> ServiceResult:
        return self._call("clear_long_term", self.memory.clear_long_term)

    # -- Health -----------------------------------------------------------------------

    def health(self) -> ServiceHealth:
        try:
            count = self.memory.short_term_count
            cap = self.memory.short_term_capacity
        except Exception as exc:  # noqa: BLE001
            return ServiceHealth(self.name, ServiceState.UNAVAILABLE, str(exc))
        return ServiceHealth(self.name, ServiceState.HEALTHY, f"{count}/{cap} short-term entries")
