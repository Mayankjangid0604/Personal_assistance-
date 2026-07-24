"""
Phase 4 AI Operating Layer — Full Test Suite.

Tests all 8 Phase 4 systems:
  1. Workflow Intelligence Engine
  2. Cross-Application Context Layer
  3. Agentic Task Execution System
  4. Productivity Cognition Engine
  5. Environmental Reasoning System
  6. Safe Autonomous Automation Governor
  7. AI Operating Layer Integration (server endpoints)
  8. Human-Centered Behavioral Refinement

Run::

    python backend/tests/test_phase4_operating_layer.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_TESTS_DIR)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)

for p in (_BACKEND_DIR, _PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

_PASS = 0
_FAIL = 0
_RESULTS: list[tuple[bool, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        _RESULTS.append((True, name, ""))
        print(f"  [PASS]  {name}")
    else:
        _FAIL += 1
        _RESULTS.append((False, name, detail))
        print(f"  [FAIL]  {name}" + (f" -- {detail}" if detail else ""))


def section(title: str) -> None:
    print()
    print("-" * 75)
    print(f"  {title}")
    print("-" * 75)


# ===========================================================================
# Test 1: Workflow Intelligence Engine
# ===========================================================================

section("Test 1: Workflow Intelligence Engine (Step 1)")

from workflow_intelligence import WorkflowIntelligence, workflow_intelligence, _WORKFLOW_DEFINITIONS

wi = WorkflowIntelligence()
check("WorkflowIntelligence initializes", wi is not None)

# Simulate a sequence of desktop snapshots
def make_snap(category: str) -> dict:
    return {"category": category, "window_title": f"Test {category}", "workflow": None}

# Single category → no workflow yet (buffer too small)
wi.update(make_snap("coding"))
result = wi.update(make_snap("coding"))
check("update() returns dict", isinstance(result, dict))
check("update() has active_workflow key", "active_workflow" in result)
check("update() has overload key", "overload" in result)

# Feed many coding snapshots → should detect deep_coding
for _ in range(15):
    wi.update(make_snap("coding"))
wf = wi.get_active_workflow()
check("Deep coding detected after many snapshots", wf is not None and wf.get("name") == "deep_coding",
      f"got: {wf}")

check("is_deep_work() returns True for deep_coding", wi.is_deep_work())

# Now mix browsing into it (simulate code-debug cycle)
wi2 = WorkflowIntelligence()
for i in range(20):
    cat = "coding" if i % 3 != 0 else "browsing"
    wi2.update(make_snap(cat))
wf2 = wi2.get_active_workflow()
check("Code-debug cycle detected", wf2 is not None and wf2.get("name") in
      ("code_debug_cycle", "deep_coding"), f"got: {wf2}")

# Overload detection
wi3 = WorkflowIntelligence()
cats = ["coding", "browsing", "communication", "design", "media", "studying",
        "gaming"] * 3
for c in cats:
    wi3.update(make_snap(c))
# Overload depends on transition rate and category diversity
result3 = wi3.update(make_snap("communication"))
check("Overload detection runs without error", isinstance(result3.get("overload"), bool))

# Context summary
summary = wi.get_context_summary()
check("get_context_summary() returns str", isinstance(summary, str))

# Routine hints
hints = wi.get_routine_hints()
check("get_routine_hints() returns list", isinstance(hints, list))

# Category distribution
dist = wi.get_category_distribution()
check("get_category_distribution() returns dict", isinstance(dist, dict))
check("coding in distribution", "coding" in dist)

# Status
status = wi.get_status()
check("get_status() returns dict", isinstance(status, dict))
check("Status has active_workflow", "active_workflow" in status)
check("Status has overload_detected", "overload_detected" in status)
check("Status has transition_count", "transition_count" in status)
check("Status has routine_hints", "routine_hints" in status)

# Workflow definitions count
check("At least 7 workflow definitions", len(_WORKFLOW_DEFINITIONS) >= 7)

# Reset
wi.reset()
check("reset() clears buffer", wi.get_active_workflow() is None)


# ===========================================================================
# Test 2: Cross-Application Context Layer
# ===========================================================================

section("Test 2: Cross-Application Context Layer (Step 2)")

from cross_app_context import CrossAppContext, cross_app_context

ca = CrossAppContext()
check("CrossAppContext initializes", ca is not None)

# Feed a coding + browsing snapshot
snap = {
    "category": "coding",
    "window_title": "Visual Studio Code",
    "workflow": "code_debug_cycle",
}
ctx_result = ca.update(snap)
check("update() returns dict", isinstance(ctx_result, dict))
check("update() has context_name", "context_name" in ctx_result)
check("update() has context_label", "context_label" in ctx_result)
check("update() has active_categories", "active_categories" in ctx_result)
check("update() has context_changed", "context_changed" in ctx_result)

# PDF + Notion → study_synthesis
ca2 = CrossAppContext()
snap2 = {"category": "studying", "window_title": "Notion - My Notes", "workflow": None}
ca2.update({"category": "browsing", "window_title": "Chrome", "workflow": None})
ctx2 = ca2.update(snap2)
check("Context_name is str or None", ctx2["context_name"] is None or isinstance(ctx2["context_name"], str))

# Context string
ctx_str = ca.get_context_string()
check("get_context_string() returns str", isinstance(ctx_str, str))

# Current context
current = ca.get_current_context()
check("get_current_context() returns dict", isinstance(current, dict))
check("current context has name", "name" in current)
check("current context has active_categories", "active_categories" in current)

# Status
status = ca.get_status()
check("get_status() returns dict", isinstance(status, dict))
check("Status has current_context", "current_context" in status)
check("Status has context_string", "context_string" in status)


# ===========================================================================
# Test 3: Agentic Task Execution System
# ===========================================================================

section("Test 3: Agentic Task Execution System (Step 3)")

from agentic_executor import AgenticExecutor, executor, _ACTION_REGISTRY

ae = AgenticExecutor()
ae.set_autonomy_tier(2)
check("AgenticExecutor initializes", ae is not None)

# Default tier
check("Default autonomy tier is 2", ae.autonomy_tier == 2)

# Tier setting
ae.set_autonomy_tier(0)
check("Set tier 0 works", ae.autonomy_tier == 0)

# Tier 0 blocks all actions
result0 = ae.request("notify", {"message": "Test"}, "Test reason")
check("Tier 0 blocks notify", result0["status"] == "rejected")

ae.set_autonomy_tier(1)
result1 = ae.request("open_url", {"url": "https://google.com"}, "Test")
check("Tier 1 blocks moderate actions", result1["status"] == "rejected")

# Safe action on tier 1
result_safe = ae.request("notify", {"message": "Test notification"}, "Test")
check("Tier 1 allows safe (notify) action", result_safe["status"] in ("executed", "failed"))

# Tier 2: moderate action goes to pending
ae.set_autonomy_tier(2)
result2 = ae.request("open_url", {"url": "https://google.com"}, "Test open URL")
check("Tier 2 queues moderate action as pending", result2["status"] == "pending")
check("Pending result has action_id", "action_id" in result2)

# Get pending
pending = ae.get_pending()
check("get_pending() returns list", isinstance(pending, list))
check("Pending has one item", len(pending) >= 1)

# Cancel pending
if pending:
    cancel_result = ae.cancel(pending[0]["action_id"])
    check("cancel() returns dict", isinstance(cancel_result, dict))
    check("cancel() status=cancelled", cancel_result["status"] == "cancelled")

# Tier 3: moderate action auto-approves
ae.set_autonomy_tier(3)
result3 = ae.request("open_url", {"url": "https://google.com"}, "Auto open")
check("Tier 3 auto-approves moderate action", result3["status"] in ("executed", "failed"))

# Unknown action
bad = ae.request("delete_everything", {}, "Bad actor")
check("Unknown action rejected", bad["status"] == "rejected")

# Safety: non-http URL blocked
ae_safe = AgenticExecutor()
ae_safe.set_autonomy_tier(3)
bad_url = ae_safe.request("open_url", {"url": "file:///etc/passwd"}, "Try exploit")
check("Non-http URL rejected", bad_url.get("result", {}).get("ok") is False)

# Known app check
good_app = ae_safe.request("open_app", {"app": "notepad"}, "Open notepad")
check("Known app action returns result", good_app["status"] in ("executed", "failed"))
bad_app = ae_safe.request("open_app", {"app": "malware.exe"}, "Unknown app")
check("Unknown app rejected in result", bad_app.get("result", {}).get("ok") is False)

# Audit log
log = ae.get_audit_log(limit=5)
check("get_audit_log() returns list", isinstance(log, list))
check("Audit entries have action field", all("action" in e for e in log))
check("Audit entries have timestamp", all("timestamp" in e for e in log))

# Status
status = ae.get_status()
check("get_status() returns dict", isinstance(status, dict))
check("Status has autonomy_tier", "autonomy_tier" in status)
check("Status has pending_count", "pending_count" in status)
check("Status has total_actions_executed", "total_actions_executed" in status)

# Action registry
check("At least 5 registered actions", len(_ACTION_REGISTRY) >= 5)
for action in ["notify", "open_url", "open_app", "clipboard_store"]:
    check(f"Action '{action}' in registry", action in _ACTION_REGISTRY)
    check(f"Action '{action}' has risk", "risk" in _ACTION_REGISTRY[action])
    check(f"Action '{action}' has reversible", "reversible" in _ACTION_REGISTRY[action])


# ===========================================================================
# Test 4: Productivity Cognition Engine
# ===========================================================================

section("Test 4: Productivity Cognition Engine (Step 4)")

from productivity_cognition import ProductivityEngine, productivity_engine

pe = ProductivityEngine()
check("ProductivityEngine initializes", pe is not None)

# Update with coding snapshot
snap_code = {"category": "coding"}
prod_result = pe.update(snap_code)
check("update() returns dict", isinstance(prod_result, dict))
check("update() has focus_score", "focus_score" in prod_result)
check("update() has burnout_risk", "burnout_risk" in prod_result)
check("update() has in_focus_session", "in_focus_session" in prod_result)
check("Focus score in [0,1]", 0.0 <= prod_result["focus_score"] <= 1.0)
check("Burnout risk is valid", prod_result["burnout_risk"] in ("none", "low", "moderate", "high"))

# Multiple coding updates → should build a focus session
for _ in range(5):
    pe.update({"category": "coding"})
check("In focus session after coding", pe.update({"category": "coding"})["in_focus_session"])

# Communication → lower focus score
pe2 = ProductivityEngine()
for _ in range(10):
    pe2.update({"category": "communication"})
result2 = pe2.update({"category": "media"})
check("Communication/media reduces focus", result2["focus_score"] < 0.8)

# Break suggestion: initially None (no long focus session)
suggestion = pe.check_break_suggestion()
check("check_break_suggestion() returns str or None",
      suggestion is None or isinstance(suggestion, str))

# Context summary
ctx = pe.get_context_summary()
check("get_context_summary() returns str", isinstance(ctx, str))

# Fragmentation
pe3 = ProductivityEngine()
cats = ["coding", "browsing", "communication", "design", "media", "studying"] * 2
for c in cats:
    pe3.update({"category": c})
frag = pe3.is_fragmented()
check("is_fragmented() returns bool", isinstance(frag, bool))

# Status
status = pe.get_status()
check("get_status() returns dict", isinstance(status, dict))
check("Status has focus_score", "focus_score" in status)
check("Status has burnout_risk", "burnout_risk" in status)
check("Status has daily_focus_hours", "daily_focus_hours" in status)
check("Status has context_summary", "context_summary" in status)

# ===========================================================================
# Test 5: Environmental Reasoning System
# ===========================================================================

section("Test 5: Environmental Reasoning System (Step 5)")

from environmental_reasoning import EnvironmentalReasoning, environment, _MODE_DEFINITIONS

er = EnvironmentalReasoning()
check("EnvironmentalReasoning initializes", er is not None)

# Update with no snapshot
env_result = er.update(None)
check("update(None) returns dict", isinstance(env_result, dict))
check("update() has mode", "mode" in env_result)
check("update() has label", "label" in env_result)
check("update() has aisha_tone", "aisha_tone" in env_result)
check("update() has interruption_tolerance", "interruption_tolerance" in env_result)
check("Mode is in definitions", env_result["mode"] in _MODE_DEFINITIONS)

# With coding snapshot
env2 = EnvironmentalReasoning()
env_code = env2.update({"category": "coding", "workflow": "deep_coding"})
check("Coding + deep_coding -> deep_work mode", env_code["mode"] == "deep_work")
check("deep_work is low interruption",
      env_code["interruption_tolerance"] == "low")

# is_low_interruption
env2._current_mode = "deep_work"
check("is_low_interruption() True for deep_work", env2.is_low_interruption())

env2._current_mode = "general"
check("is_low_interruption() False for general", not env2.is_low_interruption())

# get_behavioral_guidance
guidance = er.get_behavioral_guidance()
check("get_behavioral_guidance() returns str", isinstance(guidance, str))
check("Behavioral guidance is non-empty", len(guidance) > 0)

# Mode context
mode_ctx = er.get_mode_context()
check("get_mode_context() returns dict", isinstance(mode_ctx, dict))
check("Mode context has mode", "mode" in mode_ctx)
check("Mode context has aisha_tone", "aisha_tone" in mode_ctx)
check("Mode context has duration_min", "duration_min" in mode_ctx)

# All modes defined correctly
for mode_name, defn in _MODE_DEFINITIONS.items():
    check(f"Mode '{mode_name}' has label", "label" in defn)
    check(f"Mode '{mode_name}' has aisha_tone", "aisha_tone" in defn)

# Status
status = er.get_status()
check("get_status() returns dict", isinstance(status, dict))
check("Status has current_mode", "current_mode" in status)
check("Status has behavioral_guidance", "behavioral_guidance" in status)


# ===========================================================================
# Test 6: Automation Governor
# ===========================================================================

section("Test 6: Safe Autonomous Automation Governor (Step 6)")

from automation_governor import AutomationGovernor, automation_governor, DAILY_BUDGET, HOURLY_BUDGET

ag = AutomationGovernor()
ag.set_tier(2)
check("AutomationGovernor initializes", ag is not None)

# Default tier
check("Default tier is 2", ag.tier == 2)

# Tier 0 blocks everything
ag.set_tier(0)
allowed, reason = ag.can_automate("presence", "notify", confidence=1.0, action_risk="safe")
check("Tier 0 blocks safe actions", not allowed)

# Tier 1 blocks moderate
ag.set_tier(1)
allowed, reason = ag.can_automate("presence", "open_url", confidence=1.0, action_risk="moderate")
check("Tier 1 blocks moderate actions", not allowed)

# Tier 1 allows safe
ag.set_tier(1)
allowed, reason = ag.can_automate("presence", "notify", confidence=1.0, action_risk="safe")
check("Tier 1 allows safe actions", allowed, reason)

# User source bypasses gates
ag.set_tier(2)
allowed, reason = ag.can_automate("user", "open_url", confidence=0.1, action_risk="moderate")
check("User source bypasses gates", allowed, reason)

# Confidence threshold
ag2 = AutomationGovernor()
ag2.set_tier(3)
allowed, reason = ag2.can_automate("presence", "open_url", confidence=0.3, action_risk="moderate",
                                    emotion="neutral")
check("Low confidence blocks moderate action", not allowed, reason)

allowed_high, _ = ag2.can_automate("presence", "open_url", confidence=0.8, action_risk="moderate",
                                    emotion="neutral")
check("Sufficient confidence allows moderate action", allowed_high)

# Emotional gating
ag3 = AutomationGovernor()
ag3.set_tier(3)
allowed_s, reason_s = ag3.can_automate("presence", "notify", confidence=0.9, action_risk="safe",
                                        emotion="stressed", urgency="normal")
check("Stressed emotion suppresses non-urgent automations", not allowed_s, reason_s)

# Budget exhaustion
ag4 = AutomationGovernor()
ag4.set_tier(3)
ag4._daily_count = DAILY_BUDGET
allowed_b, _ = ag4.can_automate("presence", "open_url", confidence=0.9, action_risk="moderate")
check("Daily budget exhaustion blocks actions", not allowed_b)

ag5 = AutomationGovernor()
ag5.set_tier(3)
ag5._hourly_count = HOURLY_BUDGET
allowed_h, _ = ag5.can_automate("presence", "open_url", confidence=0.9, action_risk="moderate")
check("Hourly budget exhaustion blocks actions", not allowed_h)

# Cooldown
ag6 = AutomationGovernor()
ag6.set_tier(3)
ag6._last_execution_time = time.time() - 30  # 30s ago, under 10min cooldown
allowed_c, _ = ag6.can_automate("presence", "open_url", confidence=0.9, action_risk="moderate")
check("Cooldown blocks moderate actions", not allowed_c)

# Record and get log
ag.set_tier(3)
ag.record_execution("productivity", "notify", "safe")
log = ag.get_execution_log(limit=5)
check("get_execution_log() returns list", isinstance(log, list))
check("Log entry has source", all("source" in e for e in log))

# Status
status = ag.get_status()
check("get_status() returns dict", isinstance(status, dict))
check("Status has tier", "tier" in status)
check("Status has daily_count", "daily_count" in status)
check("Status has suppressed_count", "suppressed_count" in status)


# ===========================================================================
# Test 7: AI Operating Layer Integration (Server Endpoints)
# ===========================================================================

section("Test 7: AI Operating Layer Server Endpoints (Step 7)")


async def _test_phase4_endpoints():
    from server import app
    results = {}

    async with app.test_client() as client:
        # Phase 4 endpoints
        for endpoint in [
            "/workflow/status",
            "/workspace/context",
            "/productivity/status",
            "/environment/status",
            "/executor/status",
            "/executor/log",
            "/automation/status",
            "/operating/status",
        ]:
            r = await client.get(endpoint)
            results[endpoint] = r.status_code

        # POST endpoints
        r = await client.post("/executor/action", json={
            "action": "notify",
            "params": {"message": "Test"},
            "reason": "Phase 4 test",
        })
        results["/executor/action"] = r.status_code

        r = await client.post("/automation/tier", json={"tier": 2})
        results["/automation/tier"] = r.status_code

        # Phase 3 regression
        for endpoint in [
            "/health",
            "/cognitive/status",
            "/memory/search?q=test",
            "/presence/status",
        ]:
            r = await client.get(endpoint)
            results[endpoint] = r.status_code

        # Health version check
        r = await client.get("/health")
        results["health_data"] = await r.get_json()

    return results


ep_results = asyncio.run(_test_phase4_endpoints())

# Phase 4 endpoints
for endpoint in [
    "/workflow/status", "/workspace/context", "/productivity/status",
    "/environment/status", "/executor/status", "/executor/log",
    "/automation/status", "/operating/status",
    "/executor/action", "/automation/tier",
]:
    code = ep_results.get(endpoint, 0)
    check(f"Phase 4: {endpoint} responds 2xx", 200 <= code < 300, f"got {code}")

# Phase 3 regression
for endpoint in ["/health", "/cognitive/status", "/memory/search?q=test", "/presence/status"]:
    code = ep_results.get(endpoint, 0)
    check(f"Phase 3 regression: {endpoint} still 200", code == 200, f"got {code}")

# Version bump (≥ 4.0.0 since Phase 5 bumped to 5.0.0)
health = ep_results.get("health_data", {})
check(
    "Version is >= 4.0.0",
    health.get("version", "0").split(".")[0] >= "4",
    f"got={health.get('version')}",
)


# ===========================================================================
# Test 8: Behavioral Intelligence (Phase 4 Refinements)
# ===========================================================================

section("Test 8: Human-Centered Behavioral Refinement (Step 8)")

from behavioral_intelligence import BehavioralIntelligence, behavioral_intelligence

bi = BehavioralIntelligence()

# Phase 4 context enrichment
p4_context = {
    "aisha_tone": "Be concise, precise, and avoid unnecessary conversation.",
    "workflow": "Deep Coding Session",
    "productivity_context": "User is in high-quality focused work.",
    "burnout_risk": "none",
}

prompt = bi.get_behavioral_prompt("neutral", p4_context)
check("Phase 4 behavioral prompt returns str", isinstance(prompt, str))
check("Phase 4 tone included in prompt",
      "concise" in prompt.lower() or "precise" in prompt.lower(), prompt[:100])
check("Workflow included in prompt",
      "Deep Coding Session" in prompt or "workflow" in prompt.lower(), prompt[:200])
check("Productivity context included", "focused" in prompt.lower(), prompt[:200])

# Burnout high
p4_burnout = {
    "aisha_tone": "Be calm and supportive.",
    "burnout_risk": "high",
}
prompt_burnout = bi.get_behavioral_prompt("stressed", p4_burnout)
check("Burnout high included in prompt",
      "burnout" in prompt_burnout.lower() or "rest" in prompt_burnout.lower(),
      prompt_burnout[:200])

# Burnout moderate
p4_moderate = {"burnout_risk": "moderate"}
prompt_mod = bi.get_behavioral_prompt("neutral", p4_moderate)
check("Burnout moderate acknowledged in prompt",
      "working hard" in prompt_mod.lower() or "effort" in prompt_mod.lower(),
      prompt_mod[:200])

# Deep work pacing
response_long = "Here is a very detailed explanation that goes on and on about everything in great detail."
enriched = bi.enrich_response(
    response_long, "explain this", emotion="neutral",
    context={"desktop_status": {"deep_work": True}}
)
check("Deep work shortens responses", len(enriched) <= len(response_long))

# Normal mode: no truncation for short responses
short_resp = "Got it!"
enriched_short = bi.enrich_response(short_resp, "ok", emotion="neutral", context={})
check("Short response untouched", enriched_short == short_resp)

# Status
status = bi.get_status()
check("Behavioral status returns dict", isinstance(status, dict))
check("Status has turn_count", "turn_count" in status)
check("Status has session_depth", "session_depth" in status)


# ===========================================================================
# Test 9: Full Cognitive Pipeline (Phase 4 Integrated Turn)
# ===========================================================================

section("Test 9: Full Phase 4 Pipeline Integration")


async def _test_p4_turn():
    from server import app
    async with app.test_client() as client:
        r = await client.post(
            "/chat",
            json={"message": "I've been coding for hours, feeling a bit tired"},
        )
        status = r.status_code
        data = await r.get_json()
    return status, data


status_p4, data_p4 = asyncio.run(_test_p4_turn())
check("Phase 4 turn returns 200", status_p4 == 200)
check("Phase 4 response present", "response" in data_p4)
check("Phase 4 cognitive key present", "cognitive" in data_p4)
check("Phase 4 operating key present", "operating" in data_p4,
      f"keys: {list(data_p4.keys())}")

if "operating" in data_p4:
    op = data_p4["operating"]
    check("operating has environment_mode", "environment_mode" in op)
    check("operating has focus_score", "focus_score" in op)
    check("operating has burnout_risk", "burnout_risk" in op)
    check("operating has is_deep_work", "is_deep_work" in op)


# ===========================================================================
# Test 10: Behavioral Safety Analysis
# ===========================================================================

section("Test 10: Behavioral Safety & Privacy Guarantee")

# DesktopAwareness: verify no file reading
from desktop_awareness import _get_foreground_window_info, _get_clipboard_type
import inspect
da_source = inspect.getsource(_get_foreground_window_info)
check("desktop_awareness reads no file paths (open/read)", "open(" not in da_source)
check("desktop_awareness has no os.walk()", "os.walk" not in da_source)

# WorkflowIntelligence: only uses category data
wi_source = inspect.getsource(WorkflowIntelligence.update)
check("WorkflowIntelligence uses only category data",
      "category" in wi_source and "open(" not in wi_source)

# AgenticExecutor: only known apps
from agentic_executor import _APP_MAPPINGS
exec_src = inspect.getsource(AgenticExecutor._do_open_app)
check("open_app only launches from known list", "_APP_MAPPINGS" in exec_src)

# AgenticExecutor: URL safety check
url_src = inspect.getsource(AgenticExecutor._do_open_url)
check("open_url enforces http/https", "http" in url_src and "startswith" in url_src)

# AutomationGovernor: emotional gating is present
gov_src = inspect.getsource(AutomationGovernor.can_automate)
check("Automation governor checks emotion", "_SUPPRESSED_EMOTIONS" in gov_src or "emotion" in gov_src)

# Executor audit trail
ae_audit = AgenticExecutor()
ae_audit.set_autonomy_tier(3)
ae_audit.request("notify", {"message": "Test"}, "Safety test")
log = ae_audit.get_audit_log()
check("Every action creates audit entry", len(log) > 0)
check("Audit entry has reason", all("reason" in e for e in log))


# ===========================================================================
# Final Results
# ===========================================================================

total = _PASS + _FAIL
print()
print("=" * 75)
print(f"  RESULTS: {_PASS} passed, {_FAIL} failed, {total} total")
if _FAIL == 0:
    print("  ALL TESTS PASSED -- Phase 4 AI Operating Layer Verified!")
else:
    print("  FAILED TESTS:")
    for passed, name, detail in _RESULTS:
        if not passed:
            print(f"    - {name}" + (f": {detail}" if detail else ""))
print("=" * 75)
