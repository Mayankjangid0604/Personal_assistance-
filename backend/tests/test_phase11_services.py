"""
Phase 11 -- Service Layer (Production Integration Layer) test suite.

Every service is exercised with an injected fake/stub dependency, so this
suite is fast, deterministic, and never touches the real SQLite database or
OS (no test here mutates ``database/aisha.db``). One integration test in
``TestRealDefaults`` verifies the lazy-default wiring resolves to real
subsystem singletons, using only read-only calls.

Run::

    python backend/tests/test_phase11_services.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_BACKEND)
for p in (_BACKEND, os.path.join(_ROOT, "database")):
    if p not in sys.path:
        sys.path.insert(0, p)

from services import (
    AgentService,
    BaseService,
    ConfigurationService,
    DesktopService,
    MemoryService,
    NotificationBackend,
    NotificationService,
    PluginService,
    ProviderService,
    ServiceContainer,
    ServiceHealth,
    ServiceResult,
    ServiceState,
    WorkspaceService,
    build_default_container,
    get_services,
    reset_services,
)


# ===========================================================================
# Fakes
# ===========================================================================

class FakeMemory:
    """Stand-in for database.memory.Memory."""

    def __init__(self):
        self.short_term = []
        self.long_term = {}
        self.short_term_capacity = 20

    class _Entry:
        def __init__(self, u, r, resp):
            self.user_input, self.role, self.response = u, r, resp
        def to_dict(self):
            return {"user_input": self.user_input, "role": self.role, "response": self.response}

    def add_conversation(self, user_input, role, response):
        entry = self._Entry(user_input, role, response)
        self.short_term.append(entry)
        return entry

    def get_recent_conversations(self):
        return list(self.short_term)

    def get_last_conversation(self):
        return self.short_term[-1] if self.short_term else None

    def clear_short_term(self):
        self.short_term.clear()

    def save_user_info(self, key, value):
        self.long_term[key] = value

    def get_user_info(self, key):
        return self.long_term.get(key)

    def get_all_user_info(self):
        return dict(self.long_term)

    def delete_user_info(self, key):
        return self.long_term.pop(key, None) is not None

    def clear_long_term(self):
        self.long_term.clear()

    @property
    def short_term_count(self):
        return len(self.short_term)


class FakePluginManager:
    def __init__(self, active=True):
        self._active = active
        class _Registry:
            def names(self_inner): return ["fake"]
        self.registry = _Registry()

    def manifests(self): return [{"name": "fake", "version": "1.0.0"}]
    def capability_index(self): return {"calculator": ["fake"]}
    def status_report(self): return {"fake": "active" if self._active else "unloaded"}
    def health_report(self): return {"fake": {"state": "healthy"}}
    def load(self, name): return _PR(True, "loaded")
    def unload(self, name): return _PR(True, "unloaded")
    def reload(self, name): return _PR(True, "reloaded")
    def enable(self, name): return _PR(True, "enabled")
    def disable(self, name): return _PR(True, "disabled")
    def status(self, name):
        class S:
            value = "active" if self._active else "unloaded"
        return S()

    def invoke(self, plugin, action, *a, **kw):
        if plugin == "fake" and action == "echo":
            return _PR(True, a[0] if a else None)
        return _PR(False, None, error="no such action")


class _PR:
    """Minimal PluginResult-shaped stub."""
    def __init__(self, ok, data=None, error=None):
        self.ok, self.data, self.error, self.meta = ok, data, error, {}


class FakeProviderRegistry:
    def __init__(self, healthy_names=("local",)):
        self._healthy = set(healthy_names)
        self._all = ["local", "ollama", "gemini"]

    def names(self): return list(self._all)
    def is_healthy(self, name): return name in self._healthy

    def generate(self, prompt, **kw):
        class R:
            ok = True; text = f"echo: {prompt}"; provider = "local"; model = "rule-based"
            latency_ms = 0.1; error = None
        return R()

    def generate_stream(self, prompt, **kw):
        yield "chunk-a"
        yield "chunk-b"

    def route(self, task):
        class D:
            provider, model, reason, task_ = "local", "rule-based", "last_resort", task
            def __repr__(self): return "route"
        return D()

    def set_override(self, name): return {"override": name}
    def capability_registry(self): return {"general": ["local"]}
    def latency_report(self): return {"local": {"avg_ms": 1.0}}
    def health_report(self, force=False): return {"local": {"status": "healthy"}}


class FakeNotificationBackend(NotificationBackend):
    def __init__(self):
        self._items = []
        super().__init__(
            add=self._add, list=self._list, unread_count=self._unread,
            mark_all_read=self._mark_read, clear=self._clear,
        )

    def _add(self, message, category="general", source="system"):
        item = {"message": message, "category": category, "source": source, "read": False}
        self._items.append(item)
        return item

    def _list(self, unread_only=False, limit=20):
        items = [i for i in self._items if not i["read"]] if unread_only else self._items
        return items[:limit]

    def _unread(self):
        return sum(1 for i in self._items if not i["read"])

    def _mark_read(self):
        n = self._unread()
        for i in self._items:
            i["read"] = True
        return n

    def _clear(self):
        n = len(self._items)
        self._items.clear()
        return n


class FakeWorkspace:
    def __init__(self):
        self._ws = {}
        self._next = 1

    def create_workspace(self, title, description=""):
        wid = self._next; self._next += 1
        self._ws[wid] = {"id": wid, "title": title, "nodes": []}
        return self._ws[wid]

    def add_node(self, workspace_id, content, node_type="note"):
        node = {"id": len(self._ws[workspace_id]["nodes"]) + 1, "content": content, "type": node_type}
        self._ws[workspace_id]["nodes"].append(node)
        return node

    def link_nodes(self, a, b, relation="related"):
        return {"a": a, "b": b, "relation": relation}

    def get_workspace(self, workspace_id):
        return self._ws.get(workspace_id)

    def get_active_workspaces(self):
        return list(self._ws.values())

    def search_nodes(self, query):
        return [n for ws in self._ws.values() for n in ws["nodes"] if query in n["content"]]

    def summarize_workspace(self, workspace_id):
        return f"workspace {workspace_id} summary"

    def get_status(self):
        return {"total_workspaces": len(self._ws)}


class FakeAgent:
    def __init__(self, name):
        self._name = name
    @property
    def name(self):
        return self._name


class FakeCoordinator:
    def __init__(self):
        self.agents = [FakeAgent("alpha"), FakeAgent("beta")]
        self._log = [{"decision": "resolved"}]

    def gather(self, user_input, system_context=None):
        return {"contributions": len(self.agents), "input": user_input}

    def get_arbitration_logs(self):
        return list(self._log)


class FakeAwareness:
    def get_current_activity(self): return {"category": "coding"}
    def get_status(self): return {"category": "coding", "deep_work": True}
    def get_session(self): return {"duration": 300}
    def get_workflow(self): return {"pattern": "focused"}
    def is_coding(self): return True
    def is_deep_work(self): return True
    def poll(self): return {"polled": True}


# ===========================================================================
# base.py
# ===========================================================================

class TestBase(unittest.TestCase):
    def test_result_success(self):
        r = ServiceResult.success("x")
        self.assertTrue(r.ok)
        self.assertEqual(r.data, "x")

    def test_result_failure(self):
        r = ServiceResult.failure("boom")
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "boom")

    def test_health_available(self):
        h = ServiceHealth("s", ServiceState.HEALTHY)
        self.assertTrue(h.available)
        self.assertFalse(ServiceHealth("s", ServiceState.UNAVAILABLE).available)
        self.assertTrue(ServiceHealth("s", ServiceState.DEGRADED).available)

    def test_base_service_call_wraps_exception(self):
        class S(BaseService):
            name = "x"
        s = S()
        def boom(): raise ValueError("nope")
        r = s._call("boom", boom)
        self.assertFalse(r.ok)
        self.assertIn("nope", r.error)

    def test_base_service_call_wraps_bare_value(self):
        class S(BaseService):
            name = "x"
        s = S()
        r = s._call("id", lambda v: v, 42)
        self.assertTrue(r.ok)
        self.assertEqual(r.data, 42)

    def test_base_service_call_passes_through_service_result(self):
        class S(BaseService):
            name = "x"
        s = S()
        inner = ServiceResult.success("already wrapped")
        r = s._call("act", lambda: inner)
        self.assertEqual(r.data, "already wrapped")
        self.assertEqual(r.service, "x")
        self.assertEqual(r.action, "act")


# ===========================================================================
# ConfigurationService
# ===========================================================================

class TestConfigurationService(unittest.TestCase):
    def test_defaults(self):
        c = ConfigurationService()
        self.assertEqual(c.get("ui.theme"), "dark")

    def test_set_get_runtime_override(self):
        c = ConfigurationService()
        c.set("ui.theme", "light")
        self.assertEqual(c.get("ui.theme"), "light")

    def test_unknown_key_default(self):
        c = ConfigurationService()
        self.assertEqual(c.get("does.not.exist", "fallback"), "fallback")

    def test_env_overrides_file(self):
        os.environ["AISHA_UI_THEME"] = "solarized"
        try:
            c = ConfigurationService()
            self.assertEqual(c.get("ui.theme"), "solarized")
        finally:
            del os.environ["AISHA_UI_THEME"]

    def test_runtime_beats_env(self):
        os.environ["AISHA_UI_THEME"] = "solarized"
        try:
            c = ConfigurationService()
            c.set("ui.theme", "override-wins")
            self.assertEqual(c.get("ui.theme"), "override-wins")
        finally:
            del os.environ["AISHA_UI_THEME"]

    def test_persist_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cfg.json"
            c = ConfigurationService(path=path)
            c.set("custom.key", "value", persist=True)
            c2 = ConfigurationService(path=path)
            self.assertEqual(c2.get("custom.key"), "value")

    def test_export_import(self):
        c = ConfigurationService()
        c.set("a.b", 1)
        dump = c.export_dict()
        c2 = ConfigurationService()
        c2.import_dict(dump)
        self.assertEqual(c2.get("a.b"), 1)

    def test_unset(self):
        c = ConfigurationService()
        c.set("x.y", "z")
        c.unset("x.y")
        self.assertIsNone(c.get("x.y"))

    def test_health(self):
        h = ConfigurationService().health()
        self.assertEqual(h.state, ServiceState.HEALTHY)

    def test_all_merges_layers(self):
        c = ConfigurationService()
        c.set("new.key", "v")
        merged = c.all()
        self.assertIn("ui.theme", merged)
        self.assertIn("new.key", merged)


# ===========================================================================
# ProviderService
# ===========================================================================

class TestProviderService(unittest.TestCase):
    def setUp(self):
        self.svc = ProviderService(registry=FakeProviderRegistry())

    def test_generate(self):
        r = self.svc.generate("hello")
        self.assertTrue(r.ok)
        self.assertIn("hello", r.data)
        self.assertEqual(r.meta["provider"], "local")

    def test_stream(self):
        chunks = list(self.svc.stream("hi"))
        self.assertEqual(chunks, ["chunk-a", "chunk-b"])

    def test_route(self):
        r = self.svc.route("coding")
        self.assertTrue(r.ok)

    def test_capability_registry(self):
        r = self.svc.capability_registry()
        self.assertIn("general", r.data)

    def test_latency_report(self):
        r = self.svc.latency_report()
        self.assertIn("local", r.data)

    def test_names(self):
        self.assertEqual(self.svc.names(), ["local", "ollama", "gemini"])

    def test_health(self):
        h = self.svc.health()
        self.assertEqual(h.state, ServiceState.HEALTHY)
        self.assertIn("1/3", h.detail)

    def test_health_no_providers(self):
        svc = ProviderService(registry=FakeProviderRegistry(healthy_names=()))
        # still "registered" (3 names) but none healthy -> degraded
        h = svc.health()
        self.assertEqual(h.state, ServiceState.DEGRADED)

    def test_lazy_default_resolution(self):
        svc = ProviderService()  # no injection -> resolves real providers.get_registry()
        self.assertIsNotNone(svc.registry)


# ===========================================================================
# PluginService
# ===========================================================================

class TestPluginService(unittest.TestCase):
    def setUp(self):
        self.svc = PluginService(manager=FakePluginManager())

    def test_list_plugins(self):
        r = self.svc.list_plugins()
        self.assertEqual(r.data[0]["name"], "fake")

    def test_invoke_success(self):
        r = self.svc.invoke("fake", "echo", "hi")
        self.assertTrue(r.ok)
        self.assertEqual(r.data, "hi")
        self.assertEqual(r.action, "fake.echo")

    def test_invoke_failure(self):
        r = self.svc.invoke("fake", "nope")
        self.assertFalse(r.ok)

    def test_lifecycle_calls(self):
        for method in ("load", "unload", "reload", "enable", "disable"):
            r = getattr(self.svc, method)("fake")
            self.assertTrue(r.ok)

    def test_health_active(self):
        h = self.svc.health()
        self.assertEqual(h.state, ServiceState.HEALTHY)

    def test_health_no_active(self):
        svc = PluginService(manager=FakePluginManager(active=False))
        h = svc.health()
        self.assertEqual(h.state, ServiceState.DEGRADED)


# ===========================================================================
# MemoryService
# ===========================================================================

class TestMemoryService(unittest.TestCase):
    def setUp(self):
        self.svc = MemoryService(memory=FakeMemory())

    def test_add_and_recent(self):
        self.svc.add_conversation("hi", "assistant", "hello")
        r = self.svc.recent_conversations()
        self.assertEqual(len(r.data), 1)

    def test_last_conversation(self):
        self.svc.add_conversation("a", "assistant", "b")
        r = self.svc.last_conversation()
        self.assertEqual(r.data["user_input"], "a")

    def test_last_conversation_empty(self):
        r = self.svc.last_conversation()
        self.assertIsNone(r.data)

    def test_clear_short_term(self):
        self.svc.add_conversation("a", "assistant", "b")
        self.svc.clear_short_term()
        r = self.svc.recent_conversations()
        self.assertEqual(r.data, [])

    def test_user_info_roundtrip(self):
        self.svc.save_user_info("name", "Mayank")
        r = self.svc.get_user_info("name")
        self.assertEqual(r.data, "Mayank")

    def test_all_user_info(self):
        self.svc.save_user_info("a", 1)
        r = self.svc.all_user_info()
        self.assertEqual(r.data["a"], 1)

    def test_delete_user_info(self):
        self.svc.save_user_info("a", 1)
        r = self.svc.delete_user_info("a")
        self.assertTrue(r.data)

    def test_clear_long_term(self):
        self.svc.save_user_info("a", 1)
        self.svc.clear_long_term()
        r = self.svc.all_user_info()
        self.assertEqual(r.data, {})

    def test_health(self):
        h = self.svc.health()
        self.assertEqual(h.state, ServiceState.HEALTHY)


# ===========================================================================
# NotificationService
# ===========================================================================

class TestNotificationService(unittest.TestCase):
    def setUp(self):
        self.svc = NotificationService(backend=FakeNotificationBackend())

    def test_notify_and_list(self):
        self.svc.notify("hello")
        r = self.svc.list()
        self.assertEqual(len(r.data), 1)

    def test_unread_count(self):
        self.svc.notify("a"); self.svc.notify("b")
        r = self.svc.unread_count()
        self.assertEqual(r.data, 2)

    def test_mark_all_read(self):
        self.svc.notify("a")
        self.svc.mark_all_read()
        r = self.svc.unread_count()
        self.assertEqual(r.data, 0)

    def test_clear(self):
        self.svc.notify("a")
        self.svc.clear()
        r = self.svc.list()
        self.assertEqual(r.data, [])

    def test_health(self):
        self.svc.notify("a")
        h = self.svc.health()
        self.assertIn("1 unread", h.detail)


# ===========================================================================
# WorkspaceService
# ===========================================================================

class TestWorkspaceService(unittest.TestCase):
    def setUp(self):
        self.svc = WorkspaceService(workspace=FakeWorkspace())

    def test_create_and_get(self):
        r = self.svc.create_workspace("Research")
        wid = r.data["id"]
        got = self.svc.get_workspace(wid)
        self.assertEqual(got.data["title"], "Research")

    def test_add_node_and_search(self):
        wid = self.svc.create_workspace("R").data["id"]
        self.svc.add_node(wid, "quantum computing notes")
        r = self.svc.search_nodes("quantum")
        self.assertEqual(len(r.data), 1)

    def test_link_nodes(self):
        r = self.svc.link_nodes(1, 2, "supports")
        self.assertEqual(r.data["relation"], "supports")

    def test_active_workspaces(self):
        self.svc.create_workspace("A")
        self.svc.create_workspace("B")
        r = self.svc.active_workspaces()
        self.assertEqual(len(r.data), 2)

    def test_summarize(self):
        wid = self.svc.create_workspace("R").data["id"]
        r = self.svc.summarize(wid)
        self.assertIn("summary", r.data)

    def test_health(self):
        h = self.svc.health()
        self.assertEqual(h.state, ServiceState.HEALTHY)


# ===========================================================================
# AgentService
# ===========================================================================

class TestAgentService(unittest.TestCase):
    def setUp(self):
        self.svc = AgentService(coordinator=FakeCoordinator())

    def test_gather(self):
        r = self.svc.gather("hello", {"ctx": 1})
        self.assertEqual(r.data["contributions"], 2)

    def test_arbitration_log(self):
        r = self.svc.arbitration_log()
        self.assertEqual(r.data[0]["decision"], "resolved")

    def test_agent_names(self):
        self.assertEqual(self.svc.agent_names(), ["alpha", "beta"])

    def test_health(self):
        h = self.svc.health()
        self.assertEqual(h.state, ServiceState.HEALTHY)
        self.assertIn("alpha", h.detail)

    def test_health_no_agents(self):
        class Empty:
            agents = []
        h = AgentService(coordinator=Empty()).health()
        self.assertEqual(h.state, ServiceState.UNAVAILABLE)


# ===========================================================================
# DesktopService (read-only)
# ===========================================================================

class TestDesktopService(unittest.TestCase):
    def setUp(self):
        self.svc = DesktopService(awareness=FakeAwareness())

    def test_current_activity(self):
        r = self.svc.current_activity()
        self.assertEqual(r.data["category"], "coding")

    def test_is_coding(self):
        self.assertTrue(self.svc.is_coding().data)

    def test_is_deep_work(self):
        self.assertTrue(self.svc.is_deep_work().data)

    def test_session_and_workflow(self):
        self.assertEqual(self.svc.session().data["duration"], 300)
        self.assertEqual(self.svc.workflow().data["pattern"], "focused")

    def test_poll(self):
        self.assertTrue(self.svc.poll().data["polled"])

    def test_health(self):
        h = self.svc.health()
        self.assertEqual(h.state, ServiceState.HEALTHY)

    def test_no_write_actions_exposed(self):
        """DesktopService is intentionally read-only (Milestone 2 is separate)."""
        write_like = {"launch", "close", "kill", "click", "type", "move_window"}
        exposed = {m for m in dir(self.svc) if not m.startswith("_")}
        self.assertEqual(exposed & write_like, set())


# ===========================================================================
# ServiceContainer
# ===========================================================================

class TestServiceContainer(unittest.TestCase):
    def test_manual_construction_with_fakes(self):
        container = ServiceContainer(
            config=ConfigurationService(),
            providers=ProviderService(registry=FakeProviderRegistry()),
            plugins=PluginService(manager=FakePluginManager()),
            memory=MemoryService(memory=FakeMemory()),
            notifications=NotificationService(backend=FakeNotificationBackend()),
            workspace=WorkspaceService(workspace=FakeWorkspace()),
            agents=AgentService(coordinator=FakeCoordinator()),
            desktop=DesktopService(awareness=FakeAwareness()),
        )
        report = container.health_report()
        self.assertEqual(len(report), 8)
        self.assertTrue(all(v["available"] for v in report.values()))

    def test_health_report_survives_one_broken_service(self):
        class Broken:
            def health(self):
                raise RuntimeError("dead")
        container = ServiceContainer(
            config=ConfigurationService(),
            providers=ProviderService(registry=FakeProviderRegistry()),
            plugins=PluginService(manager=FakePluginManager()),
            memory=Broken(),
            notifications=NotificationService(backend=FakeNotificationBackend()),
            workspace=WorkspaceService(workspace=FakeWorkspace()),
            agents=AgentService(coordinator=FakeCoordinator()),
            desktop=DesktopService(awareness=FakeAwareness()),
        )
        report = container.health_report()
        self.assertFalse(report["memory"]["available"])
        self.assertTrue(report["configuration"]["available"])  # others unaffected


class TestRealDefaults(unittest.TestCase):
    """Integration: lazy defaults resolve to the real subsystems (read-only calls)."""

    def tearDown(self):
        reset_services()

    def test_build_default_container_all_lazy(self):
        reset_services()
        container = build_default_container()
        # nothing constructed eagerly except ConfigurationService
        self.assertIsInstance(container.config, ConfigurationService)

    def test_get_services_singleton(self):
        reset_services()
        s1 = get_services()
        s2 = get_services()
        self.assertIs(s1, s2)

    def test_provider_service_resolves_real_registry(self):
        svc = ProviderService()
        self.assertTrue(len(svc.names()) > 0)

    def test_plugin_service_resolves_real_manager(self):
        svc = PluginService()
        r = svc.list_plugins()
        self.assertTrue(r.ok)
        self.assertTrue(len(r.data) > 0)

    def test_desktop_service_resolves_real_awareness_readonly(self):
        svc = DesktopService()
        h = svc.health()
        self.assertIn(h.state, (ServiceState.HEALTHY, ServiceState.DEGRADED, ServiceState.UNAVAILABLE))


if __name__ == "__main__":
    unittest.main(verbosity=2)
