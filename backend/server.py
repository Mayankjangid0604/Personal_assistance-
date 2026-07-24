"""
Aisha AI Assistant -- Quart API Server (Phase 2: Async-Ready).

Exposes a REST API so the React frontend can communicate with Aisha's
brain pipeline over HTTP.  Migrated from Flask to Quart for native
async/await support, WebSocket readiness, and non-blocking I/O.

API Contract
------------
All endpoints, URL paths, HTTP methods, and JSON schemas are **identical**
to the Phase 1 Flask server.  This is a drop-in replacement.

Endpoints
---------
POST /chat
    Send a user message and receive Aisha's response.
POST /chat/stream
    SSE streaming chat endpoint (token-by-token).
GET  /health
    Quick health-check (returns server status).
GET  /profile
    Returns the current user profile stored in memory.
POST /reset
    Clears all memory (short-term + long-term).
GET  /notifications
    Returns recent notifications and unread count.
POST /notifications/read
    Marks all notifications as read.
GET  /dashboard
    Returns dashboard stats for the frontend panel.
GET  /reminders
    Returns all pending reminders.
GET  /reminders/check
    Returns any newly triggered reminders.
GET  /habits
    Returns all habits with streaks.
GET  /learning
    Returns learning interests and active plans.
GET  /journal
    Returns journal entries.

Usage:
    python backend/server.py
"""

import asyncio
import json as _json
import os
import sys
import uuid
from datetime import datetime

# ---------------------------------------------------------------------------
# Path setup -- allow imports from sibling packages
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_DATABASE_DIR = os.path.join(_PROJECT_ROOT, "database")

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
if _DATABASE_DIR not in sys.path:
    sys.path.insert(0, _DATABASE_DIR)

# ---------------------------------------------------------------------------
# Quart setup (async Flask-compatible)
# ---------------------------------------------------------------------------
from quart import Quart, request, jsonify, Response, websocket
from quart_cors import cors

from brain import process_input, aisha_memory, get_emotion_trend
from llm_router import generate_ai_response_stream
from scheduler import get_triggered_reminders
from notifications import get_notifications, get_unread_count, mark_all_read
from notifications import get_journal_entries
from scheduler import list_reminders
from learning import get_top_interests
from learning import _data as _learning_data
from power_tools import _data as _power_data

# Async bridge for running sync brain pipeline off the event loop
from async_bridge import run_sync, event_bus

# Phase 2 Experience Layer
from personality import personality_engine
from context_tracker import context_tracker
from conversation_engine import conversation_engine

# Phase 3 Cognitive System
from cognitive_orchestrator import orchestrator as cognitive_orchestrator
from presence import presence_engine
from desktop_awareness import desktop_awareness
from episodic_memory import episodic_memory
from cognitive_planner import cognitive_planner

# Phase 4 AI Operating Layer
from workflow_intelligence import workflow_intelligence
from cross_app_context import cross_app_context
from productivity_cognition import productivity_engine
from environmental_reasoning import environment as env_reasoning
from agentic_executor import executor as agentic_executor
from automation_governor import automation_governor
from human_oversight import human_oversight

# Phase 5 Ecosystem
from routine_intelligence import routine_intelligence
from behavioral_model import behavioral_model
from reflective_cognition import reflective_cognition
from ecosystem_memory import ecosystem_memory
from evolutionary_personalization import evolutionary_personalization
from life_management import life_management
from nl_automation import nl_automation
from continuity import continuity


app = Quart(__name__)
app = cors(app)  # Allow requests from React dev server (localhost:5173)


# ---------------------------------------------------------------------------
# Session Management (Step 5)
# ---------------------------------------------------------------------------
_current_session_id: str = str(uuid.uuid4())[:8]
_last_message_time: float = 0.0
_SESSION_GAP_SECONDS = 300  # 5 minutes of silence → new session


def _get_session_id() -> str:
    """Return the current session ID, rotating if there's been a long gap."""
    global _current_session_id, _last_message_time
    import time
    now = time.time()
    if _last_message_time > 0 and (now - _last_message_time) > _SESSION_GAP_SECONDS:
        # Finalize the old session before rotating
        old_id = _current_session_id
        context_tracker.finalize_session(old_id)
        _current_session_id = str(uuid.uuid4())[:8]
    _last_message_time = now
    return _current_session_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/chat", methods=["POST"])
async def chat():
    """
    Main chat endpoint.

    Expects JSON: { "message": "user input" }
    Returns JSON: { "response": "...", "role": "...", "emotion": "...",
                     "style": "...", "task": false }
    """
    data = await request.get_json(silent=True)

    if not data or "message" not in data:
        return jsonify({"error": "Missing 'message' field."}), 400

    message = data["message"].strip()
    if not message:
        return jsonify({"error": "Message cannot be empty."}), 400

    # Log incoming request
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"  [{timestamp}]  User: {message}")

    # Emit orb state: thinking (Step 4)
    await event_bus.emit("orb:state", {"state": "thinking", "handler": "general"})

    # Process through the brain pipeline via conversation engine
    try:
        sid = _get_session_id()
        result = await conversation_engine.process_text(message, session_id=sid)
    except Exception as e:
        print(f"  [ERROR] {e}")
        await event_bus.emit("orb:state", {"state": "idle"})
        return jsonify({"error": "Internal processing error."}), 500

    # Emit orb state: responding → idle (Step 4)
    await event_bus.emit("orb:state", {"state": "responding", "handler": result["handler"]})

    # Log response
    print(f"  [{timestamp}]  Aisha: {result['response']}")
    print()

    # Emit idle after response
    await event_bus.emit("orb:state", {"state": "idle"})

    return jsonify({
        "response":       result["response"],
        "role":           result.get("role", "assistant"),
        "emotion":        result["emotion"],
        "response_style": result.get("response_style", ""),
        "task_detected":  result.get("task_detected", False),
        "handler":        result["handler"],
        "session_id":     sid,
        "cognitive":      result.get("cognitive", {}),
        "operating":      result.get("operating", {}),
        "ecosystem":      result.get("ecosystem", {}),
    })


