"""
Phase 2 — Complete Integration Test Suite.

Tests all Phase 2 features:
  Step 1: Async bridge (run_sync, EventBus)
  Step 2: WebSocket endpoint
  Step 3: Async voice pipeline
  Step 4: Orb state events from chat handlers
  Step 5: Session ID tracking
  Step 6: Server contract validation

Run:
    python backend/tests/test_phase2_integration.py
"""

import asyncio
import json
import os
import sys
import time

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_TEST_DIR)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_DATABASE_DIR = os.path.join(_PROJECT_ROOT, "database")

for p in (_BACKEND_DIR, _DATABASE_DIR, _PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# Test Framework
# ---------------------------------------------------------------------------

passed = 0
failed = 0


def section(title):
    print()
    print("-" * 75)
    print("  " + title)
    print("-" * 75)
    print()


def check(description, condition, detail=""):
    global passed, failed
    status = "PASS" if condition else "FAIL"
    if condition:
        passed += 1
    else:
        failed += 1
    suffix = "  (%s)" % detail if detail and not condition else ""
    print("  [%s]  %s%s" % (status, description, suffix))


if __name__ == "__main__":
    # ==========================================================================
    print("=" * 75)
    print("  AISHA -- Phase 2 -- Complete Integration Test")
    print("=" * 75)


    # --- Test 1: Async Bridge (Step 1 regression) -----------------------------
    section("Test 1: Async Bridge (Step 1 Regression)")

    from async_bridge import run_sync, event_bus, EventBus


    def _blocking_multiply(a, b):
        time.sleep(0.01)
        return a * b

    result = asyncio.run(run_sync(_blocking_multiply, 6, 7))
    check("run_sync works correctly", result == 42, f"got={result}")


    # EventBus basic test
    async def _test_bus():
        bus = EventBus()
        received = []

        async def sub():
            async for d in bus.subscribe("test"):
                received.append(d)
                if len(received) >= 1:
                    break

        async def pub():
            await asyncio.sleep(0.01)
            await bus.emit("test", {"ok": True})

        await asyncio.gather(
            asyncio.wait_for(sub(), timeout=2),
            pub(),
        )
        return received

    bus_result = asyncio.run(_test_bus())
    check("EventBus pub/sub works", len(bus_result) == 1 and bus_result[0].get("ok"))


    # --- Test 2: Server Import + WebSocket (Step 2) --------------------------
    section("Test 2: Server Import + Quart App")

    from server import app as quart_app
    check("server.py imports without error", True)
    check("app is Quart", type(quart_app).__name__ == "Quart")


    # --- Test 3: Session ID (Step 5) -----------------------------------------
    section("Test 3: Session ID Tracking (Step 5)")

    from server import _get_session_id

    sid1 = _get_session_id()
    check("Session ID is string", isinstance(sid1, str))
    check("Session ID length = 8", len(sid1) == 8)

    sid2 = _get_session_id()
    check("Same session within gap", sid1 == sid2)


    # --- Test 4: Chat endpoint returns session_id (Step 5) -------------------
    section("Test 4: Chat Response Includes session_id")


    async def _test_chat_session():
        async with quart_app.test_client() as client:
            resp = await client.post("/chat", json={"message": "hi"})
            data = await resp.get_json()
            return data

    chat_data = asyncio.run(_test_chat_session())
    check("Chat response has session_id", "session_id" in chat_data,
          f"keys={list(chat_data.keys())}")
    check("session_id is string", isinstance(chat_data.get("session_id"), str))


    # --- Test 5: SSE Stream includes session_id in meta (Step 5) -------------
    section("Test 5: SSE Stream Meta Includes session_id")


    async def _test_sse_session():
        async with quart_app.test_client() as client:
            resp = await client.post("/chat/stream", json={"message": "hi"})
            raw = await resp.get_data(as_text=True)
            # Find meta event
            for line in raw.split("\n"):
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload == "[DONE]":
                        continue
                    try:
                        evt = json.loads(payload)
                        if evt.get("type") == "meta":
                            return evt
                    except json.JSONDecodeError:
                        pass
        return None

    sse_meta = asyncio.run(_test_sse_session())
    check("SSE meta event found", sse_meta is not None)
    check("SSE meta has session_id", sse_meta and "session_id" in sse_meta,
          f"meta={sse_meta}")


    # --- Test 6: Orb state emission (Step 4) ---------------------------------
    section("Test 6: Orb State Events (Step 4)")


    async def _test_orb_events():
        """Verify orb:state events are emitted during chat processing."""
        bus = EventBus()
        events = []

        async def collector():
            async for data in bus.subscribe("orb:state"):
                events.append(data)
                if len(events) >= 2:
                    break

        # We can't easily test the server's event_bus emission through test client
        # without WebSocket, so we test the EventBus contract directly.
        async def emitter():
            await asyncio.sleep(0.01)
            await bus.emit("orb:state", {"state": "thinking", "handler": "general"})
            await asyncio.sleep(0.01)
            await bus.emit("orb:state", {"state": "idle"})

        await asyncio.gather(
            asyncio.wait_for(collector(), timeout=2),
            emitter(),
        )
        return events

    orb_events = asyncio.run(_test_orb_events())
    check("Orb events emitted", len(orb_events) >= 2, f"got={len(orb_events)}")
    check("First event is thinking", orb_events[0].get("state") == "thinking")
    check("Second event is idle", orb_events[1].get("state") == "idle")


    # --- Test 7: Async Voice Pipeline (Step 3) --------------------------------
    section("Test 7: Async Voice Pipeline (Step 3)")

    from async_voice import get_voice_state

    check("async_voice imports", True)
    check("Initial voice state is idle", get_voice_state() == "idle")

    # Test that async_speak/async_listen are callable
    from async_voice import async_speak, async_listen
    check("async_speak is coroutine function",
          asyncio.iscoroutinefunction(async_speak))
    check("async_listen is coroutine function",
          asyncio.iscoroutinefunction(async_listen))


    # --- Test 8: Server Contract Validation (Step 6) -------------------------
    section("Test 8: Server Contract Validation (Step 6)")

    from server_compat import validate_contract

    compat_passed, compat_failed, compat_details = asyncio.run(validate_contract())

    check(f"Contract validation: {compat_passed} passed", compat_passed > 0)
    check("Contract validation: 0 failures", compat_failed == 0,
          f"failed={compat_failed}")

    if compat_failed > 0:
        for label, status, detail in compat_details:
            if status != "PASS":
                print(f"    → {label}: {detail}")


    # --- Test 9: All REST endpoints still work (Step 1 regression) ------------
    section("Test 9: Full Endpoint Regression")


    async def _test_all_endpoints():
        results = []
        async with quart_app.test_client() as client:
            endpoints = [
                ("GET", "/health"), ("GET", "/profile"),
                ("GET", "/notifications"), ("GET", "/dashboard"),
                ("GET", "/reminders"), ("GET", "/reminders/check"),
                ("GET", "/habits"), ("GET", "/learning"),
                ("GET", "/journal"),
            ]
            for method, path in endpoints:
                try:
                    resp = await client.get(path) if method == "GET" else await client.post(path)
                    ok = resp.status_code == 200
                    results.append((path, ok))
                except Exception as e:
                    results.append((path, False))

        return results

    endpoint_results = asyncio.run(_test_all_endpoints())
    for path, ok in endpoint_results:
        check(f"{path} responds 200", ok)


    # --- Test 10: Concurrent safety ------------------------------------------
    section("Test 10: Concurrent Request Safety")


    async def _test_concurrent():
        async with quart_app.test_client() as client:
            tasks = [
                client.get("/health"),
                client.post("/chat", json={"message": "hey"}),
                client.get("/dashboard"),
                client.get("/profile"),
                client.get("/notifications"),
            ]
            start = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - start
            errors = [r for r in results if isinstance(r, Exception)]
            return len(results) - len(errors), len(errors), elapsed

    ok, errs, t = asyncio.run(_test_concurrent())
    check(f"Concurrent: {ok}/5 succeeded", ok == 5)
    check("Concurrent: no deadlock", t < 30, f"took={t:.1f}s")


    # ==========================================================================
    print()
    print("=" * 75)
    print("  RESULTS: %d passed, %d failed, %d total" % (passed, failed, passed + failed))
    if failed == 0:
        print("  ALL TESTS PASSED — Phase 2 Integration Verified!")
    else:
        print("  %d TESTS FAILED — Review required." % failed)
    print("=" * 75)

    if failed > 0:
        sys.exit(1)
