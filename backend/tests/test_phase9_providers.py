"""
Phase 9 -- Local LLM Platform: provider abstraction test suite.

Covers the provider interface, the three concrete providers (Local, Gemini,
Ollama), the config-driven registry/router, and the backward-compatible
``llm_router`` facade.  All network I/O is faked so the suite runs fully
offline and deterministically.

Run::

    python backend/tests/test_phase9_providers.py
"""

from __future__ import annotations

import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_BACKEND)
for p in (_BACKEND, os.path.join(_ROOT, "database")):
    if p not in sys.path:
        sys.path.insert(0, p)

import providers as P
from providers import (
    Capability,
    TaskType,
    ProviderStatus,
    ProviderResponse,
    HealthReport,
    LatencyTracker,
    LocalProvider,
    GeminiProvider,
    OllamaProvider,
    ProviderRegistry,
    build_default_registry,
    get_registry,
    reset_registry,
)
from providers import config as pconfig
from providers.gemini_provider import (
    is_real_key,
    load_gemini_keys,
    build_gemini_prompt,
)


# ===========================================================================
# Fakes
# ===========================================================================

class FakeOllamaTransport:
    """In-memory stand-in for the Ollama HTTP transport."""

    def __init__(self, models=None, response="fake-ollama-output", stream_pieces=None, fail=False):
        self._models = models or []
        self._response = response
        self._stream = stream_pieces if stream_pieces is not None else ["one ", "two ", "three"]
        self._fail = fail
        self.calls = []

    def get(self, path):
        self.calls.append(("GET", path, None))
        if self._fail:
            raise ConnectionError("daemon down")
        return {"models": [{"name": m} for m in self._models]}

    def post(self, path, payload):
        self.calls.append(("POST", path, payload))
        if self._fail:
            raise ConnectionError("daemon down")
        return {"response": self._response, "done": True}

    def post_stream(self, path, payload):
        self.calls.append(("STREAM", path, payload))
        if self._fail:
            raise ConnectionError("daemon down")
        for piece in self._stream:
            yield {"response": piece, "done": False}
        yield {"response": "", "done": True}


ALL_MODELS = ["qwen2.5-coder:7b", "deepseek-r1:8b", "phi4:latest", "gemma2:9b", "qwen2.5:7b"]


def healthy_ollama():
    return OllamaProvider(transport=FakeOllamaTransport(models=ALL_MODELS))


def install_fake_genai(text="gemini-says-hi"):
    """Inject a fake google.generativeai module; return an uninstall fn."""
    fake = types.ModuleType("google.generativeai")

    class _Resp:
        def __init__(self, t):
            self.text = t

    class _Model:
        def __init__(self, name):
            self.name = name

        def generate_content(self, prompt, stream=False):
            if stream:
                return [_Resp("chunk-a "), _Resp("chunk-b")]
            return _Resp(text)

    fake.configure = lambda **kw: None
    fake.GenerativeModel = _Model

    google_mod = sys.modules.get("google") or types.ModuleType("google")
    saved_google = sys.modules.get("google")
    saved_genai = sys.modules.get("google.generativeai")
    google_mod.generativeai = fake
    sys.modules["google"] = google_mod
    sys.modules["google.generativeai"] = fake

    def uninstall():
        if saved_genai is not None:
            sys.modules["google.generativeai"] = saved_genai
        else:
            sys.modules.pop("google.generativeai", None)
        if saved_google is not None:
            sys.modules["google"] = saved_google
        elif "google" in sys.modules and not hasattr(saved_google or object(), "generativeai"):
            # only remove if we created it
            if saved_google is None:
                sys.modules.pop("google", None)

    return uninstall


# ===========================================================================
# base.py
# ===========================================================================

