"""
Phase 10 -- Plugin Platform test suite.

Covers the plugin interface, manifest validation, registry, permission broker,
manager lifecycle (load/unload/hot-reload/dependency order), health monitoring,
the SDK, and every implemented built-in plugin (including permission denial and
filesystem path-jail escape prevention).  Runs fully offline.

Run::

    python backend/tests/test_phase10_plugins.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_BACKEND)
for p in (_BACKEND, os.path.join(_ROOT, "database")):
    if p not in sys.path:
        sys.path.insert(0, p)

import plugins as PL
from plugins import (
    Capability,
    Permission,
    PermissionDenied,
    PluginManager,
    PluginManifest,
    PluginRegistry,
    PermissionBroker,
    PluginConfigStore,
    PluginResult,
    PluginStatus,
    HealthState,
    SimplePlugin,
    action,
    validate_manifest,
    validate_plugin,
    version_satisfies,
    parse_version,
    build_default_manager,
)
from plugins.base import PluginHealth
from plugins.builtin import (
    CalculatorPlugin, FilesystemPlugin, ClipboardPlugin,
    SystemInfoPlugin, GitPlugin, register_builtins,
    IMPLEMENTED_PLUGINS, ALL_BUILTIN_PLUGINS,
)
from plugins.builtin.planned import PLANNED_PLUGINS


# ---------------------------------------------------------------------------
# Test plugins
# ---------------------------------------------------------------------------

class Echo(SimplePlugin):
    def manifest(self):
        return PluginManifest(
            name="echo", version="1.2.3",
            capabilities=[Capability.CALCULATOR],
            permissions=[Permission.SYSTEM_INFO],
            description="echoes input",
        )

    @action
    def say(self, text="hi"):
        return text

    @action
    def guarded(self):
        self.require(Permission.SYSTEM_INFO)
        return "secret"


class DependentPlugin(SimplePlugin):
    def manifest(self):
        return PluginManifest(
            name="dependent", version="1.0.0",
            capabilities=[Capability.SYSTEM],
            dependencies=["echo>=1.0.0"],
        )

    @action
    def go(self):
        return "ok"


# ===========================================================================
# base / manifest / validation
# ===========================================================================

class TestValidation(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(parse_version("2.3.4"), (2, 3, 4))
        self.assertEqual(parse_version("garbage"), (0, 0, 0))

    def test_version_satisfies_ge(self):
        self.assertTrue(version_satisfies("1.2.3", ">=1.0.0"))
        self.assertFalse(version_satisfies("0.9.0", ">=1.0.0"))

    def test_version_satisfies_ops(self):
        self.assertTrue(version_satisfies("1.0.0", "==1.0.0"))
        self.assertTrue(version_satisfies("2.0.0", ">1.0.0"))
        self.assertTrue(version_satisfies("1.0.0", "<=1.0.0"))
        self.assertTrue(version_satisfies("0.5.0", "<1.0.0"))

    def test_version_bare_is_ge(self):
        self.assertTrue(version_satisfies("1.5.0", "1.0.0"))

    def test_valid_manifest(self):
        self.assertEqual(validate_manifest(Echo().manifest()), [])

    def test_invalid_name(self):
        m = PluginManifest(name="Bad Name!", version="1.0.0", capabilities=[Capability.SYSTEM])
        self.assertTrue(any("name" in p for p in validate_manifest(m)))

    def test_no_capabilities(self):
        m = PluginManifest(name="x", version="1.0.0", capabilities=[])
        self.assertTrue(any("capabilit" in p for p in validate_manifest(m)))

    def test_validate_plugin_no_actions(self):
        class NoActions(SimplePlugin):
            def manifest(self):
                return PluginManifest(name="noact", version="1.0.0", capabilities=[Capability.SYSTEM])
        self.assertTrue(any("no actions" in p for p in validate_plugin(NoActions())))

    def test_assert_valid_raises(self):
        class Bad(SimplePlugin):
            def manifest(self):
                return PluginManifest(name="", version="x", capabilities=[])
            @action
            def a(self): return 1
        with self.assertRaises(PL.ValidationError):
            PL.assert_valid(Bad())


# ===========================================================================
# registry
# ===========================================================================

class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.reg = PluginRegistry()

    def test_register_get(self):
        e = Echo()
        self.reg.register(e)
        self.assertIs(self.reg.get("echo"), e)
        self.assertIn("echo", self.reg)
        self.assertEqual(len(self.reg), 1)

    def test_with_capability(self):
        self.reg.register(Echo())
        self.reg.register(SystemInfoPlugin())
        self.assertEqual([p.name for p in self.reg.with_capability(Capability.SYSTEM)], ["system_info"])

    def test_capability_index(self):
        self.reg.register(Echo())
        idx = self.reg.capability_index()
        self.assertIn("echo", idx["calculator"])

    def test_unregister_clear(self):
        self.reg.register(Echo())
        self.reg.unregister("echo")
        self.assertEqual(len(self.reg), 0)


# ===========================================================================
# permission broker
# ===========================================================================

class TestPermissionBroker(unittest.TestCase):
    def setUp(self):
        self.b = PermissionBroker()
        self.b.declare("p", [Permission.FS_READ, Permission.FS_WRITE])

    def test_grant_and_check(self):
        self.b.grant("p", Permission.FS_READ)
        self.assertTrue(self.b.is_granted("p", Permission.FS_READ))
        self.b.check("p", Permission.FS_READ)  # no raise

    def test_check_denied(self):
        with self.assertRaises(PermissionDenied):
            self.b.check("p", Permission.FS_READ)

    def test_grant_undeclared_raises(self):
        with self.assertRaises(PermissionDenied):
            self.b.grant("p", Permission.NETWORK)

    def test_grant_all_declared(self):
        self.b.grant_all_declared("p")
        self.assertTrue(self.b.is_granted("p", Permission.FS_WRITE))

    def test_revoke(self):
        self.b.grant("p", Permission.FS_READ)
        self.b.revoke("p", Permission.FS_READ)
        self.assertFalse(self.b.is_granted("p", Permission.FS_READ))

    def test_requirer_closure(self):
        req = self.b.requirer_for("p")
        with self.assertRaises(PermissionDenied):
            req(Permission.FS_READ)
        self.b.grant("p", Permission.FS_READ)
        req(Permission.FS_READ)  # no raise

    def test_audit_hook(self):
        events = []
        b = PermissionBroker(audit=events.append)
        b.declare("q", [Permission.FS_READ])
        b.grant("q", Permission.FS_READ)
        b.check("q", Permission.FS_READ)
        self.assertTrue(any(e["action"] == "check" and e["allowed"] for e in events))

    def test_snapshot(self):
        self.b.grant("p", Permission.FS_READ)
        snap = self.b.snapshot()
        self.assertIn("fs.read", snap["p"]["granted"])
        self.assertIn("fs.write", snap["p"]["declared"])


# ===========================================================================
# config store
# ===========================================================================

class TestConfigStore(unittest.TestCase):
    def test_set_get(self):
        c = PluginConfigStore()
        c.set("p", {"a": 1})
        self.assertEqual(c.get("p"), {"a": 1})
        self.assertEqual(c.get_value("p", "a"), 1)

    def test_update(self):
        c = PluginConfigStore()
        c.set("p", {"a": 1})
        c.update("p", b=2)
        self.assertEqual(c.get("p"), {"a": 1, "b": 2})

    def test_persist_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "cfg.json")
            c = PluginConfigStore(path=path)
            c.set("p", {"x": 9})
            c.save_file()
            c2 = PluginConfigStore(path=path)
            self.assertEqual(c2.get_value("p", "x"), 9)


# ===========================================================================
# manager lifecycle
# ===========================================================================

class TestManager(unittest.TestCase):
    def setUp(self):
        self.mgr = PluginManager()

    def test_register_status_discovered(self):
        self.mgr.register(Echo())
        self.assertEqual(self.mgr.status("echo"), PluginStatus.DISCOVERED)

    def test_load_activates(self):
        self.mgr.register(Echo())
        res = self.mgr.load("echo")
        self.assertTrue(res.ok)
        self.assertEqual(self.mgr.status("echo"), PluginStatus.ACTIVE)

    def test_invoke_action(self):
        self.mgr.register(Echo()); self.mgr.load("echo")
        r = self.mgr.invoke("echo", "say", "yo")
        self.assertTrue(r.ok)
        self.assertEqual(r.data, "yo")

    def test_invoke_unknown_action(self):
        self.mgr.register(Echo()); self.mgr.load("echo")
        r = self.mgr.invoke("echo", "nope")
        self.assertFalse(r.ok)

    def test_invoke_before_load(self):
        self.mgr.register(Echo())
        r = self.mgr.invoke("echo", "say")
        self.assertFalse(r.ok)
        self.assertIn("not loaded", r.error)

    def test_guarded_action_auto_granted(self):
        self.mgr.register(Echo()); self.mgr.load("echo")
        r = self.mgr.invoke("echo", "guarded")
        self.assertTrue(r.ok)  # auto_grant on by default
        self.assertEqual(r.data, "secret")

    def test_guarded_action_denied_without_grant(self):
        self.mgr.auto_grant = False
        self.mgr.register(Echo()); self.mgr.load("echo")
        r = self.mgr.invoke("echo", "guarded")
        self.assertFalse(r.ok)
        self.assertIn("permission denied", r.error.lower())

    def test_manual_grant_then_allowed(self):
        self.mgr.auto_grant = False
        self.mgr.register(Echo()); self.mgr.load("echo")
        self.mgr.broker.grant("echo", Permission.SYSTEM_INFO)
        r = self.mgr.invoke("echo", "guarded")
        self.assertTrue(r.ok)

    def test_unload(self):
        self.mgr.register(Echo()); self.mgr.load("echo")
        self.mgr.unload("echo")
        self.assertEqual(self.mgr.status("echo"), PluginStatus.UNLOADED)
        r = self.mgr.invoke("echo", "say")
        self.assertFalse(r.ok)

    def test_reload_hot(self):
        self.mgr.register(Echo()); self.mgr.load("echo")
        r = self.mgr.reload("echo")
        self.assertTrue(r.ok)
        self.assertEqual(self.mgr.status("echo"), PluginStatus.ACTIVE)

    def test_disable_enable(self):
        self.mgr.register(Echo()); self.mgr.load("echo")
        self.mgr.disable("echo")
        self.assertEqual(self.mgr.status("echo"), PluginStatus.DISABLED)
        self.mgr.enable("echo")
        self.assertEqual(self.mgr.status("echo"), PluginStatus.ACTIVE)

    def test_dependency_met(self):
        self.mgr.register(Echo())
        self.mgr.register(DependentPlugin())
        res = self.mgr.load("dependent")
        self.assertTrue(res.ok)

    def test_dependency_unmet(self):
        self.mgr.register(DependentPlugin())  # echo missing
        res = self.mgr.load("dependent")
        self.assertFalse(res.ok)
        self.assertIn("dependency", res.error)
        self.assertEqual(self.mgr.status("dependent"), PluginStatus.ERROR)

    def test_dependency_version_unmet(self):
        class OldEcho(Echo):
            def manifest(self):
                m = super().manifest(); m.version = "0.1.0"; return m
        self.mgr.register(OldEcho())
        self.mgr.register(DependentPlugin())
        res = self.mgr.load("dependent")
        self.assertFalse(res.ok)

    def test_load_all_dependency_order(self):
        self.mgr.register(DependentPlugin())
        self.mgr.register(Echo())
        results = self.mgr.load_all()
        self.assertTrue(all(r.ok for r in results.values()))

    def test_health_report(self):
        self.mgr.register(Echo()); self.mgr.load("echo")
        rep = self.mgr.health_report()
        self.assertIn("echo", rep)

    def test_status_report(self):
        self.mgr.register(Echo()); self.mgr.load("echo")
        self.assertEqual(self.mgr.status_report()["echo"], "active")

    def test_register_invalid_raises(self):
        class Bad(SimplePlugin):
            def manifest(self):
                return PluginManifest(name="", version="0", capabilities=[])
            @action
            def a(self): return 1
        with self.assertRaises(PL.ValidationError):
            self.mgr.register(Bad())

    def test_plugin_returning_pluginresult(self):
        class Direct(SimplePlugin):
            def manifest(self):
                return PluginManifest(name="direct", version="1.0.0", capabilities=[Capability.SYSTEM])
            @action
            def act(self):
                return PluginResult.success("explicit")
        self.mgr.register(Direct()); self.mgr.load("direct")
        r = self.mgr.invoke("direct", "act")
        self.assertTrue(r.ok)
        self.assertEqual(r.data, "explicit")
        self.assertEqual(r.plugin, "direct")


# ===========================================================================
# built-in: calculator
# ===========================================================================

class TestCalculator(unittest.TestCase):
    def setUp(self):
        self.mgr = PluginManager()
        self.mgr.register(CalculatorPlugin()); self.mgr.load("calculator")

    def _eval(self, expr):
        return self.mgr.invoke("calculator", "evaluate", expr)

    def test_arithmetic(self):
        self.assertEqual(self._eval("2 + 2 * 10").data, 22)

    def test_precedence_and_parens(self):
        self.assertEqual(self._eval("(2 + 2) * 10").data, 40)

    def test_functions(self):
        self.assertAlmostEqual(self._eval("sqrt(144)").data, 12.0)

    def test_constants(self):
        r = self.mgr.invoke("calculator", "constants")
        self.assertIn("pi", r.data)

    def test_rejects_names(self):
        r = self._eval("os")
        self.assertFalse(r.ok)

    def test_rejects_calls(self):
        r = self._eval("__import__('os').system('echo hi')")
        self.assertFalse(r.ok)

    def test_rejects_attribute(self):
        r = self._eval("(1).__class__")
        self.assertFalse(r.ok)

    def test_health(self):
        self.assertEqual(self.mgr.health("calculator").state, HealthState.HEALTHY)


# ===========================================================================
# built-in: filesystem (path jail)
# ===========================================================================

class TestFilesystem(unittest.TestCase):
    def setUp(self):
        self.mgr = PluginManager()
        self.tmp = tempfile.mkdtemp()
        self.mgr.register(FilesystemPlugin())
        self.mgr.config.set("filesystem", {"roots": [self.tmp]})
        self.mgr.load("filesystem")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_read(self):
        w = self.mgr.invoke("filesystem", "write", "a.txt", "hello")
        self.assertTrue(w.ok)
        r = self.mgr.invoke("filesystem", "read", "a.txt")
        self.assertEqual(r.data, "hello")

    def test_list(self):
        self.mgr.invoke("filesystem", "write", "a.txt", "x")
        r = self.mgr.invoke("filesystem", "list", ".")
        self.assertTrue(any(e["name"] == "a.txt" for e in r.data))

    def test_mkdir_and_exists(self):
        self.mgr.invoke("filesystem", "mkdir", "sub")
        r = self.mgr.invoke("filesystem", "exists", "sub")
        self.assertTrue(r.data)

    def test_delete(self):
        self.mgr.invoke("filesystem", "write", "a.txt", "x")
        self.mgr.invoke("filesystem", "delete", "a.txt")
        r = self.mgr.invoke("filesystem", "exists", "a.txt")
        self.assertFalse(r.data)

    def test_jail_blocks_absolute_escape(self):
        r = self.mgr.invoke("filesystem", "read", "/etc/passwd")
        self.assertFalse(r.ok)
        self.assertIn("outside allowed roots", r.error)

    def test_jail_blocks_traversal(self):
        r = self.mgr.invoke("filesystem", "read", "../../../../etc/passwd")
        self.assertFalse(r.ok)

    def test_permission_denied_without_grant(self):
        mgr = PluginManager(); mgr.auto_grant = False
        mgr.register(FilesystemPlugin())
        mgr.config.set("filesystem", {"roots": [self.tmp]})
        mgr.load("filesystem")
        r = mgr.invoke("filesystem", "write", "x.txt", "data")
        self.assertFalse(r.ok)
        self.assertIn("permission denied", r.error.lower())


# ===========================================================================
# built-in: clipboard
# ===========================================================================

class TestClipboard(unittest.TestCase):
    def test_memory_fallback(self):
        mgr = PluginManager()
        mgr.register(ClipboardPlugin()); mgr.load("clipboard")
        mgr.invoke("clipboard", "copy", "hi")
        r = mgr.invoke("clipboard", "paste")
        self.assertEqual(r.data, "hi")
        self.assertEqual(mgr.health("clipboard").state, HealthState.DEGRADED)

    def test_os_backend(self):
        store = {}
        p = ClipboardPlugin(backend_get=lambda: store.get("v", ""),
                            backend_set=lambda t: store.__setitem__("v", t))
        mgr = PluginManager()
        mgr.register(p); mgr.load("clipboard")
        mgr.invoke("clipboard", "copy", "world")
        self.assertEqual(store["v"], "world")
        self.assertEqual(mgr.health("clipboard").state, HealthState.HEALTHY)


# ===========================================================================
# built-in: system_info
# ===========================================================================

class TestSystemInfo(unittest.TestCase):
    def setUp(self):
        self.mgr = PluginManager()
        self.mgr.register(SystemInfoPlugin()); self.mgr.load("system_info")

    def test_info(self):
        r = self.mgr.invoke("system_info", "info")
        self.assertTrue(r.ok)
        self.assertIn("platform", r.data)

    def test_cpu_count(self):
        r = self.mgr.invoke("system_info", "cpu_count")
        self.assertGreaterEqual(r.data, 1)

    def test_env(self):
        os.environ["AISHA_TEST_VAR"] = "yes"
        try:
            r = self.mgr.invoke("system_info", "env", "AISHA_TEST_VAR")
            self.assertEqual(r.data, "yes")
        finally:
            del os.environ["AISHA_TEST_VAR"]


# ===========================================================================
# built-in: git (injected runner)
# ===========================================================================

class TestGit(unittest.TestCase):
    def _runner(self, mapping):
        def run(args, cwd):
            key = " ".join(args)
            out = mapping.get(key, "")
            return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")
        return run

    def test_current_branch(self):
        p = GitPlugin(runner=self._runner({"rev-parse --abbrev-ref HEAD": "main\n"}))
        mgr = PluginManager(); mgr.register(p); mgr.load("git")
        r = mgr.invoke("git", "current_branch")
        self.assertEqual(r.data, "main")

    def test_status_porcelain(self):
        p = GitPlugin(runner=self._runner({"status --porcelain": " M a.py\n?? b.py\n"}))
        mgr = PluginManager(); mgr.register(p); mgr.load("git")
        r = mgr.invoke("git", "status")
        self.assertEqual(len(r.data), 2)

    def test_log_parsing(self):
        line = "abc123\x1fMayank\x1fInitial commit"
        p = GitPlugin(runner=self._runner({"log -5 --pretty=format:%h\x1f%an\x1f%s": line}))
        mgr = PluginManager(); mgr.register(p); mgr.load("git")
        r = mgr.invoke("git", "log", 5)
        self.assertEqual(r.data[0]["author"], "Mayank")

    def test_error_returncode(self):
        def run(args, cwd):
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="fatal: not a repo")
        p = GitPlugin(runner=run)
        mgr = PluginManager(); mgr.register(p); mgr.load("git")
        r = mgr.invoke("git", "status")
        self.assertFalse(r.ok)

    def test_permission_denied(self):
        p = GitPlugin(runner=self._runner({}))
        mgr = PluginManager(); mgr.auto_grant = False
        mgr.register(p); mgr.load("git")
        r = mgr.invoke("git", "current_branch")
        self.assertFalse(r.ok)


# ===========================================================================
# planned plugins
# ===========================================================================

class TestPlanned(unittest.TestCase):
    def test_all_planned_unavailable(self):
        mgr = PluginManager()
        for cls in PLANNED_PLUGINS:
            mgr.register(cls())
        mgr.load_all()
        for cls in PLANNED_PLUGINS:
            name = cls().manifest().name
            self.assertEqual(mgr.health(name).state, HealthState.UNAVAILABLE)

    def test_planned_info_reports_not_implemented(self):
        mgr = PluginManager()
        mgr.register(PLANNED_PLUGINS[0]())
        name = PLANNED_PLUGINS[0]().manifest().name
        mgr.load(name)
        r = mgr.invoke(name, "info")
        self.assertFalse(r.data["implemented"])


# ===========================================================================
# default manager / integration
# ===========================================================================

class TestDefaultManager(unittest.TestCase):
    def test_builds_full_catalogue(self):
        mgr = build_default_manager()
        names = mgr.registry.names()
        for expected in ("calculator", "filesystem", "clipboard", "system_info", "git",
                         "terminal", "browser", "pdf", "ocr", "weather"):
            self.assertIn(expected, names)

    def test_catalogue_counts(self):
        self.assertEqual(len(IMPLEMENTED_PLUGINS), 5)
        self.assertEqual(len(ALL_BUILTIN_PLUGINS), 15)

    def test_implemented_loaded_active(self):
        mgr = build_default_manager()
        self.assertEqual(mgr.status("calculator"), PluginStatus.ACTIVE)

    def test_capability_index_complete(self):
        mgr = build_default_manager()
        idx = mgr.capability_index()
        self.assertIn("filesystem", idx)
        self.assertIn("image_generation", idx)

    def test_manifests_serializable(self):
        mgr = build_default_manager()
        for m in mgr.manifests():
            self.assertIn("name", m)
            self.assertIn("permissions", m)

    def test_register_builtins_implemented_only(self):
        mgr = PluginManager()
        register_builtins(mgr, include_planned=False)
        self.assertEqual(len(mgr.registry), 5)


# ===========================================================================
# SDK
# ===========================================================================

class TestSDK(unittest.TestCase):
    def test_action_discovery(self):
        e = Echo()
        self.assertIn("say", e.actions())
        self.assertIn("guarded", e.actions())

    def test_ok_err_helpers(self):
        self.assertTrue(SimplePlugin.ok("x").ok)
        self.assertFalse(SimplePlugin.err("boom").ok)

    def test_private_not_action(self):
        class P(SimplePlugin):
            def manifest(self):
                return PluginManifest(name="p", version="1.0.0", capabilities=[Capability.SYSTEM])
            @action
            def pub(self): return 1
            def _priv(self): return 2
        self.assertIn("pub", P().actions())
        self.assertNotIn("_priv", P().actions())


if __name__ == "__main__":
    unittest.main(verbosity=2)
