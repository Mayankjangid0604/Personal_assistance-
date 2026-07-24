"""
Phase 2 Step 1 — Async Migration Regression Test Suite.

Tests:
  1. Async Bridge (run_sync, EventBus)
  2. Server import validation (Quart loads without errors)
  3. API contract verification (all endpoints respond correctly)
  4. Brain pipeline integration (process_input works through async bridge)
  5. SSE streaming validation
  6. Concurrent request safety

Run:
    python backend/tests/test_async_migration.py
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
    print("  AISHA -- Phase 2 Step 1 -- Async Migration Regression Test")
    print("=" * 75)


    # --- Test 1: Async Bridge Module ------------------------------------------
    section("Test 1: Async Bridge Module (run_sync + EventBus)")

    from async_bridge import run_sync, event_bus, EventBus, get_event_loop

    check("run_sync imported", callable(run_sync))
    check("event_bus imported", isinstance(event_bus, EventBus))
    check("get_event_loop imported", callable(get_event_loop))


    # Test run_sync with a simple blocking function
    def _blocking_add(a, b):
        time.sleep(0.01)  # simulate blocking work
        return a + b


    async def _test_run_sync():
        result = await run_sync(_blocking_add, 3, 7)
        return result

    loop_result = asyncio.run(_test_run_sync())
    check("run_sync executes blocking function", loop_result == 10, f"got={loop_result}")


    # Test run_sync error propagation
    def _blocking_error():
        raise ValueError("test_error_propagation")


    async def _test_run_sync_error():
        try:
            await run_sync(_blocking_error)
            return False
        except ValueError as e:
            return "test_error_propagation" in str(e)

    error_propagated = asyncio.run(_test_run_sync_error())
    check("run_sync propagates exceptions", error_propagated)


    # Test EventBus pub/sub
    async def _test_event_bus():
        bus = EventBus()
        received = []

        async def subscriber():
            async for data in bus.subscribe("test:event"):
                received.append(data)
                if len(received) >= 2:
                    break

        # Run subscriber and publisher concurrently
        async def publisher():
            await asyncio.sleep(0.01)
            await bus.emit("test:event", {"msg": "hello"})
            await asyncio.sleep(0.01)
            await bus.emit("test:event", {"msg": "world"})

        await asyncio.gather(
            asyncio.wait_for(subscriber(), timeout=2.0),
            publisher(),
        )
        return received

    bus_result = asyncio.run(_test_event_bus())
    check("EventBus delivers events", len(bus_result) == 2, f"got={len(bus_result)}")
    check("EventBus payload correct", bus_result[0].get("msg") == "hello",
          f"got={bus_result[0]}")


    # Test EventBus subscriber count
    async def _test_subscriber_count():
        bus = EventBus()
        count_before = bus.subscriber_count("test:count")

        async def dummy_sub():
            async for _ in bus.subscribe("test:count"):
                break

        task = asyncio.create_task(dummy_sub())
        await asyncio.sleep(0.05)
        count_during = bus.subscriber_count("test:count")
        await bus.emit("test:count", {"done": True})
        await asyncio.sleep(0.05)
        return count_before, count_during

    sb, sd = asyncio.run(_test_subscriber_count())
    check("EventBus subscriber count=0 before", sb == 0, f"got={sb}")
    check("EventBus subscriber count=1 during", sd == 1, f"got={sd}")


    # --- Test 2: Server Import Validation ------------------------------------
    section("Test 2: Server Import Validation (Quart)")

    try:
        from server import app
        check("server.py imports without error", True)
        check("app is a Quart instance", type(app).__name__ == "Quart",
              f"got={type(app).__name__}")
    except Exception as e:
        check("server.py imports without error", False, str(e))
        check("app is a Quart instance", False, "import failed")


    # --- Test 3: API Contract Verification -----------------------------------
    section("Test 3: API Contract (all endpoints via test client)")

    from server import app as quart_app


    async def _test_endpoints():
        """Test all endpoints via Quart's built-in test client."""
        results = []

        async with quart_app.test_client() as client:
            # GET endpoints
            get_endpoints = [
                ("/health", ["status", "assistant", "timestamp"]),
                ("/profile", ["profile"]),
                ("/notifications", ["notifications", "unread_count"]),
                ("/dashboard", ["user_name", "goal", "emotion", "stats"]),
                ("/reminders", ["reminders"]),
                ("/reminders/check", ["triggered"]),
                ("/habits", ["habits"]),
                ("/learning", ["interests", "plans"]),
                ("/journal", ["entries"]),
            ]

            for path, expected_keys in get_endpoints:
                try:
                    resp = await client.get(path)
                    data = await resp.get_json()
                    status_ok = resp.status_code == 200
                    keys_ok = all(k in data for k in expected_keys)
                    results.append((path, status_ok, keys_ok, data))
                except Exception as e:
                    results.append((path, False, False, str(e)))

            # POST /chat
            try:
                resp = await client.post("/chat", json={"message": "hello"})
                data = await resp.get_json()
                chat_ok = resp.status_code == 200
                chat_keys = all(k in data for k in ["response", "role", "emotion", "handler"])
                results.append(("/chat", chat_ok, chat_keys, data))
            except Exception as e:
                results.append(("/chat", False, False, str(e)))

            # POST /chat - missing message
            try:
                resp = await client.post("/chat", json={})
                missing_ok = resp.status_code == 400
                results.append(("/chat (missing msg)", missing_ok, True, None))
            except Exception as e:
                results.append(("/chat (missing msg)", False, False, str(e)))

            # POST /chat - empty message
            try:
                resp = await client.post("/chat", json={"message": ""})
                empty_ok = resp.status_code == 400
                results.append(("/chat (empty msg)", empty_ok, True, None))
            except Exception as e:
                results.append(("/chat (empty msg)", False, False, str(e)))

            # POST /notifications/read
            try:
                resp = await client.post("/notifications/read")
                data = await resp.get_json()
                notif_ok = resp.status_code == 200 and "marked" in data
                results.append(("/notifications/read", notif_ok, True, data))
            except Exception as e:
                results.append(("/notifications/read", False, False, str(e)))

            # POST /reset
            try:
                resp = await client.post("/reset")
                data = await resp.get_json()
                reset_ok = resp.status_code == 200 and "status" in data
                results.append(("/reset", reset_ok, True, data))
            except Exception as e:
                results.append(("/reset", False, False, str(e)))

        return results


    endpoint_results = asyncio.run(_test_endpoints())

    for path, status_ok, keys_ok, data in endpoint_results:
        check(f"{path} — status 200", status_ok,
              f"data={str(data)[:60]}" if not status_ok else "")
        if keys_ok is not None and path not in ("/chat (missing msg)", "/chat (empty msg)"):
            check(f"{path} — JSON schema correct", keys_ok,
                  f"data={str(data)[:80]}" if not keys_ok else "")


    # --- Test 4: SSE Streaming Validation ------------------------------------
    section("Test 4: SSE Streaming Endpoint")


    async def _test_sse_stream():
        """Test that /chat/stream produces valid SSE format."""
        async with quart_app.test_client() as client:
            resp = await client.post("/chat/stream", json={"message": "hello"})

            # Collect raw response via Quart test client API
            raw_data = await resp.get_data(as_text=False)
            text = raw_data.decode("utf-8")
            lines = [l for l in text.strip().split("\n") if l.strip()]

            has_meta = False
            has_chunk = False
            has_done = False

            for line in lines:
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload == "[DONE]":
                        has_done = True
                    else:
                        try:
                            parsed = json.loads(payload)
                            if parsed.get("type") == "meta":
                                has_meta = True
                            elif parsed.get("type") == "chunk":
                                has_chunk = True
                        except json.JSONDecodeError:
                            pass

            return has_meta, has_chunk, has_done, len(lines)


    sse_meta, sse_chunk, sse_done, sse_lines = asyncio.run(_test_sse_stream())
    check("SSE has meta event", sse_meta)
    check("SSE has chunk event", sse_chunk)
    check("SSE has [DONE] terminator", sse_done)
    check("SSE has multiple lines", sse_lines >= 3, f"got={sse_lines}")


    # --- Test 5: Concurrent Request Safety -----------------------------------
    section("Test 5: Concurrent Request Safety")


    async def _test_concurrency():
        """Send multiple simultaneous requests to verify no deadlocks."""
        async with quart_app.test_client() as client:
            tasks = [
                client.get("/health"),
                client.post("/chat", json={"message": "hey"}),
                client.get("/dashboard"),
                client.get("/profile"),
                client.get("/notifications"),
            ]

            start = time.time()
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - start

            errors = [r for r in responses if isinstance(r, Exception)]
            successes = [r for r in responses if not isinstance(r, Exception)]

            return len(successes), len(errors), elapsed


    conc_ok, conc_err, conc_time = asyncio.run(_test_concurrency())
    check(f"Concurrent: {conc_ok}/5 succeeded", conc_ok == 5,
          f"errors={conc_err}")
    check("Concurrent: no deadlock (< 30s)", conc_time < 30,
          f"took={conc_time:.1f}s")
    check("Concurrent: zero errors", conc_err == 0)


    # --- Test 6: Brain Pipeline through Async Bridge -------------------------
    section("Test 6: Brain Pipeline via Async Bridge")


    async def _test_brain_async():
        """Verify process_input works correctly through run_sync."""
        from brain import process_input as pi, BrainResult
        result = await run_sync(pi, "what time is it?")
        return result, isinstance(result, BrainResult)


    brain_result, is_brain_result = asyncio.run(_test_brain_async())
    check("process_input via run_sync returns BrainResult", is_brain_result)
    check("BrainResult has response", hasattr(brain_result, "response") and brain_result.response)
    check("BrainResult has handler", hasattr(brain_result, "handler") and brain_result.handler)
    check("BrainResult has emotion", hasattr(brain_result, "emotion"))


    # --- Test 7: Health endpoint version field --------------------------------
    section("Test 7: Version & Metadata")


    async def _test_version():
        async with quart_app.test_client() as client:
            resp = await client.get("/health")
            data = await resp.get_json()
            return data


    health_data = asyncio.run(_test_version())
    check("Health reports version 3.0.0+ or newer",
          any(health_data.get("version", "").startswith(v) for v in ["3.0.0", "5.0.0", "6.0.0"]),
          f"got={health_data.get('version')}")
    check("Health status=online", health_data.get("status") == "online")


    # ==========================================================================
    print()
    print("=" * 75)
    print("  RESULTS: %d passed, %d failed, %d total" % (passed, failed, passed + failed))
    if failed == 0:
        print("  ALL TESTS PASSED -- Async migration verified!")
    else:
        print("  %d TESTS FAILED -- Review required." % failed)
    print("=" * 75)

    if failed > 0:
        sys.exit(1)