class TestBase(unittest.TestCase):
    def test_latency_avg(self):
        t = LatencyTracker()
        for v in (10, 20, 30):
            t.record(v)
        self.assertEqual(t.count, 3)
        self.assertAlmostEqual(t.avg, 20.0)

    def test_latency_p95(self):
        t = LatencyTracker()
        for v in range(1, 101):
            t.record(v)
        # window default 50 -> last 50 samples (51..100)
        self.assertLessEqual(t.count, 50)
        self.assertGreaterEqual(t.p95, t.avg)

    def test_latency_window_cap(self):
        t = LatencyTracker(window=5)
        for v in range(20):
            t.record(v)
        self.assertEqual(t.count, 5)

    def test_latency_reset(self):
        t = LatencyTracker()
        t.record(5)
        t.reset()
        self.assertEqual(t.count, 0)
        self.assertEqual(t.avg, 0.0)
        self.assertEqual(t.p95, 0.0)

    def test_response_failure(self):
        r = ProviderResponse.failure("x", "boom")
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "boom")
        self.assertEqual(r.text, "")

    def test_health_available(self):
        h = HealthReport("x", ProviderStatus.HEALTHY)
        self.assertTrue(h.available)
        d = HealthReport("x", ProviderStatus.UNAVAILABLE)
        self.assertFalse(d.available)
        deg = HealthReport("x", ProviderStatus.DEGRADED)
        self.assertTrue(deg.available)

    def test_health_to_dict(self):
        h = HealthReport("x", ProviderStatus.HEALTHY, detail="ok", models=["m"])
        d = h.to_dict()
        self.assertEqual(d["provider"], "x")
        self.assertEqual(d["status"], "healthy")
        self.assertTrue(d["available"])

    def test_coerce_capability(self):
        self.assertEqual(P.coerce_capability("coding"), Capability.CODING)
        self.assertEqual(P.coerce_capability(Capability.REASONING), Capability.REASONING)

    def test_coerce_task(self):
        self.assertEqual(P.coerce_task("planning"), TaskType.PLANNING)
        self.assertEqual(P.coerce_task(TaskType.GENERAL), TaskType.GENERAL)

    def test_generate_wraps_exception(self):
        class Boom(LocalProvider):
            def _generate(self, *a, **k):
                raise ValueError("nope")
        b = Boom()
        r = b.generate("hi")
        self.assertFalse(r.ok)
        self.assertIn("nope", r.error)
        self.assertEqual(b.latency.count, 1)  # latency recorded even on failure

    def test_generate_records_latency(self):
        lp = LocalProvider()
        lp.generate("hello", context={"role": "assistant"})
        self.assertEqual(lp.latency.count, 1)


# ===========================================================================
# LocalProvider
# ===========================================================================

class TestLocalProvider(unittest.TestCase):
    def setUp(self):
        self.p = LocalProvider()

    def test_name_and_local(self):
        self.assertEqual(self.p.name, "local")
        self.assertTrue(self.p.local)

    def test_capabilities(self):
        caps = self.p.capabilities()
        self.assertIn(Capability.GENERAL, caps)
        self.assertIn(Capability.CONVERSATION, caps)

    def test_always_healthy(self):
        self.assertTrue(self.p.is_available())
        self.assertEqual(self.p.check_health().status, ProviderStatus.HEALTHY)

    def test_generate_returns_text(self):
        r = self.p.generate("hello", context={"role": "assistant"})
        self.assertTrue(r.ok)
        self.assertTrue(len(r.text) > 0)
        self.assertEqual(r.provider, "local")

    def test_supports(self):
        self.assertTrue(self.p.supports(Capability.GENERAL))
        self.assertFalse(self.p.supports(Capability.CODING))


# ===========================================================================
# GeminiProvider
# ===========================================================================

