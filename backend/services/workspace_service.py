"""
WorkspaceService for Aisha AI Assistant (Phase 11).

Facade over :mod:`cognitive_workspace` (the shared idea-graph workspace from
Phase 7).  Accepts an injected workspace object for testability.
"""

from __future__ import annotations

from typing import Any

from .base import BaseService, ServiceHealth, ServiceResult, ServiceState


class WorkspaceService(BaseService):
    """Facade over a :class:`CognitiveWorkspace` instance."""

    name = "workspace"

    def __init__(self, workspace: Any | None = None) -> None:
        self._workspace = workspace

    @property
    def workspace(self) -> Any:
        if self._workspace is None:
            from cognitive_workspace import cognitive_workspace
            self._workspace = cognitive_workspace
        return self._workspace

    # -- Actions ------------------------------------------------------------------

    def create_workspace(self, title: str, description: str = "") -> ServiceResult:
        return self._call("create_workspace", self.workspace.create_workspace, title, description)

    def add_node(self, workspace_id: int, content: str, node_type: str = "note") -> ServiceResult:
        return self._call("add_node", self.workspace.add_node, workspace_id, content, node_type)

    def link_nodes(self, node_a: int, node_b: int, relation: str = "related") -> ServiceResult:
        return self._call("link_nodes", self.workspace.link_nodes, node_a, node_b, relation)

    def get_workspace(self, workspace_id: int) -> ServiceResult:
        return self._call("get_workspace", self.workspace.get_workspace, workspace_id)

    def active_workspaces(self) -> ServiceResult:
        return self._call("active_workspaces", self.workspace.get_active_workspaces)

    def search_nodes(self, query: str) -> ServiceResult:
        return self._call("search_nodes", self.workspace.search_nodes, query)

    def summarize(self, workspace_id: int) -> ServiceResult:
        return self._call("summarize", self.workspace.summarize_workspace, workspace_id)

    def status(self) -> ServiceResult:
        return self._call("status", self.workspace.get_status)

    # -- Health -----------------------------------------------------------------------

    def health(self) -> ServiceHealth:
        try:
            status = self.workspace.get_status()
        except Exception as exc:  # noqa: BLE001
            return ServiceHealth(self.name, ServiceState.UNAVAILABLE, str(exc))
        return ServiceHealth(self.name, ServiceState.HEALTHY, str(status)[:80])
