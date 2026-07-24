"""
Phase 2 Experience Layer -- Complete Test Suite.

Tests all Phase 2 Experience Layer components:
  Step 1: STT Engine architecture
  Step 2: TTS Engine architecture
  Step 3: Conversation Engine state machine
  Step 4: Orb state synchronization
  Step 5: Personality Adaptation Layer
  Step 6: Contextual Conversation Continuity
  Step 7: Latency diagnostics
  + Full endpoint regression

Run:
    python backend/tests/test_phase2_experience.py
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
    print("  AISHA -- Phase 2 Experience Layer -- Complete Test")
    print("=" * 75)


    # --- Test 1: Database schema updated ------------------------------------
    section("Test 1: Database Schema (Phase 2 Tables)")

    from database.db import get_connection

    with get_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {r[0] for r in tables}

    check("personality_preferences table exists",
          "personality_preferences" in table_names)
    check("conversation_context table exists",
          "conversation_context" in table_names)
    check("conversation_goals table exists",
          "conversation_goals" in table_names)
    check("session_summaries table exists",
          "session_summaries" in table_names)


    # --- Test 2: Personality Repository -------------------------------------
    section("Test 2: Personality Repository")

    from database.repositories import personality_repo

    # Clean up
    personality_repo.clear_preferences()

    personality_repo.save_preference("warmth", 0.7, 0.5)
    result = personality_repo.get_preference("warmth")
    check("Save/get preference works", result is not None)
    check("Preference value correct", result and result[0] == 0.7)
    check("Preference confidence correct", result and result[1] == 0.5)

    personality_repo.update_confidence("warmth", 0.1)
    result2 = personality_repo.get_preference("warmth")
    check("Confidence updated", result2 and result2[1] == 0.6,
          f"got={result2[1] if result2 else None}")

    all_prefs = personality_repo.get_all_preferences()
    check("get_all_preferences works", "warmth" in all_prefs)

    # Clean up
    personality_repo.clear_preferences()


    # --- Test 3: Personality Engine -----------------------------------------
    section("Test 3: Personality Adaptation Engine (Step 5)")

    from personality import PersonalityEngine, DIMENSIONS

    # Fresh engine (no persisted data)
    personality_repo.clear_preferences()
    engine = PersonalityEngine()

    profile = engine.get_profile()
    check("Profile has all dimensions", len(profile) == len(DIMENSIONS),
          f"got={len(profile)}")
    check("Each dimension has value", all("value" in v for v in profile.values()))
    check("Each dimension has confidence", all("confidence" in v for v in profile.values()))
    check("Each dimension has label", all("label" in v for v in profile.values()))

    # Test observation: casual input
    adjustments = engine.observe_interaction(
        "yo bro whats up lol", "Hey!", "happy", "general"
    )
    check("Casual input detected adjustments", len(adjustments) > 0,
          f"adjustments={adjustments}")

    formality_after = engine.get_dimension("formality")
    check("Formality decreased (casual signals)", formality_after < 0.4,
          f"got={formality_after}")

    # Test observation: formal input
    engine2 = PersonalityEngine()
    adj2 = engine2.observe_interaction(
        "Could you please help me with this sir", "Of course!", "neutral", "general"
    )
    check("Formal input detected adjustments", len(adj2) > 0)

    # Test context prompt
    prompt = engine.get_context_prompt()
    check("Context prompt is string", isinstance(prompt, str))

    # Test adapt_response
    adapted = engine.adapt_response("I understand.", "neutral")
    check("adapt_response returns string", isinstance(adapted, str))

    # Clean up
    personality_repo.clear_preferences()


    # --- Test 4: Context Tracker (Step 6) -----------------------------------
    section("Test 4: Contextual Conversation Continuity (Step 6)")

    from context_tracker import ContextTracker, extract_topics, extract_key_terms

    # Topic extraction
    topics = extract_topics("I need help with my python code for the project")
    check("Topic extraction works", len(topics) > 0, f"got={topics}")
    check("Coding topic detected", "coding" in topics)

    topics2 = extract_topics("I'm stressed about my exam tomorrow")
    check("Study topic detected", "study" in topics2)

    # Key terms
    terms = extract_key_terms("help me understand quantum computing algorithms")
    check("Key terms extracted", len(terms) > 0, f"got={terms}")
    check("Stopwords filtered", "about" not in terms)

    # Context tracker
    tracker = ContextTracker()

    turn1 = tracker.track_turn("sess1", "help me with python coding", "Sure!", "neutral", "general")
    check("track_turn returns dict", isinstance(turn1, dict))
    check("Topics detected in turn", "coding" in turn1.get("topics", []))
    check("Turn number tracked", turn1.get("turn_number") == 1)

    turn2 = tracker.track_turn("sess1", "what about javascript?", "JS is great!", "happy", "general")
    check("Second turn incremented", turn2.get("turn_number") == 2)

    active = tracker.get_active_topics()
    check("Active topics tracked", len(active) > 0, f"got={active}")

    session_topics = tracker.get_session_topics("sess1")
    check("Session topics accumulated", len(session_topics) > 0)

    # Emotional trajectory
    trajectory = tracker.get_emotional_trajectory("sess1")
    check("Trajectory has dominant", "dominant" in trajectory)
    check("Trajectory has trend", "trend" in trajectory)
    check("Trajectory has emotions list", "emotions" in trajectory)

    # Session finalization
    summary = tracker.finalize_session("sess1")
    check("Session finalized", summary is not None)
    check("Summary has topics", "topics" in summary)
    check("Summary has turn count", summary.get("turn_count") == 2)

    # Context window
    window = tracker.get_context_window()
    check("Context window is string", isinstance(window, str))

    # Goal tracking
    goal_id = tracker.add_goal("Learn Python basics")
    check("Goal created", goal_id > 0, f"id={goal_id}")

    goals = tracker.get_goals()
    check("Goal retrievable", len(goals) > 0)

    tracker.update_goal(goal_id, 0.5)
    goals2 = tracker.get_goals()
    check("Goal progress updated", goals2[0].get("progress") == 0.5)


    # --- Test 5: STT Engine Architecture (Step 1) --------------------------
    section("Test 5: STT Engine Architecture (Step 1)")

    from stt_engine import STTEngine, SpeechRecognitionSTT, stt_engine

    check("stt_engine is STTEngine", isinstance(stt_engine, STTEngine))
    check("stt_engine not listening initially", not stt_engine.is_listening())
    check("STTEngine has recognize method", hasattr(stt_engine, "recognize"))
    check("STTEngine has start_continuous", hasattr(stt_engine, "start_continuous"))
    check("STTEngine has stop_continuous", hasattr(stt_engine, "stop_continuous"))


    # --- Test 6: TTS Engine Architecture (Step 2) --------------------------
    section("Test 6: TTS Engine Architecture (Step 2)")

    from tts_engine import TTSEngine, Pyttsx3TTS, tts_engine, split_into_chunks

    check("tts_engine is TTSEngine", isinstance(tts_engine, TTSEngine))
    check("tts_engine not speaking initially", not tts_engine.is_speaking())
    check("TTSEngine has speak method", hasattr(tts_engine, "speak"))
    check("TTSEngine has speak_streamed", hasattr(tts_engine, "speak_streamed"))
    check("TTSEngine has interrupt", hasattr(tts_engine, "interrupt"))

    # Test sentence splitting
    chunks = split_into_chunks("Hello! How are you? I'm doing great today.")
    check("Sentence splitter works", len(chunks) >= 1, f"chunks={chunks}")

    chunks2 = split_into_chunks("Short.")
    check("Single sentence handled", len(chunks2) == 1)

    long_text = "This is sentence one. " * 20
    chunks3 = split_into_chunks(long_text, max_chunk_len=100)
    check("Long text split into multiple chunks", len(chunks3) > 1,
          f"chunks={len(chunks3)}")


    # --- Test 7: Conversation Engine (Step 3) -------------------------------
    section("Test 7: Conversation Engine (Step 3)")

    from conversation_engine import ConversationEngine, ConversationState

    ce = ConversationEngine()
    check("Initial state is IDLE", ce.state == ConversationState.IDLE)
    check("Voice not active initially", not ce.is_voice_active)

    # Test process_text
    result = asyncio.run(ce.process_text("hello", "test_session"))
    check("process_text returns dict", isinstance(result, dict))
    check("Result has response", "response" in result)
    check("Result has handler", "handler" in result)
    check("Result has emotion", "emotion" in result)
    check("Result has latency_ms", "latency_ms" in result)
    check("Result has turn count", "turn" in result)
    check("Result has personality profile", "personality_profile" in result)

    # Latency stats
    stats = ce.get_latency_stats()
    check("Latency stats has stt_ms", "stt_ms" in stats)
    check("Latency stats has brain_ms", "brain_ms" in stats)
    check("Latency stats has tts_ms", "tts_ms" in stats)

    # Status
    status = ce.get_status()
    check("Status has state", "state" in status)
    check("Status has turn_count", "turn_count" in status)


    # --- Test 8: EventBus Orb State Events (Step 4) -------------------------
    section("Test 8: Orb State Events (Step 4)")

    from async_bridge import EventBus


    async def _test_orb_states():
        bus = EventBus()
        events = []

        async def collector():
            async for data in bus.subscribe("orb:state"):
                events.append(data)
                if len(events) >= 4:
                    break

        async def emitter():
            await asyncio.sleep(0.01)
            # Simulate a full conversation cycle
            await bus.emit("orb:state", {"state": "listening"})
            await asyncio.sleep(0.01)
            await bus.emit("orb:state", {"state": "processing"})
            await asyncio.sleep(0.01)
            await bus.emit("orb:state", {"state": "speaking"})
            await asyncio.sleep(0.01)
            await bus.emit("orb:state", {"state": "idle"})

        await asyncio.gather(
            asyncio.wait_for(collector(), timeout=3),
            emitter(),
        )
        return events

    orb_events = asyncio.run(_test_orb_states())
    check("All orb states emitted", len(orb_events) >= 4, f"got={len(orb_events)}")

    expected_states = ["listening", "processing", "speaking", "idle"]
    actual_states = [e.get("state") for e in orb_events]
    check("Correct state sequence", actual_states == expected_states,
          f"got={actual_states}")


    # --- Test 9: Server Endpoints (Phase 2 APIs) ----------------------------
    section("Test 9: Phase 2 API Endpoints")

    from server import app as quart_app


    async def _test_phase2_endpoints():
        results = []
        async with quart_app.test_client() as client:
            # Phase 2 endpoints
            endpoints = [
                ("GET", "/personality"),
                ("GET", "/context"),
                ("GET", "/voice/status"),
                ("GET", "/conversation/status"),
                # Original endpoints (regression)
                ("GET", "/health"),
                ("GET", "/profile"),
                ("GET", "/notifications"),
                ("GET", "/dashboard"),
                ("GET", "/habits"),
                ("GET", "/learning"),
                ("GET", "/journal"),
            ]
            for method, path in endpoints:
                try:
                    resp = await client.get(path)
                    data = await resp.get_json()
                    ok = resp.status_code == 200 and data is not None
                    results.append((path, ok, data))
                except Exception as e:
                    results.append((path, False, str(e)))
        return results

    ep_results = asyncio.run(_test_phase2_endpoints())
    for path, ok, data in ep_results:
        check(f"{path} responds 200", ok)

    # Specific field checks
    for path, ok, data in ep_results:
        if path == "/personality" and ok:
            check("/personality has profile", "profile" in data)
        elif path == "/context" and ok:
            check("/context has context_window", "context_window" in data)
        elif path == "/voice/status" and ok:
            check("/voice/status has conversation", "conversation" in data)
        elif path == "/conversation/status" and ok:
            check("/conversation/status has state", "state" in data)
        elif path == "/health" and ok:
            check("/health version is current", data.get("version", "") != "", f"got={data.get('version')}")


    # --- Test 10: Chat with personality + context integration ----------------
    section("Test 10: Integrated Chat (Personality + Context)")


    async def _test_integrated_chat():
        async with quart_app.test_client() as client:
            # Send a message
            resp = await client.post("/chat", json={"message": "hey bro help me study coding"})
            data = await resp.get_json()
            return data

    chat_result = asyncio.run(_test_integrated_chat())
    check("Chat response received", "response" in chat_result)
    check("Chat has session_id", "session_id" in chat_result)
    check("Chat has handler", "handler" in chat_result)


    # --- Test 11: Concurrent safety with Phase 2 modules --------------------
    section("Test 11: Concurrent Safety")


    async def _test_concurrent():
        async with quart_app.test_client() as client:
            tasks = [
                client.get("/health"),
                client.post("/chat", json={"message": "hello"}),
                client.get("/personality"),
                client.get("/context"),
                client.get("/voice/status"),
                client.get("/dashboard"),
            ]
            start = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - start
            errors = [r for r in results if isinstance(r, Exception)]
            return len(results) - len(errors), len(errors), elapsed

    ok, errs, t = asyncio.run(_test_concurrent())
    check(f"Concurrent: {ok}/6 succeeded", ok == 6)
    check("Concurrent: no deadlock", t < 30, f"took={t:.1f}s")


    # --- Test 12: Latency measurement (Step 7) ------------------------------
    section("Test 12: Latency Optimization Verification (Step 7)")


    async def _test_latency():
        from conversation_engine import ConversationEngine
        ce2 = ConversationEngine()

        t0 = time.time()
        result = await ce2.process_text("hi", "latency_test")
        total = (time.time() - t0) * 1000  # ms
        return total, result.get("latency_ms", 0)

    wall_ms, reported_ms = asyncio.run(_test_latency())
    check(f"Brain pipeline < 2000ms", wall_ms < 2000, f"wall={wall_ms:.0f}ms")
    check("Latency tracking works", reported_ms > 0, f"reported={reported_ms}ms")


    # ==========================================================================
    print()
    print("=" * 75)
    print("  RESULTS: %d passed, %d failed, %d total" % (passed, failed, passed + failed))
    if failed == 0:
        print("  ALL TESTS PASSED -- Phase 2 Experience Layer Verified!")
    else:
        print("  %d TESTS FAILED -- Review required." % failed)
    print("=" * 75)

    if failed > 0:
        sys.exit(1)