class TestGeminiProvider(unittest.TestCase):
    def test_is_real_key(self):
        self.assertTrue(is_real_key("abc123"))
        self.assertFalse(is_real_key(None))
        self.assertFalse(is_real_key(""))
        self.assertFalse(is_real_key("your_gemini_key_here"))

    def test_load_keys_from_env(self):
        for k in list(os.environ):
            if k.startswith("GEMINI_API_KEY"):
                del os.environ[k]
        os.environ["GEMINI_API_KEY"] = "legacy"
        os.environ["GEMINI_API_KEY_1"] = "one"
        os.environ["GEMINI_API_KEY_2"] = "one"  # dup, deduped
        try:
            keys = load_gemini_keys()
            self.assertIn("legacy", keys)
            self.assertIn("one", keys)
            self.assertEqual(len(keys), 2)
        finally:
            for k in ("GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_2"):
                os.environ.pop(k, None)

    def test_build_prompt_contains_context(self):
        prompt = build_gemini_prompt("hello", {"user_name": "Mayank", "emotion": "curious"})
        self.assertIn("Mayank", prompt)
        self.assertIn("curious", prompt)
        self.assertIn("User: hello", prompt)

    def test_capabilities(self):
        caps = GeminiProvider(keys=["k"]).capabilities()
        self.assertIn(Capability.CODING, caps)
        self.assertIn(Capability.STREAMING, caps)

    def test_health_no_keys(self):
        h = GeminiProvider(keys=[]).check_health()
        self.assertEqual(h.status, ProviderStatus.UNAVAILABLE)

    def test_generate_no_keys_fails_gracefully(self):
        r = GeminiProvider(keys=[]).generate("hi")
        self.assertFalse(r.ok)

    def test_generate_with_fake_genai(self):
        uninstall = install_fake_genai(text="hello-from-gemini")
        try:
            r = GeminiProvider(keys=["k1"]).generate("explain recursion", context={})
            self.assertTrue(r.ok)
            self.assertEqual(r.text, "hello-from-gemini")
            self.assertEqual(r.provider, "gemini")
        finally:
            uninstall()

    def test_stream_with_fake_genai(self):
        uninstall = install_fake_genai()
        try:
            chunks = list(GeminiProvider(keys=["k1"]).generate_stream("explain", context={}))
            self.assertEqual("".join(chunks), "chunk-a chunk-b")
        finally:
            uninstall()

    def test_health_with_fake_genai(self):
        uninstall = install_fake_genai()
        try:
            h = GeminiProvider(keys=["k1"]).check_health()
            self.assertEqual(h.status, ProviderStatus.HEALTHY)
        finally:
            uninstall()


# ===========================================================================
# OllamaProvider
# ===========================================================================

class TestOllamaProvider(unittest.TestCase):
    def test_health_healthy(self):
        p = OllamaProvider(transport=FakeOllamaTransport(models=ALL_MODELS))
        h = p.check_health()
        self.assertEqual(h.status, ProviderStatus.HEALTHY)

    def test_health_unreachable(self):
        p = OllamaProvider(transport=FakeOllamaTransport(fail=True))
        h = p.check_health()
        self.assertEqual(h.status, ProviderStatus.UNAVAILABLE)
        self.assertIn("unreachable", h.detail)

    def test_health_no_models(self):
        p = OllamaProvider(transport=FakeOllamaTransport(models=[]))
        h = p.check_health()
        self.assertEqual(h.status, ProviderStatus.UNAVAILABLE)

    def test_health_degraded(self):
        # daemon has some other model, none from our catalogue
        p = OllamaProvider(transport=FakeOllamaTransport(models=["llama3:8b"]))
        h = p.check_health()
        self.assertEqual(h.status, ProviderStatus.DEGRADED)

    def test_installed_models(self):
        p = OllamaProvider(transport=FakeOllamaTransport(models=["phi4:latest"]))
        self.assertEqual(p.installed_models(), ["phi4:latest"])

    def test_capabilities_union(self):
        p = healthy_ollama()
        caps = p.capabilities()
        for c in (Capability.CODING, Capability.REASONING, Capability.PLANNING, Capability.CONVERSATION):
            self.assertIn(c, caps)

    def test_model_for_capability(self):
        p = healthy_ollama()
        self.assertEqual(p.model_for(Capability.CODING), "qwen2.5-coder:7b")
        self.assertEqual(p.model_for(Capability.REASONING), "deepseek-r1:8b")
        self.assertEqual(p.model_for(Capability.PLANNING), "phi4:latest")
        self.assertEqual(p.model_for(Capability.CONVERSATION), "gemma2:9b")

    def test_generate(self):
        p = OllamaProvider(transport=FakeOllamaTransport(models=ALL_MODELS, response="42"))
        r = p.generate("what is 6*7", model="qwen2.5:7b")
        self.assertTrue(r.ok)
        self.assertEqual(r.text, "42")
        self.assertEqual(r.provider, "ollama")

    def test_generate_sends_system_prompt(self):
        tx = FakeOllamaTransport(models=ALL_MODELS)
        p = OllamaProvider(transport=tx)
        p.generate("hi", model="gemma2:9b", system_prompt="be terse")
        post = [c for c in tx.calls if c[0] == "POST"][0]
        self.assertEqual(post[2]["system"], "be terse")
        self.assertEqual(post[2]["model"], "gemma2:9b")

    def test_stream(self):
        p = OllamaProvider(transport=FakeOllamaTransport(models=ALL_MODELS, stream_pieces=["a", "b", "c"]))
        chunks = list(p.generate_stream("go", model="qwen2.5:7b"))
        self.assertEqual("".join(chunks), "abc")

    def test_generate_failure_wrapped(self):
        p = OllamaProvider(transport=FakeOllamaTransport(fail=True, models=ALL_MODELS))
        # health uses transport too; generate should wrap the connection error
        r = p.generate("hi", model="qwen2.5:7b")
        self.assertFalse(r.ok)