@app.route("/chat/stream", methods=["POST"])
async def chat_stream():
    """
    SSE streaming chat endpoint.

    Streams Gemini's response token-by-token as Server-Sent Events.
    Falls back to a single-chunk response for simple queries.

    SSE format:
        data: {"type": "meta", "handler": "general", "emotion": "neutral"}
        data: {"type": "chunk", "text": "Hello"}
        data: {"type": "chunk", "text": " there!"}
        data: [DONE]
    """
    # json already imported at module level as _json

    data = await request.get_json(silent=True)
    if not data or "message" not in data:
        return jsonify({"error": "Missing 'message' field."}), 400

    message = data["message"].strip()
    if not message:
        return jsonify({"error": "Message cannot be empty."}), 400

    async def generate_sse():
        # Emit orb state: thinking (Step 4)
        await event_bus.emit("orb:state", {"state": "thinking", "handler": "general"})

        # Run the full brain pipeline (sync → async bridge)
        try:
            result = await run_sync(process_input, message)
            handler = result.handler
            emotion = result.emotion
        except Exception as e:
            handler = "general"
            emotion = "neutral"
            await event_bus.emit("orb:state", {"state": "idle"})
            yield f"data: {_json.dumps({'type': 'error', 'text': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # If NOT general, the brain pipeline already produced the response.
        # Send it as a single chunk (only general/LLM benefits from streaming).
        if handler != "general":
            await event_bus.emit("orb:state", {"state": "responding", "handler": handler})
            yield f"data: {_json.dumps({'type': 'meta', 'handler': handler, 'emotion': emotion, 'session_id': _get_session_id()})}\n\n"
            yield f"data: {_json.dumps({'type': 'chunk', 'text': result.response})}\n\n"
            yield "data: [DONE]\n\n"
            await event_bus.emit("orb:state", {"state": "idle"})
            return

        # For general handler: stream the LLM response token-by-token
        await event_bus.emit("orb:state", {"state": "responding", "handler": handler})
        yield f"data: {_json.dumps({'type': 'meta', 'handler': handler, 'emotion': emotion, 'session_id': _get_session_id()})}\n\n"

        user_name = aisha_memory.get_user_info("name") or "User"
        from power_tools import get_extended_context
        llm_context = {
            "user_name": user_name,
            "emotion": emotion,
            "role": result.role,
            "chat_history": get_extended_context(aisha_memory, limit=10),
        }

        full_response = ""
        try:
            # Run the sync streaming generator in a thread and yield chunks
            for chunk in await run_sync(
                lambda: list(generate_ai_response_stream(message, llm_context))
            ):
                full_response += chunk
                yield f"data: {_json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'text': str(e)})}\n\n"

        # Memory was already stored by process_input for non-streaming.
        # For streaming, store the streamed LLM response.
        if full_response:
            await run_sync(
                aisha_memory.add_conversation, message, result.role, full_response
            )
            from learning import track_topics
            from power_tools import record_behaviour
            await run_sync(track_topics, message)
            await run_sync(record_behaviour, message)

        await event_bus.emit("orb:state", {"state": "idle"})
        yield "data: [DONE]\n\n"

    return Response(
        generate_sse(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/reminders/check", methods=["GET"])
async def reminders_check():
    """Return any newly triggered reminders (for native notification bridge)."""
    triggered = await run_sync(get_triggered_reminders)
    return jsonify({
        "triggered": [
            {"id": r.get("id"), "task": r.get("task"), "time": r.get("time")}
            for r in triggered
        ]
    })


@app.route("/health", methods=["GET"])
async def health():
    """Quick health-check endpoint."""
    return jsonify({
        "status": "online",
        "assistant": "Aisha",
        "version": "6.0.0-personalized",
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/profile", methods=["GET"])
async def profile():
    """Return the current user profile from long-term memory."""
    return jsonify({
        "profile": aisha_memory.get_all_user_info(),
    })


@app.route("/reset", methods=["POST"])
async def reset():
    """Clear all memory (short-term + long-term)."""
    await run_sync(aisha_memory.clear_short_term)
    await run_sync(aisha_memory.clear_long_term)
    print("  [RESET] Memory cleared.")
    return jsonify({"status": "Memory cleared."})


@app.route("/notifications", methods=["GET"])
async def notifications():
    """Return recent notifications and unread count."""
    return jsonify({
        "notifications": get_notifications(limit=20),
        "unread_count": get_unread_count(),
    })


@app.route("/notifications/read", methods=["POST"])
async def notifications_read():
    """Mark all notifications as read."""
    count = mark_all_read()
    return jsonify({"marked": count})


# --- Panel Data APIs ---

@app.route("/dashboard", methods=["GET"])
async def dashboard():
    """Return dashboard stats for the frontend panel."""
    profile_data = aisha_memory.get_all_user_info() or {}
    conversations = aisha_memory.get_recent_conversations()
    reminders = list_reminders()
    habits = _power_data.get("habits", {})
    trend = get_emotion_trend()

    return jsonify({
        "user_name":    profile_data.get("name", "User"),
        "goal":         profile_data.get("goal", "Not set"),
        "emotion":      profile_data.get("last_emotion", "neutral"),
        "emotion_trend": trend,
        "stats": {
            "conversations": len(conversations),
            "reminders":     len(reminders),
            "habits":        len(habits),
            "interests":     len(_learning_data.get("interests", {})),
        },
    })


@app.route("/reminders", methods=["GET"])
async def reminders_list():
    """Return all pending reminders."""
    pending = list_reminders()
    return jsonify({"reminders": pending})


@app.route("/habits", methods=["GET"])
async def habits_list():
    """Return all habits with streaks."""
    habits = _power_data.get("habits", {})
    from datetime import date
    today = date.today().isoformat()

    habit_list = []
    for key, h in habits.items():
        habit_list.append({
            "id":          key,
            "name":        h.get("name", key),
            "streak":      h.get("streak", 0),
            "best_streak": h.get("best_streak", 0),
            "total":       h.get("total_completions", 0),
            "done_today":  h.get("last_done") == today,
        })

    return jsonify({"habits": habit_list})


@app.route("/learning", methods=["GET"])
async def learning_data():
    """Return learning interests and active plans."""
    interests = get_top_interests(10)
    plans = _learning_data.get("milestones", [])

    plan_list = []
    for p in plans:
        done = sum(1 for s in p.get("steps", []) if s.get("done"))
        total = len(p.get("steps", []))
        plan_list.append({
            "topic":    p.get("topic", "unknown"),
            "done":     done,
            "total":    total,
            "percent":  int(done / total * 100) if total else 0,
            "steps":    p.get("steps", []),
        })

    return jsonify({
        "interests": [{"topic": t, "count": c} for t, c in interests],
        "plans":     plan_list,
    })


@app.route("/journal", methods=["GET"])
async def journal_list():
    """Return journal entries."""
    entries = get_journal_entries(limit=20)
    return jsonify({"entries": entries})


# --- Phase 2 Experience Layer APIs ---

@app.route("/personality", methods=["GET"])
async def personality_profile():
    """Return the adaptive personality profile."""
    profile = personality_engine.get_profile()
    context_prompt = personality_engine.get_context_prompt()
    return jsonify({
        "profile": profile,
        "context_prompt": context_prompt,
    })


@app.route("/context", methods=["GET"])
async def context_window():
    """Return the current conversation context."""
    window = context_tracker.get_context_window()
    active_topics = context_tracker.get_active_topics()
    goals = context_tracker.get_goals()
    return jsonify({
        "context_window": window,
        "active_topics": active_topics,
        "goals": goals,
    })


@app.route("/voice/status", methods=["GET"])
async def voice_status():
    """Return the current voice/conversation engine status."""
    return jsonify({
        "conversation": conversation_engine.get_status(),
        "latency": conversation_engine.get_latency_stats(),
    })


@app.route("/conversation/status", methods=["GET"])
async def conversation_status():
    """Return full conversation engine diagnostics."""
    return jsonify({
        "state": conversation_engine.state.value,
        "voice_active": conversation_engine.is_voice_active,
        "latency": conversation_engine.get_latency_stats(),
        "personality": personality_engine.get_profile(),
        "active_topics": context_tracker.get_active_topics(),
    })


# ---------------------------------------------------------------------------
# Phase 3: Cognitive System Endpoints
# ---------------------------------------------------------------------------

@app.route("/memory/search", methods=["GET"])
async def memory_search():
    """Semantic memory recall."""
    query = request.args.get("q", "")
    top_k = int(request.args.get("top_k", 5))
    results = cognitive_orchestrator.recall(query, top_k=top_k)
    return jsonify(results)


@app.route("/episodes", methods=["GET"])
async def get_episodes():
    """Return recent life episodes."""
    category = request.args.get("category")
    limit = int(request.args.get("limit", 10))
    episodes = episodic_memory.get_recent_episodes(limit=limit, category=category)
    arc = episodic_memory.get_emotional_arc(days=14)
    return jsonify({
        "episodes": episodes,
        "emotional_arc": arc,
    })


@app.route("/desktop/status", methods=["GET"])
async def desktop_status():
    """Return current desktop awareness status."""
    status = desktop_awareness.get_status()
    return jsonify(status)


@app.route("/cognitive/status", methods=["GET"])
async def cognitive_status():
    """Return full cognitive system diagnostics."""
    return jsonify({
        "orchestrator": cognitive_orchestrator.get_status(),
        "presence": presence_engine.get_status(),
        "desktop": desktop_awareness.get_status(),
        "plans": cognitive_planner.get_active_plans(),
    })


@app.route("/presence/status", methods=["GET"])
async def get_presence_status():
    """Return presence governor status."""
    return jsonify(presence_engine.get_status())


@app.route("/presence/tier", methods=["POST"])
async def set_presence_tier():
    """Set the presence governor escalation tier."""
    data = await request.get_json(silent=True)
    tier = int(data.get("tier", 2)) if data else 2
    presence_engine.set_tier(tier)
    return jsonify({"tier": presence_engine.governor.tier})


# ---------------------------------------------------------------------------
# Phase 4: AI Operating Layer Endpoints
# ---------------------------------------------------------------------------

@app.route("/workflow/status", methods=["GET"])
async def workflow_status():
    """Return active workflow and workflow intelligence status."""
    return jsonify(workflow_intelligence.get_status())


@app.route("/workspace/context", methods=["GET"])
async def workspace_context():
    """Return unified cross-application workspace context."""
    return jsonify(cross_app_context.get_status())


@app.route("/productivity/status", methods=["GET"])
async def productivity_status():
    """Return productivity cognition status."""
    return jsonify(productivity_engine.get_status())


@app.route("/environment/status", methods=["GET"])
async def environment_status():
    """Return environmental reasoning mode status."""
    return jsonify(env_reasoning.get_status())


@app.route("/executor/status", methods=["GET"])
async def executor_status():
    """Return agentic executor status and pending actions."""
    return jsonify({
        "status": agentic_executor.get_status(),
        "pending": agentic_executor.get_pending(),
    })


@app.route("/executor/action", methods=["POST"])
async def executor_action():
    """Request an agentic action. Requires permission gate."""
    data = await request.get_json(silent=True)
    if not data or "action" not in data:
        return jsonify({"error": "Missing 'action' field"}), 400

    action = data["action"]
    params = data.get("params", {})
    reason = data.get("reason", "User-requested action")

    result = agentic_executor.request(
        action=action,
        params=params,
        reason=reason,
        auto_approve=data.get("auto_approve", False),
    )
    return jsonify(result)


@app.route("/executor/approve/<action_id>", methods=["POST"])
async def executor_approve(action_id: str):
    """Approve a pending agentic action."""
    result = agentic_executor.approve(action_id)
    return jsonify(result)


@app.route("/executor/cancel/<action_id>", methods=["POST"])
async def executor_cancel(action_id: str):
    """Cancel a pending agentic action."""
    result = agentic_executor.cancel(action_id)
    return jsonify(result)


@app.route("/executor/log", methods=["GET"])
async def executor_audit_log():
    """Return agentic executor audit log."""
    limit = int(request.args.get("limit", 20))
    return jsonify({"log": agentic_executor.get_audit_log(limit=limit)})


@app.route("/automation/status", methods=["GET"])
async def automation_status():
    """Return automation governor status."""
    return jsonify(automation_governor.get_status())


@app.route("/automation/tier", methods=["POST"])
async def set_automation_tier():
    """Set the automation governor tier."""
    data = await request.get_json(silent=True)
    tier = int(data.get("tier", 2)) if data else 2
    automation_governor.set_tier(tier)
    agentic_executor.set_autonomy_tier(tier)
    return jsonify({"tier": automation_governor.tier})


@app.route("/operating/status", methods=["GET"])
async def operating_layer_status():
    """Return unified Phase 4 AI Operating Layer status."""
    return jsonify({
        "workflow": workflow_intelligence.get_status(),
        "workspace": cross_app_context.get_status(),
        "productivity": productivity_engine.get_status(),
        "environment": env_reasoning.get_status(),
        "executor": agentic_executor.get_status(),
        "automation_governor": automation_governor.get_status(),
    })


# ---------------------------------------------------------------------------
# Phase 5: Ecosystem Intelligence Endpoints
# ---------------------------------------------------------------------------

@app.route("/routine/status", methods=["GET"])
async def routine_status():
    """Return routine intelligence patterns and focus windows."""
    return jsonify(routine_intelligence.get_status())


@app.route("/routine/summary", methods=["GET"])
async def routine_summary():
    """Return behavioral summary for the last N days."""
    days = int(request.args.get("days", 7))
    return jsonify(routine_intelligence.get_behavioral_summary(days=days))


@app.route("/behavioral/model", methods=["GET"])
async def behavioral_model_status():
    """Return long-term behavioral model and trend analysis."""
    return jsonify(behavioral_model.get_status())


@app.route("/reflection/status", methods=["GET"])
async def reflection_status():
    """Return reflective cognition status and pending insights."""
    return jsonify(reflective_cognition.get_status())


@app.route("/reflection/generate", methods=["POST"])
async def generate_reflection():
    """Force-generate a new reflective insight."""
    insight = reflective_cognition.generate_reflection()
    return jsonify({"insight": insight})


@app.route("/ecosystem/timeline", methods=["GET"])
async def ecosystem_timeline():
    """Return recent ecosystem timeline events."""
    days = int(request.args.get("days", 7))
    return jsonify({
        "timeline": ecosystem_memory.get_recent_timeline(days=days),
        "continuity_summary": ecosystem_memory.get_continuity_summary(),
    })


@app.route("/ecosystem/status", methods=["GET"])
async def ecosystem_status():
    """Return unified Phase 5 ecosystem status."""
    return jsonify({
        "routine": routine_intelligence.get_status(),
        "behavioral_model": behavioral_model.get_status(),
        "reflection": reflective_cognition.get_status(),
        "ecosystem_memory": ecosystem_memory.get_status(),
        "personalization": evolutionary_personalization.get_status(),
        "life_management": life_management.get_status(),
        "nl_automation": nl_automation.get_status(),
        "continuity": continuity.get_status(),
    })


@app.route("/personalization/status", methods=["GET"])
async def personalization_status():
    """Return evolutionary personalization status and drift context."""
    return jsonify(evolutionary_personalization.get_status())


@app.route("/life/goals", methods=["GET"])
async def life_goals():
    """Return all active life goals."""
    return jsonify({"goals": life_management.get_active_goals()})


@app.route("/life/goal", methods=["POST"])
async def create_life_goal():
    """Create a new life goal."""
    data = await request.get_json(silent=True)
    if not data or "title" not in data:
        return jsonify({"error": "Missing 'title' field"}), 400
    result = life_management.create_goal(
        title=data["title"],
        description=data.get("description", ""),
        target_date=data.get("target_date"),
    )
    return jsonify(result)


@app.route("/life/status", methods=["GET"])
async def life_status():
    """Return life management status."""
    return jsonify(life_management.get_status())


@app.route("/automation/recipe", methods=["POST"])
async def create_automation_recipe():
    """Parse and optionally create an NL automation recipe."""
    data = await request.get_json(silent=True)
    if not data or "description" not in data:
        return jsonify({"error": "Missing 'description' field"}), 400

    description = data["description"]
    if data.get("confirm"):
        # User confirmed: create it
        result = nl_automation.parse_and_create(description)
    else:
        # Just parse and preview
        result = nl_automation.parse(description)
    return jsonify(result)


@app.route("/automation/recipes", methods=["GET"])
async def list_automation_recipes():
    """Return all active NL automation recipes."""
    return jsonify(nl_automation.get_status())


@app.route("/automation/recipe/<int:recipe_id>/toggle", methods=["POST"])
async def toggle_automation_recipe(recipe_id: int):
    """Enable or disable an NL automation recipe."""
    data = await request.get_json(silent=True)
    enabled = bool(data.get("enabled", True)) if data else True
    result = nl_automation.toggle_recipe(recipe_id, enabled)
    return jsonify(result)


@app.route("/continuity/status", methods=["GET"])
async def continuity_status():
    """Return continuity engine status."""
    return jsonify(continuity.get_status())


@app.route("/continuity/export", methods=["POST"])
async def continuity_export():
    """Export cognitive state to a local file."""
    data = await request.get_json(silent=True)
    output_path = data.get("path") if data else None
    try:
        path = continuity.export_state(output_path)
        return jsonify({"status": "exported", "path": path})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/continuity/import", methods=["POST"])
async def continuity_import():
    """Import cognitive state from a local file."""
    data = await request.get_json(silent=True)
    if not data or "path" not in data:
        return jsonify({"error": "Missing 'path' field"}), 400
    result = continuity.import_state(data["path"])
    return jsonify(result)


# ---------------------------------------------------------------------------
# WebSocket Communication Layer (Step 2)
# ---------------------------------------------------------------------------

_ws_clients: set = set()


@app.websocket("/ws")
async def ws_endpoint():
    """
    Bidirectional WebSocket endpoint for real-time communication.

    Message types (client → server):
        {"type": "ping"}                     → keepalive
        {"type": "chat", "message": "..."}   → chat (response streamed back)
        {"type": "typing", "active": true}   → typing indicator

    Message types (server → client):
        {"type": "pong"}                     → keepalive response
        {"type": "orb_state", ...}           → orb animation state
        {"type": "notification", ...}        → new notification
        {"type": "chat_response", ...}       → chat response
        {"type": "typing", ...}              → typing indicator
    """
    client_id = str(uuid.uuid4())[:8]
    _ws_clients.add(client_id)
    print(f"  [WS] Client connected: {client_id} (total: {len(_ws_clients)})")

    async def _send(data: dict):
        """Send JSON to this WebSocket client."""
        try:
            await websocket.send(_json.dumps(data))
        except Exception:
            pass

    # Subscribe to EventBus channels in a background task
    async def _event_forwarder():
        """Forward EventBus events to this WebSocket client."""
        try:
            async for payload in event_bus.subscribe("orb:state"):
                await _send({"type": "orb_state", **payload})
        except asyncio.CancelledError:
            pass

    async def _notification_forwarder():
        """Forward notification events to this WebSocket client."""
        try:
            async for payload in event_bus.subscribe("notification"):
                await _send({"type": "notification", **payload})
        except asyncio.CancelledError:
            pass

    # Start event forwarding tasks
    orb_task = asyncio.create_task(_event_forwarder())
    notif_task = asyncio.create_task(_notification_forwarder())

    try:
        # Send initial state
        await _send({
            "type": "connected",
            "client_id": client_id,
            "session_id": _get_session_id(),
        })

        while True:
            raw = await websocket.receive()
            try:
                msg = _json.loads(raw)
            except (TypeError, _json.JSONDecodeError):
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await _send({"type": "pong"})

            elif msg_type == "typing":
                # Broadcast typing state to EventBus
                await event_bus.emit("chat:typing", {
                    "active": msg.get("active", False),
                    "client_id": client_id,
                })

            elif msg_type == "chat":
                message = (msg.get("message") or "").strip()
                if not message:
                    await _send({"type": "error", "text": "Empty message"})
                    continue

                # Route through conversation engine (includes personality + context)
                try:
                    sid = _get_session_id()
                    result = await conversation_engine.process_text(message, sid)

                    await _send({
                        "type": "chat_response",
                        "response": result["response"],
                        "handler": result["handler"],
                        "emotion": result["emotion"],
                        "role": result.get("role", "assistant"),
                        "session_id": sid,
                        "turn": result.get("turn", 0),
                        "latency_ms": result.get("latency_ms", 0),
                    })
                except Exception as e:
                    await event_bus.emit("orb:state", {"state": "idle"})
                    await _send({"type": "error", "text": str(e)})

            elif msg_type == "voice_start":
                # Start voice conversation session
                sid = _get_session_id()
                await conversation_engine.start_voice_session(sid)
                await _send({"type": "voice_started", "session_id": sid})

            elif msg_type == "voice_stop":
                # Stop voice conversation session
                await conversation_engine.stop_voice_session()
                await _send({"type": "voice_stopped"})

            elif msg_type == "interrupt":
                # Interrupt current speech
                await conversation_engine.interrupt()
                await _send({"type": "interrupted"})

    except asyncio.CancelledError:
        pass
    except Exception:
        pass
    finally:
        orb_task.cancel()
        notif_task.cancel()
        _ws_clients.discard(client_id)
        print(f"  [WS] Client disconnected: {client_id} (remaining: {len(_ws_clients)})")


# ===========================================================================
# Phase 6: Deeply Personalized Cognitive AI Partner Endpoints
# ===========================================================================

@app.route("/personalization/deep", methods=["GET"])
async def personalization_deep():
    """Return deep personalization dimensions."""
    from deep_personalization import deep_personalization
    return jsonify(deep_personalization.get_status())


@app.route("/personalization/override", methods=["POST"])
async def personalization_override():
    """Override a deep personalization dimension."""
    from deep_personalization import deep_personalization
    data = await request.get_json()
    dimension = data.get("dimension", "")
    direction = data.get("direction", "more")
    result = deep_personalization.override_dimension(dimension, direction)
    return jsonify(result)


@app.route("/timing/status", methods=["GET"])
async def timing_status():
    """Return emotional timing gate status."""
    from emotional_timing import emotional_timing
    return jsonify(emotional_timing.get_status())


@app.route("/timing/mute", methods=["POST"])
async def timing_mute():
    """Set mute/available override for emotional timing."""
    from emotional_timing import emotional_timing
    data = await request.get_json()
    mode = data.get("mode", "mute")
    if mode == "mute":
        emotional_timing.set_mute()
    elif mode == "available":
        emotional_timing.set_available()
    else:
        emotional_timing.clear_overrides()
    return jsonify({"status": "ok", "mode": mode})


@app.route("/automation/multi", methods=["GET"])
async def automation_multi_list():
    """List multi-step automation recipes."""
    from multi_step_automation import multi_step_automation
    return jsonify(multi_step_automation.get_status())


@app.route("/automation/multi", methods=["POST"])
async def automation_multi_create():
    """Create a multi-step automation recipe from natural language."""
    from multi_step_automation import multi_step_automation
    data = await request.get_json()
    description = data.get("description", "")
    if data.get("confirm"):
        result = multi_step_automation.parse_and_create(description)
    else:
        result = multi_step_automation.parse(description)
    return jsonify(result)


@app.route("/reflection/llm", methods=["GET"])
async def reflection_llm():
    """Get an LLM-generated reflective insight."""
    from reflective_cognition import reflective_cognition
    insight = reflective_cognition.generate_llm_reflection()
    return jsonify({"insight": insight})


@app.route("/coaching/status", methods=["GET"])
async def coaching_status():
    """Return adaptive coaching status."""
    from life_management import life_management
    status = life_management.get_status()
    status["streak"] = life_management.get_streak_recognition()
    status["rhythm_suggestion"] = life_management.get_rhythm_suggestion()
    return jsonify(status)


@app.route("/continuity/export-encrypted", methods=["POST"])
async def continuity_export_encrypted():
    """Export encrypted cognitive state."""
    from continuity import continuity
    data = await request.get_json()
    passphrase = data.get("passphrase", "")
    if not passphrase:
        return jsonify({"status": "error", "error": "Passphrase required."}), 400
    path = continuity.export_encrypted(passphrase)
    return jsonify({"status": "exported", "path": path})


@app.route("/continuity/import-encrypted", methods=["POST"])
async def continuity_import_encrypted():
    """Import encrypted cognitive state."""
    from continuity import continuity
    data = await request.get_json()
    path = data.get("path", "")
    passphrase = data.get("passphrase", "")
    if not path or not passphrase:
        return jsonify({"status": "error", "error": "Path and passphrase required."}), 400
    result = continuity.import_encrypted(path, passphrase)
    return jsonify(result)


@app.route("/proactive/status", methods=["GET"])
async def proactive_status():
    """Return proactive orchestration status."""
    from proactive_orchestration import proactive_orchestration
    return jsonify(proactive_orchestration.get_status())


@app.route("/proactive/mute", methods=["POST"])
async def proactive_mute():
    """Mute or unmute proactive orchestration."""
    from proactive_orchestration import proactive_orchestration
    data = await request.get_json()
    muted = data.get("muted", True)
    return jsonify(proactive_orchestration.set_muted(muted))


@app.route("/ecosystem/phase6", methods=["GET"])
async def ecosystem_phase6():
    """Unified Phase 6 status overview."""
    from deep_personalization import deep_personalization
    from emotional_timing import emotional_timing
    from multi_step_automation import multi_step_automation
    from proactive_orchestration import proactive_orchestration
    return jsonify({
        "personalization": deep_personalization.get_status(),
        "timing": emotional_timing.get_status(),
        "multi_step_automation": multi_step_automation.get_status(),
        "proactive": proactive_orchestration.get_status(),
    })


# ===================================================================
# Phase 7: Collaborative Cognitive Intelligence Environment
# ===================================================================

# ----- Projects -------------------------------------------------------

@app.route("/projects", methods=["GET"])
async def list_projects():
    """List all active projects."""
    from project_cognition import project_cognition
    return jsonify({"projects": project_cognition.get_active_projects()})


@app.route("/projects", methods=["POST"])
async def create_project():
    """Create a new project."""
    from project_cognition import project_cognition
    data = await request.get_json()
    result = project_cognition.create_project(
        title=data.get("title", "Untitled"),
        description=data.get("description", ""),
        domain=data.get("domain", "general"),
    )
    return jsonify(result), 201


@app.route("/projects/<int:project_id>", methods=["GET"])
async def get_project(project_id):
    """Get a project with milestones."""
    from project_cognition import project_cognition
    project = project_cognition.get_project(project_id)
    if not project:
        return jsonify({"error": "not_found"}), 404
    return jsonify(project)


@app.route("/projects/<int:project_id>/milestone", methods=["POST"])
async def add_milestone(project_id):
    """Add a milestone to a project."""
    from project_cognition import project_cognition
    data = await request.get_json()
    result = project_cognition.add_milestone(
        project_id=project_id,
        title=data.get("title", "Untitled milestone"),
        order_idx=data.get("order_idx", 0),
        notes=data.get("notes", ""),
    )
    return jsonify(result), 201


@app.route("/projects/<int:project_id>/progress", methods=["PUT"])
async def update_project_progress(project_id):
    """Update project progress or status."""
    from project_cognition import project_cognition
    data = await request.get_json()
    result = project_cognition.update_project(
        project_id=project_id,
        progress=data.get("progress"),
        status=data.get("status"),
    )
    return jsonify(result)


# ----- Workspaces -----------------------------------------------------

@app.route("/workspaces", methods=["GET"])
async def list_workspaces():
    """List all active cognitive workspaces."""
    from cognitive_workspace import cognitive_workspace
    return jsonify(cognitive_workspace.get_active_workspaces())


@app.route("/workspaces", methods=["POST"])
async def create_workspace():
    """Create a new cognitive workspace."""
    from cognitive_workspace import cognitive_workspace
    data = await request.get_json()
    result = cognitive_workspace.create_workspace(
        title=data.get("title", "Untitled workspace"),
        description=data.get("description"),
        workspace_type=data.get("workspace_type", "general"),
    )
    return jsonify(result), 201 if result.get("status") == "created" else 200


@app.route("/workspaces/<int:ws_id>", methods=["GET"])
async def get_workspace(ws_id):
    """Get a workspace with nodes and links."""
    from cognitive_workspace import cognitive_workspace
    ws = cognitive_workspace.get_workspace(ws_id)
    if not ws:
        return jsonify({"error": "not_found"}), 404
    return jsonify(ws)


@app.route("/workspaces/<int:ws_id>/node", methods=["POST"])
async def add_workspace_node(ws_id):
    """Add a node to a workspace."""
    from cognitive_workspace import cognitive_workspace
    data = await request.get_json()
    result = cognitive_workspace.add_node(
        workspace_id=ws_id,
        content=data.get("content", ""),
        node_type=data.get("node_type", "note"),
        importance=data.get("importance", 0.5),
        tags=data.get("tags"),
    )
    return jsonify(result), 201 if result.get("status") == "created" else 200


@app.route("/workspaces/<int:ws_id>/link", methods=["POST"])
async def link_workspace_nodes(ws_id):
    """Link two nodes in a workspace."""
    from cognitive_workspace import cognitive_workspace
    data = await request.get_json()
    result = cognitive_workspace.link_nodes(
        source_id=data.get("source_id"),
        target_id=data.get("target_id"),
        relationship=data.get("relationship", "related"),
        weight=data.get("weight", 0.5),
    )
    return jsonify(result), 201 if result.get("status") == "created" else 200


@app.route("/workspaces/<int:ws_id>/summary", methods=["GET"])
async def workspace_summary(ws_id):
    """Get workspace summary."""
    from cognitive_workspace import cognitive_workspace
    summary = cognitive_workspace.summarize_workspace(ws_id)
    return jsonify({"summary": summary})


# ----- Synthesis ------------------------------------------------------

@app.route("/synthesis/analyze", methods=["POST"])
async def synthesize_texts():
    """Synthesize multiple texts."""
    from knowledge_synthesis import knowledge_synthesis
    data = await request.get_json()
    texts = data.get("texts", [])
    context = data.get("context")
    if not texts:
        return jsonify({"error": "Missing 'texts' list"}), 400
    result = knowledge_synthesis.synthesize(texts, context=context)
    return jsonify(result)


@app.route("/synthesis/connections", methods=["POST"])
async def suggest_connections():
    """Suggest semantic connections for text."""
    from knowledge_synthesis import knowledge_synthesis
    data = await request.get_json()
    text = data.get("text", "")
    return jsonify({"connections": knowledge_synthesis.suggest_connections(text)})


# ----- Research -------------------------------------------------------

@app.route("/research/sessions", methods=["GET"])
async def list_research_sessions():
    """List active research sessions."""
    from research_intelligence import research_intelligence
    return jsonify(research_intelligence.get_active_sessions())


@app.route("/research/sessions", methods=["POST"])
async def start_research_session():
    """Start a new research session."""
    from research_intelligence import research_intelligence
    data = await request.get_json()
    result = research_intelligence.start_session(
        topic=data.get("topic", ""),
        domain=data.get("domain", "general"),
    )
    return jsonify(result), 201 if result.get("status") == "created" else 200


@app.route("/research/<int:session_id>/finding", methods=["POST"])
async def add_research_finding(session_id):
    """Add a finding to a research session."""
    from research_intelligence import research_intelligence
    data = await request.get_json()
    result = research_intelligence.add_finding(
        session_id=session_id,
        finding=data.get("finding", ""),
        source=data.get("source"),
    )
    return jsonify(result)


@app.route("/research/<int:session_id>/questions", methods=["GET"])
async def suggest_research_questions(session_id):
    """Get suggested follow-up questions."""
    from research_intelligence import research_intelligence
    questions = research_intelligence.suggest_questions(session_id)
    return jsonify({"questions": questions})


# ----- Knowledge Graph ------------------------------------------------

@app.route("/knowledge/graph", methods=["GET"])
async def knowledge_graph_status():
    """Get knowledge graph overview and top concepts."""
    from knowledge_graph import knowledge_graph
    status = knowledge_graph.get_status()
    status["top_concepts"] = knowledge_graph.get_important_concepts(top_k=10)
    return jsonify(status)


@app.route("/knowledge/graph/<concept>", methods=["GET"])
async def knowledge_graph_concept(concept):
    """Get concept subgraph."""
    from knowledge_graph import knowledge_graph
    depth = request.args.get("depth", 2, type=int)
    depth = min(depth, 3)  # Cap at 3-hop
    return jsonify(knowledge_graph.get_subgraph(concept, depth=depth))


@app.route("/knowledge/clusters", methods=["GET"])
async def knowledge_graph_clusters():
    """Get topic clusters from the knowledge graph."""
    from knowledge_graph import knowledge_graph
    min_size = request.args.get("min_size", 2, type=int)
    return jsonify({"clusters": knowledge_graph.get_clusters(min_size=min_size)})


# ----- Creative -------------------------------------------------------

@app.route("/creative/brainstorm", methods=["POST"])
async def creative_brainstorm():
    """Brainstorming support."""
    from creative_collaboration import creative_collaboration
    data = await request.get_json()
    topic = data.get("topic", "")
    existing_ideas = data.get("existing_ideas")
    return jsonify(creative_collaboration.brainstorm(topic, existing_ideas))


@app.route("/creative/challenge", methods=["POST"])
async def creative_challenge():
    """Challenge assumptions in text."""
    from creative_collaboration import creative_collaboration
    data = await request.get_json()
    text = data.get("text", "")
    return jsonify({"challenges": creative_collaboration.challenge_assumptions(text)})


@app.route("/creative/perspectives", methods=["POST"])
async def creative_perspectives():
    """Expand perspectives on an idea."""
    from creative_collaboration import creative_collaboration
    data = await request.get_json()
    idea = data.get("idea", "")
    dimensions = data.get("dimensions")
    return jsonify(creative_collaboration.expand_perspective(idea, dimensions))


# ----- Collaborative Reflection ----------------------------------------

@app.route("/collaborative/status", methods=["GET"])
async def collaborative_status():
    """Full Phase 7 collaborative intelligence status."""
    from collaborative_reflection import collaborative_reflection
    return jsonify(collaborative_reflection.get_status())


@app.route("/collaborative/reflection", methods=["GET"])
async def collaborative_reflection_view():
    """Get thinking pattern analysis."""
    from collaborative_reflection import collaborative_reflection
    days = request.args.get("days", 30, type=int)
    return jsonify(collaborative_reflection.analyze_thinking_patterns(days=days))


@app.route("/collaborative/reasoning", methods=["GET"])
async def collaborative_reasoning():
    """Get reasoning summary."""
    from collaborative_reflection import collaborative_reflection
    return jsonify({"summary": collaborative_reflection.generate_reasoning_summary()})


@app.route("/collaborative/trajectory", methods=["GET"])
async def learning_trajectory():
    """Get learning trajectory."""
    from collaborative_reflection import collaborative_reflection
    topic = request.args.get("topic")
    return jsonify(collaborative_reflection.get_learning_trajectory(topic))


# ----- Phase 7 Unified Status ----------------------------------------

@app.route("/ecosystem/phase7", methods=["GET"])
async def ecosystem_phase7():
    """Unified Phase 7 collaborative intelligence status."""
    from project_cognition import project_cognition
    from cognitive_workspace import cognitive_workspace
    from knowledge_synthesis import knowledge_synthesis
    from research_intelligence import research_intelligence
    from knowledge_graph import knowledge_graph
    from creative_collaboration import creative_collaboration
    from collaborative_reflection import collaborative_reflection
    return jsonify({
        "projects": project_cognition.get_status(),
        "workspaces": cognitive_workspace.get_status(),
        "synthesis": knowledge_synthesis.get_status(),
        "research": research_intelligence.get_status(),
        "knowledge_graph": knowledge_graph.get_status(),
        "creative": creative_collaboration.get_status(),
        "reflection": collaborative_reflection.get_status(),
        "version": "7.0.0-collaborative",
    })


# ----- Phase 8 Step 1: Human Oversight Framework ---------------------

@app.route("/autonomy/settings", methods=["GET"])
async def autonomy_settings():
    """Get autonomy settings, including tier, paused status, and overrides."""
    actions = ["notify", "open_url", "open_app", "clipboard_store", "focus_mode_on", "focus_mode_off"]
    permissions = {}
    for act in actions:
        permissions[act] = human_oversight.get_action_permission(act)
    
    return jsonify({
        "autonomy_tier": human_oversight.get_autonomy_tier(),
        "is_paused": human_oversight.is_paused(),
        "permissions": permissions,
    })


@app.route("/autonomy/tier", methods=["POST"])
async def autonomy_set_tier():
    """Set the active autonomy tier."""
    data = await request.get_json() or {}
    if "tier" not in data:
        return jsonify({"error": "Missing 'tier' parameter"}), 400
    try:
        tier = int(data["tier"])
        if not (0 <= tier <= 3):
            return jsonify({"error": "Autonomy tier must be between 0 and 3"}), 400
    except ValueError:
        return jsonify({"error": "Autonomy tier must be an integer"}), 400
    
    human_oversight.set_autonomy_tier(tier)
    return jsonify({
        "status": "success",
        "autonomy_tier": tier,
    })


@app.route("/autonomy/pause", methods=["POST"])
async def autonomy_pause():
    """Globally pause all autonomous executions."""
    human_oversight.pause_autonomy()
    return jsonify({
        "status": "success",
        "is_paused": True,
    })


@app.route("/autonomy/resume", methods=["POST"])
async def autonomy_resume():
    """Globally resume execution of autonomous actions."""
    human_oversight.resume_autonomy()
    return jsonify({
        "status": "success",
        "is_paused": False,
    })


@app.route("/autonomy/pending", methods=["GET"])
async def autonomy_pending_actions():
    """Get all pending actions awaiting confirmation."""
    pending = agentic_executor.get_pending()
    return jsonify({
        "pending": pending,
    })


@app.route("/autonomy/approve", methods=["POST"])
async def autonomy_approve_action():
    """Approve a pending action."""
    data = await request.get_json() or {}
    action_id = data.get("action_id")
    if not action_id:
        return jsonify({"error": "Missing 'action_id' parameter"}), 400
    
    result = agentic_executor.approve(action_id)
    return jsonify(result)


@app.route("/autonomy/reject", methods=["POST"])
async def autonomy_reject_action():
    """Reject/cancel a pending action."""
    data = await request.get_json() or {}
    action_id = data.get("action_id")
    if not action_id:
        return jsonify({"error": "Missing 'action_id' parameter"}), 400
    
    result = agentic_executor.cancel(action_id)
    return jsonify(result)


@app.route("/autonomy/audit", methods=["GET"])
async def autonomy_audit_logs():
    """Query persistent execution audit logs."""
    limit = request.args.get("limit", 20, type=int)
    limit = max(1, min(100, limit))
    logs = human_oversight.get_audit_log(limit=limit)
    return jsonify({
        "audit_log": logs,
    })


@app.route("/autonomy/rollback", methods=["POST"])
async def autonomy_rollback_action():
    """Revert an executed action."""
    data = await request.get_json() or {}
    action_id = data.get("action_id")
    if not action_id:
        return jsonify({"error": "Missing 'action_id' parameter"}), 400
    
    result = human_oversight.rollback(action_id)
    return jsonify(result)


@app.route("/autonomy/permission", methods=["POST"])
async def autonomy_set_permission():
    """Set custom permission override boundary for a specific action."""
    data = await request.get_json() or {}
    action = data.get("action")
    status = data.get("status")
    if not action or not status:
        return jsonify({"error": "Missing 'action' or 'status' parameter"}), 400
    
    try:
        human_oversight.set_action_permission(action, status)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
        
    return jsonify({
        "status": "success",
        "action": action,
        "permission": status,
    })


@app.route("/autonomy/agents", methods=["GET"])
async def autonomy_agents_status():
    """Get the status of distributed cognitive agents, sandboxing settings, and arbitration logs."""
    from distributed_agents import distributed_agent_system
    
    agent_info = []
    for agent in distributed_agent_system.agents:
        agent_info.append({
            "name": agent.name,
            "sandboxed": True,
            "class": agent.__class__.__name__,
        })
        
    return jsonify({
        "agents": agent_info,
        "arbitration_logs": distributed_agent_system.get_arbitration_logs(),
    })


@app.route("/autonomy/explain/<action_id>", methods=["GET"])
async def autonomy_explain_action(action_id):
    """Explain an autonomous action."""
    from explainable_autonomy import explainability_engine
    result = explainability_engine.explain_action(action_id)
    return jsonify(result)


@app.route("/autonomy/traces", methods=["GET"])
async def autonomy_decision_traces():
    """Get recent decision traces."""
    from explainable_autonomy import explainability_engine
    limit = request.args.get("limit", 10, type=int)
    result = explainability_engine.get_decision_traces(limit=limit)
    return jsonify({"traces": result})


@app.route("/autonomy/project/forecast", methods=["GET"])
async def autonomy_project_forecast():
    """Forecast milestones for a project."""
    from project_evolution import project_evolution
    project_id = request.args.get("project_id", type=int)
    if project_id is None:
        return jsonify({"error": "Missing 'project_id' query parameter"}), 400
    result = project_evolution.forecast_milestones(project_id)
    return jsonify(result)


@app.route("/autonomy/graph/organize", methods=["POST"])
async def autonomy_graph_organize():
    """Consolidate knowledge graph edges and merge duplicates."""
    from knowledge_organization import knowledge_organizer
    decay_res = knowledge_organizer.decay_edges()
    merge_res = knowledge_organizer.merge_duplicate_concepts()
    return jsonify({
        "status": "success",
        "decay": decay_res,
        "merge": merge_res
    })


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print()
    print("=" * 58)
    print("  AISHA API Server  (Phase 8: Bounded Autonomy Ecosystem)")
    print("=" * 58)
    print(f"  Chat          : http://localhost:5000/chat")
    print(f"  Stream        : http://localhost:5000/chat/stream  (SSE)")
    print(f"  WebSocket     : ws://localhost:5000/ws")
    print(f"  Projects      : http://localhost:5000/projects")
    print(f"  Workspaces    : http://localhost:5000/workspaces")
    print(f"  Synthesis     : http://localhost:5000/synthesis/<topic>")
    print(f"  Research      : http://localhost:5000/research/sessions")
    print(f"  Knowledge     : http://localhost:5000/knowledge-graph/concepts")
    print(f"  Phase 7       : http://localhost:5000/ecosystem/phase7")
    print(f"  Autonomy      : http://localhost:5000/autonomy/settings")
    print(f"  Explain Trace : http://localhost:5000/autonomy/traces")
    print(f"  Health        : http://localhost:5000/health")
    print("=" * 58)
    print()

    app.run(host="0.0.0.0", port=5000, debug=True)

