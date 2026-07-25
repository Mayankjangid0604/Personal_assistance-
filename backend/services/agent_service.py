"""
AgentService for Aisha AI Assistant (Phase 11).

Facade over :mod:`distributed_agents` (the bounded, sandboxed multi-agent
system from Phase 8).  Accepts an injected coordinator for testability --
the real ``DistributedAgentSystem`` touches memory, projects, the knowledge
graph and more through its sandbox, so tests inject a stub coordinator.
"""

from __future__ import annotations

from typing import Any

from .base import BaseService, ServiceHealth, ServiceResult, ServiceState


class AgentService(BaseService):
    """Facade over the distributed cognitive agent coordinator."""

    name = "agent"

    def __init__(self, coordinator: Any | None = None) -> None:
        self._coordinator = coordinator

    @property
    def coordinator(self) -> Any:
        if self._coordinator is None:
            from distributed_agents import distributed_agent_system
            self._coordinator = distributed_agent_system
        return self._coordinator

    # -- Actions ------------------------------------------------------------------

    def gather(self, user_input: str, system_context: dict[str, Any] | None = None) -> ServiceResult:
        return self._call("gather", self.coordinator.gather, user_input, system_context)

    def arbitration_log(self) -> ServiceResult:
        return self._call("arbitration_log", self.coordinator.get_arbitration_logs)

    def agent_names(self) -> list[str]:
        try:
            return [a.name for a in self.coordinator.agents]
        except Exception:
            return []

    # -- Health -----------------------------------------------------------------------

    def health(self) -> ServiceHealth:
        try:
            names = self.agent_names()
        except Exception as exc:  # noqa: BLE001
            return ServiceHealth(self.name, ServiceState.UNAVAILABLE, str(exc))
        if not names:
            return ServiceHealth(self.name, ServiceState.UNAVAILABLE, "no agents registered")
        return ServiceHealth(self.name, ServiceState.HEALTHY, f"{len(names)} agents: {', '.join(names)}")