# ===========================================================================
# Registry & Routing
# ===========================================================================

class TestRegistry(unittest.TestCase):
    def setUp(self):
        pconfig.reset_config()
        self.reg = ProviderRegistry()

    def _full_healthy(self):
        self.reg.register(healthy_ollama())
        gp = GeminiProvider(keys=["k"])
        self.reg.register(gp)
        self.reg.register(LocalProvider())
        return self.reg

    def test_register_and_get(self):
        lp = LocalProvider()
        self.reg.register(lp)
        self.assertIs(self.reg.get("local"), lp)
        self.assertIn("local", self.reg.names())

    def test_clear(self):
        self.reg.register(LocalProvider())
        self.reg.clear()
        self.assertEqual(self.reg.all(), [])

    def test_capability_registry(self):
        self._full_healthy()
        cr = self.reg.capability_registry()
        self.assertIn("ollama", cr["coding"])
        self.assertIn("local", cr["general"])

    def test_providers_for_ordering_local_first(self):
        self._full_healthy()
        provs = self.reg.providers_for(Capability.GENERAL)
        # local-first ordering: ollama(local, prio10) and local(local, prio90) before gemini
        names = [p.name for p in provs]
        self.assertLess(names.index("ollama"), names.index("gemini"))
        self.assertLess(names.index("local"), names.index("gemini"))

    def test_route_coding(self):
        self._full_healthy()
        d = self.reg.route(TaskType.CODING)
        self.assertEqual(d.provider, "ollama")
        self.assertEqual(d.model, "qwen2.5-coder:7b")
        self.assertEqual(d.reason, "task_routing")

    def test_route_reasoning(self):
        self._full_healthy()
        d = self.reg.route("reasoning")
        self.assertEqual((d.provider, d.model), ("ollama", "deepseek-r1:8b"))

    def test_route_planning(self):
        self._full_healthy()
        d = self.reg.route("planning")
        self.assertEqual((d.provider, d.model), ("ollama", "phi4:latest"))

    def test_route_conversation(self):
        self._full_healthy()
        d = self.reg.route("conversation")
        self.assertEqual((d.provider, d.model), ("ollama", "gemma2:9b"))

    def test_route_general(self):
        self._full_healthy()
        d = self.reg.route("general")
        self.assertEqual((d.provider, d.model), ("ollama", "qwen2.5:7b"))

    def test_route_fallback_to_gemini_when_no_ollama(self):
        self.reg.register(GeminiProvider(keys=["k"]))
        self.reg.register(LocalProvider())
        # gemini needs genai to be healthy
        uninstall = install_fake_genai()
        try:
            d = self.reg.route(TaskType.CODING)
            self.assertEqual(d.provider, "gemini")
        finally:
            uninstall()

    def test_route_last_resort_when_nothing_healthy(self):
        self.reg.register(OllamaProvider(transport=FakeOllamaTransport(fail=True)))
        self.reg.register(GeminiProvider(keys=[]))
        self.reg.register(LocalProvider())
        d = self.reg.route(TaskType.CODING)
        self.assertEqual(d.provider, "local")
        self.assertEqual(d.reason, "last_resort")

    def test_route_no_provider(self):
        d = self.reg.route(TaskType.GENERAL)
        self.assertEqual(d.provider, "none")

    def test_manual_override(self):
        self._full_healthy()
        uninstall = install_fake_genai()
        try:
            self.reg.set_override("gemini")
            d = self.reg.route(TaskType.CODING)
            self.assertEqual(d.provider, "gemini")
            self.assertEqual(d.reason, "manual_override")
        finally:
            uninstall()

    def test_override_unknown_raises(self):
        with self.assertRaises(ValueError):
            self.reg.set_override("does-not-exist")

    def test_override_arg_beats_registry_override(self):
        self._full_healthy()
        d = self.reg.route(TaskType.CODING, provider="local")
        self.assertEqual(d.provider, "local")

    def test_generate_via_ollama(self):
        self.reg.register(OllamaProvider(transport=FakeOllamaTransport(models=ALL_MODELS, response="def bs(): ...")))
        self.reg.register(LocalProvider())
        r = self.reg.generate("write binary search", task=TaskType.CODING)
        self.assertTrue(r.ok)
        self.assertEqual(r.provider, "ollama")
        self.assertEqual(r.meta["route"]["reason"], "task_routing")

    def test_generate_falls_through_on_call_failure(self):
        # Ollama healthy at route time, but the generate call fails -> chain to local
        class FlakyHealthyTransport(FakeOllamaTransport):
            def post(self, path, payload):
                raise ConnectionError("died mid-call")
        tx = FlakyHealthyTransport(models=ALL_MODELS)
        self.reg.register(OllamaProvider(transport=tx))
        self.reg.register(LocalProvider())
        r = self.reg.generate("write code", task=TaskType.CODING, context={"role": "assistant"})
        self.assertTrue(r.ok)
        self.assertEqual(r.provider, "local")  # fell through

    def test_generate_stream(self):
        self.reg.register(OllamaProvider(transport=FakeOllamaTransport(models=ALL_MODELS, stream_pieces=["x", "y"])))
        self.reg.register(LocalProvider())
        chunks = list(self.reg.generate_stream("hi", task=TaskType.GENERAL))
        self.assertEqual("".join(chunks), "xy")

    def test_generate_stream_fallback_to_local(self):
        self.reg.register(OllamaProvider(transport=FakeOllamaTransport(fail=True)))
        self.reg.register(LocalProvider())
        chunks = list(self.reg.generate_stream("hello", task=TaskType.GENERAL, context={"role": "assistant"}))
        self.assertTrue(len("".join(chunks)) > 0)

    def test_health_report(self):
        self._full_healthy()
        rep = self.reg.health_report(force=True)
        self.assertEqual(rep["ollama"]["status"], "healthy")
        self.assertIn("local", rep)

    def test_latency_report(self):
        self.reg.register(LocalProvider())
        self.reg.generate("hi", context={"role": "assistant"})
        lr = self.reg.latency_report()
        self.assertGreaterEqual(lr["local"]["count"], 1)

    def test_health_cache(self):
        p = LocalProvider()
        self.reg.register(p)
        h1 = self.reg.health("local")
        h2 = self.reg.health("local")
        self.assertEqual(h1.checked_at, h2.checked_at)  # cached

    def test_config_driven_routing_not_hardcoded(self):
        """Changing config re-routes without touching code."""
        self._full_healthy()
        uninstall = install_fake_genai()
        try:
            pconfig.load_config({"task_routing": {"coding": {"provider": "gemini", "model": "gemini-2.0-flash"}}})
            d = self.reg.route(TaskType.CODING)
            self.assertEqual(d.provider, "gemini")
        finally:
            uninstall()
            pconfig.reset_config()


# ===========================================================================
# Config
# ===========================================================================

class TestConfig(unittest.TestCase):
    def tearDown(self):
        pconfig.reset_config()

    def test_defaults_present(self):
        cfg = pconfig.reset_config()
        self.assertIn("provider_order", cfg)
        self.assertEqual(pconfig.fallback_provider(), "gemini")
        self.assertEqual(pconfig.last_resort_provider(), "local")

    def test_route_for_task(self):
        pconfig.reset_config()
        r = pconfig.route_for_task(TaskType.CODING)
        self.assertEqual(r["model"], "qwen2.5-coder:7b")

    def test_model_capabilities(self):
        pconfig.reset_config()
        caps = pconfig.ollama_model_capabilities()
        self.assertIn(Capability.CODING, caps["qwen2.5-coder:7b"])

    def test_deep_merge(self):
        pconfig.load_config({"ollama": {"timeout": 5}})
        self.assertEqual(pconfig.ollama_settings()["timeout"], 5)
        # host preserved from defaults (deep merge, not replace)
        self.assertIn("host", pconfig.ollama_settings())

    def test_reset(self):
        pconfig.load_config({"fallback_provider": "local"})
        self.assertEqual(pconfig.fallback_provider(), "local")
        pconfig.reset_config()
        self.assertEqual(pconfig.fallback_provider(), "gemini")

    def test_all_spec_models_present(self):
        pconfig.reset_config()
        models = set(pconfig.ollama_model_capabilities().keys())
        for m in ALL_MODELS:
            self.assertIn(m, models)


# ===========================================================================
# Default registry builder
# ===========================================================================

class TestDefaultRegistry(unittest.TestCase):
    def tearDown(self):
        reset_registry()
        pconfig.reset_config()

    def test_builds_all_providers(self):
        reg = build_default_registry()
        self.assertIn("ollama", reg.names())
        self.assertIn("gemini", reg.names())
        self.assertIn("local", reg.names())

    def test_last_resort_always_present(self):
        pconfig.load_config({"provider_order": ["gemini"]})
        reg = build_default_registry()
        self.assertIn("local", reg.names())  # forced in

    def test_get_registry_singleton(self):
        reset_registry()
        r1 = get_registry()
        r2 = get_registry()
        self.assertIs(r1, r2)


# ===========================================================================
# llm_router backward compatibility
# ===========================================================================

class TestLLMRouterCompat(unittest.TestCase):
    def setUp(self):
        import llm_router
        self.L = llm_router

    def test_public_functions_exist(self):
        for fn in ("generate_ai_response", "generate_ai_response_stream",
                   "get_api_status", "explain_routing", "is_simple_query",
                   "call_gemini_with_rotation"):
            self.assertTrue(hasattr(self.L, fn), fn)

    def test_legacy_helpers_exist(self):
        for fn in ("_build_gemini_prompt", "_load_gemini_keys", "_is_real_key", "GEMINI_KEYS"):
            self.assertTrue(hasattr(self.L, fn), fn)

    def test_is_simple_query(self):
        self.assertTrue(self.L.is_simple_query("hi"))
        self.assertTrue(self.L.is_simple_query("thanks"))
        self.assertFalse(self.L.is_simple_query("Write a Python function for binary search"))
        self.assertFalse(self.L.is_simple_query("Explain why the sky is blue"))

    def test_simple_query_routes_local(self):
        out = self.L.generate_ai_response("hi", {"role": "assistant"})
        self.assertIsInstance(out, str)
        self.assertTrue(len(out) > 0)

    def test_complex_query_returns_string(self):
        out = self.L.generate_ai_response("Explain why the sky is blue", {"role": "assistant"})
        self.assertIsInstance(out, str)
        self.assertTrue(len(out) > 0)

    def test_stream_yields(self):
        chunks = list(self.L.generate_ai_response_stream("hi", {"role": "assistant"}))
        self.assertTrue(len("".join(chunks)) > 0)

    def test_detect_task(self):
        self.assertEqual(self.L.detect_task("write a python function").value, "coding")
        self.assertEqual(self.L.detect_task("make a plan and roadmap").value, "planning")
        self.assertEqual(self.L.detect_task("why does gravity work, compare").value, "reasoning")
        self.assertEqual(self.L.detect_task("tell me a story").value, "conversation")

    def test_explain_routing_legacy_keys(self):
        er = self.L.explain_routing("hi")
        self.assertEqual(er["tier"], "local")
        self.assertIn("reason", er)
        self.assertIn("input_preview", er)
        er2 = self.L.explain_routing("explain recursion in detail")
        self.assertEqual(er2["tier"], "gemini")

    def test_get_api_status_has_gemini_key(self):
        st = self.L.get_api_status()
        self.assertIn("gemini", st)

    def test_call_gemini_no_keys_returns_none(self):
        gp = GeminiProvider(keys=[])
        # simulate no keys by clearing env just in case
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("GEMINI_API_KEY")}
        try:
            self.assertIsNone(self.L.call_gemini_with_rotation("hi", {}))
        finally:
            os.environ.update(saved)

    def test_singleton_exists(self):
        self.assertTrue(hasattr(self.L, "llm_router"))
        self.assertTrue(hasattr(self.L.llm_router, "generate_ai_response"))

    def test_singleton_with_system_prompt(self):
        # This is the path reflective_cognition uses -- previously dead.
        out = self.L.llm_router.generate_ai_response(
            "summarize the day", system_prompt="You are terse.",
        )
        self.assertIsInstance(out, str)
        self.assertTrue(len(out) > 0)

    def test_generate_with_task_override(self):
        out = self.L.generate_ai_response(
            "hello world program", {"role": "assistant"}, task="coding",
        )
        self.assertIsInstance(out, str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
