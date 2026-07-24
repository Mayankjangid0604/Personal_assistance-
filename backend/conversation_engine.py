"""
Conversation Engine for Aisha AI Assistant (Phase 2 Step 3).

The central coordinator for real-time conversational AI:
  - Manages the STT → Brain → TTS pipeline
  - Handles interruption (user speaks while AISHA speaks)
  - Coordinates state across STT, TTS, Brain, Orb
  - Emits unified state events via EventBus

State Machine:
    IDLE → LISTENING → PROCESSING → SPEAKING → IDLE
                ↑                        ↓
                └─────── INTERRUPT ←─────┘

Interruption flow:
    1. User speaks while AISHA is speaking
    2. TTS interrupted → stops immediately
    3. State → LISTENING
    4. STT captures new input
    5. Brain processes new input
    6. TTS speaks new response

EventBus events:
    conversation:state   — state machine transitions
    conversation:turn    — new conversation turn completed

Usage::

    from conversation_engine import conversation_engine

    # Start a voice conversation
    await conversation_engine.start_voice_session()

    # Stop voice conversation
    await conversation_engine.stop_voice_session()

    # Process text input (non-voice)
    result = await conversation_engine.process_text("hello")
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from enum import Enum
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from async_bridge import run_sync, event_bus

_log = logging.getLogger("aisha.conversation")


# ---------------------------------------------------------------------------
# Conversation State
# ---------------------------------------------------------------------------

class ConversationState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"


# ---------------------------------------------------------------------------
# Conversation Engine
# ---------------------------------------------------------------------------

class ConversationEngine:
    """
    Central coordinator for real-time conversational AI.

    Manages the full voice pipeline: STT → Brain → TTS
    with interruption support and state synchronization.
    """

    def __init__(self) -> None:
        self._state = ConversationState.IDLE
        self._voice_session_active = False
        self._voice_task: asyncio.Task | None = None
        self._current_response_task: asyncio.Task | None = None
        self._session_id: str | None = None
        self._last_turn_time: float = 0
        self._turn_count: int = 0

        # Latency tracking
        self._last_stt_latency: float = 0
        self._last_brain_latency: float = 0
        self._last_tts_latency: float = 0

    @property
    def state(self) -> ConversationState:
        return self._state

    @property
    def is_voice_active(self) -> bool:
        return self._voice_session_active

    async def _set_state(self, new_state: ConversationState) -> None:
        """Transition to a new state with EventBus notification."""
        old = self._state
        self._state = new_state
        await event_bus.emit("conversation:state", {
            "state": new_state.value,
            "previous": old.value,
            "session_id": self._session_id,
        })
        await event_bus.emit("orb:state", {
            "state": new_state.value,
        })

    # -- Text-based conversation -------------------------------------------

    async def process_text(
        self, user_input: str, session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Process a text input through the full pipeline.

        This is the primary entry point for chat messages.
        Integrates personality adaptation, context tracking,
        and Phase 3 cognitive enrichment.
        """
        t0 = time.time()
        self._session_id = session_id
        self._turn_count += 1

        await self._set_state(ConversationState.PROCESSING)

        try:
            # Import here to avoid circular imports at module level
            from brain import process_input
            from personality import personality_engine
            from context_tracker import context_tracker

            # Run brain pipeline
            brain_t0 = time.time()
            result = await run_sync(process_input, user_input)
            self._last_brain_latency = time.time() - brain_t0

            # Personality adaptation
            personality_engine.observe_interaction(
                user_input, result.response, result.emotion, result.handler,
            )

            # Adapt response based on learned personality
            adapted_response = personality_engine.adapt_response(
                result.response, result.emotion,
            )

            # Track context
            if session_id:
                context_tracker.track_turn(
                    session_id, user_input, adapted_response,
                    result.emotion, result.handler,
                )

            # ---- Phase 3: Cognitive Enrichment ----------------------------
            cognitive_context = {}
            try:
                from cognitive_orchestrator import orchestrator
                from behavioral_intelligence import behavioral_intelligence

                # Process through cognitive orchestrator
                enrichment = orchestrator.process_turn(
                    user_input, adapted_response,
                    result.emotion, session_id, result.handler,
                )
                cognitive_context.update(enrichment)

                # Gather agent contributions
                try:
                    from cognitive_agents import agent_system
                    agent_results = agent_system.gather(user_input, cognitive_context)
                    cognitive_context.update(agent_results.get("context_additions", {}))

                    # Commit agent memory intents through orchestrator
                    agent_intents = agent_results.get("memory_intents", [])
                    if agent_intents:
                        orchestrator._commit_intents(agent_intents)
                except Exception:
                    pass  # Agent system failure must not crash pipeline

                # Phase 8: Gather distributed sandboxed agent contributions
                try:
                    from distributed_agents import distributed_agent_system
                    dist_results = distributed_agent_system.gather(user_input, cognitive_context)
                    cognitive_context.update(dist_results.get("context_additions", {}))

                    # Track explainability in context
                    cognitive_context["agent_explainability"] = dist_results.get("explainability", {})

                    if dist_results.get("system_prompt"):
                        if "system_prompt" in cognitive_context:
                            cognitive_context["system_prompt"] += "\n" + dist_results["system_prompt"]
                        else:
                            cognitive_context["system_prompt"] = dist_results["system_prompt"]

                    # Commit memory intents
                    dist_intents = dist_results.get("memory_intents", [])
                    if dist_intents:
                        orchestrator._commit_intents(dist_intents)

                    # Dispatch arbitrated actions
                    action_intents = dist_results.get("action_intents", [])
                    for act in action_intents:
                        from agentic_executor import executor as agentic_executor
                        agentic_executor.request(
                            action=act["action"],
                            params=act["params"],
                            reason=f"agent:{act.get('source_agent')} reasoning:{dist_results.get('explainability', {}).get(act.get('source_agent'), {}).get('reasoning', '')}"
                        )

                    # Phase 8: Predictive Workspace Orchestration preloading
                    try:
                        from workspace_orchestration import workspace_orchestrator
                        preload_res = workspace_orchestrator.predict_and_preload()
                        if preload_res.get("status") == "success":
                            cognitive_context["preloaded_workspace"] = preload_res
                    except Exception as e:
                        _log.error("Predictive workspace preloading failed: %s", e)
                except Exception as e:
                    _log.error("Distributed agents execution in conversation turn failed: %s", e)

                # Behavioral enrichment
                adapted_response = behavioral_intelligence.enrich_response(
                    adapted_response, user_input, result.emotion, cognitive_context,
                )

                # Record activity for presence governor
                try:
                    from presence import presence_engine
                    presence_engine.record_activity(result.emotion)
                except Exception:
                    pass

            except ImportError:
                pass  # Phase 3 modules not available -- degrade gracefully

            # ---- Phase 4: AI Operating Layer ------------------------------
            operating_context = {}
            try:
                from desktop_awareness import desktop_awareness
                from workflow_intelligence import workflow_intelligence
                from cross_app_context import cross_app_context
                from productivity_cognition import productivity_engine
                from environmental_reasoning import environment

                # Poll desktop state (feeds workflow + cross-app + productivity)
                desktop_snap = desktop_awareness.poll()

                # Cross-app context
                ctx = cross_app_context.update(desktop_snap)

                # Productivity cognition
                prod_state = productivity_engine.update(desktop_snap)

                # Environmental mode
                env_state = environment.update(desktop_snap)

                operating_context = {
                    "desktop": desktop_snap,
                    "workflow": workflow_intelligence.get_active_workflow(),
                    "workspace_context": ctx.get("context_label"),
                    "environment_mode": env_state.get("mode"),
                    "aisha_tone": env_state.get("aisha_tone", ""),
                    "focus_score": prod_state.get("focus_score", 0.5),
                    "burnout_risk": prod_state.get("burnout_risk", "none"),
                    "productivity_context": productivity_engine.get_context_summary(),
                    "is_deep_work": desktop_snap.get("workflow_overload", False)
                                    or workflow_intelligence.is_deep_work(),
                }

                cognitive_context.update(operating_context)

            except Exception:
                pass  # Phase 4 modules must never crash the pipeline

            # ---- Phase 5: Ecosystem Intelligence --------------------------
            ecosystem_context = {}
            try:
                from routine_intelligence import routine_intelligence
                from behavioral_model import behavioral_model
                from reflective_cognition import reflective_cognition
                from ecosystem_memory import ecosystem_memory
                from evolutionary_personalization import evolutionary_personalization
                from life_management import life_management

                # Routine intelligence: record this tick
                routine_intelligence.record_tick(
                    operating_context.get("desktop", {}),
                    prod_state if "prod_state" in dir() else {},
                    result.emotion,
                )

                # Behavioral model: update EMA
                if prod_state:
                    behavioral_model.observe(prod_state, result.emotion)

                # Ecosystem memory: get continuity bridge
                continuity_summary = ecosystem_memory.get_continuity_summary()

                # Reflective cognition: get insight if due (non-blocking)
                reflection = reflective_cognition.get_ready_insight()

                # Evolutionary personalization: take weekly snapshot if due
                evolutionary_personalization.maybe_snapshot()
                drift_context = evolutionary_personalization.get_drift_context()

                # Life management: get session nudge if appropriate
                life_nudge = life_management.get_session_nudge(result.emotion)

                ecosystem_context = {
                    "continuity_summary": continuity_summary,
                    "reflection": reflection,
                    "drift_context": drift_context,
                    "life_nudge": life_nudge,
                    "routine_context": routine_intelligence.get_context_summary(),
                    "behavioral_trends": behavioral_model.get_trend_summary(),
                }

                cognitive_context.update(ecosystem_context)

            except Exception:
                pass  # Phase 5 modules must never crash the pipeline

            # ---- Phase 6: Deep Personalization & Orchestration -------------
            personalization_context = {}
            try:
                from deep_personalization import deep_personalization
                from emotional_timing import emotional_timing
                from proactive_orchestration import proactive_orchestration

                # Deep personalization: learn from this interaction
                deep_personalization.observe(
                    user_input, adapted_response,
                    result.emotion, result.handler,
                )

                # Emotional timing: update gates
                emotional_timing.update(result.emotion, cognitive_context)

                # Proactive orchestration: check for suggestions
                proactive_suggestion = proactive_orchestration.check_proactive(
                    operating_context,
                )

                # Get personalization prompt modifiers
                prompt_mods = deep_personalization.get_prompt_modifiers()

                personalization_context = {
                    "prompt_modifiers": prompt_mods,
                    "proactive_suggestion": proactive_suggestion,
                    "timing_status": emotional_timing.get_status(),
                }

                cognitive_context.update(personalization_context)

            except Exception:
                pass  # Phase 6 modules must never crash the pipeline

            # ---- Phase 7: Collaborative Intelligence ----------------------
            collaborative_context = {}
            try:
                from project_cognition import project_cognition
                from cognitive_workspace import cognitive_workspace
                from knowledge_graph import knowledge_graph
                from research_intelligence import research_intelligence

                # Project inference from conversation
                inferred_project = project_cognition.infer_project_from_input(
                    user_input,
                )
                project_ctx = project_cognition.get_context_for_conversation(
                    user_input,
                )

                # Workspace node search
                ws_matches = cognitive_workspace.search_nodes(user_input)

                # Knowledge graph concept observation
                kg_result = knowledge_graph.observe_concepts(
                    user_input,
                    operating_context.get("workspace_context", "general"),
                )

                # Research continuity check
                research_ctx = research_intelligence.get_research_continuity(
                    user_input,
                )

                collaborative_context = {
                    "inferred_project": inferred_project,
                    "workspace_matches": len(ws_matches),
                    "kg_observed": kg_result,
                    "research_continuity": research_ctx.get("has_prior_research", False),
                    "project_context": project_ctx,
                }

                cognitive_context.update(collaborative_context)

            except Exception:
                pass  # Phase 7 modules must never crash the pipeline


            # Emit turn event
            total_latency = time.time() - t0
            await event_bus.emit("conversation:turn", {
                "turn": self._turn_count,
                "handler": result.handler,
                "emotion": result.emotion,
                "latency_ms": int(total_latency * 1000),
                "brain_latency_ms": int(self._last_brain_latency * 1000),
            })

            await self._set_state(ConversationState.IDLE)

            return {
                "response": adapted_response,
                "handler": result.handler,
                "emotion": result.emotion,
                "role": result.role,
                "task_detected": result.task_detected,
                "turn": self._turn_count,
                "latency_ms": int(total_latency * 1000),
                "personality_profile": personality_engine.get_profile(),
                "cognitive": {
                    "intents_committed": cognitive_context.get("intents_committed", 0),
                    "semantic_recall_count": len(
                        cognitive_context.get("semantic_recall", [])
                    ),
                },
                "operating": {
                    "environment_mode": operating_context.get("environment_mode"),
                    "workflow": operating_context.get("workspace_context"),
                    "focus_score": operating_context.get("focus_score"),
                    "burnout_risk": operating_context.get("burnout_risk"),
                    "is_deep_work": operating_context.get("is_deep_work", False),
                },
                "ecosystem": {
                    "continuity_summary": ecosystem_context.get("continuity_summary", ""),
                    "reflection": ecosystem_context.get("reflection"),
                    "life_nudge": ecosystem_context.get("life_nudge"),
                    "routine_context": ecosystem_context.get("routine_context", ""),
                    "behavioral_trends": ecosystem_context.get("behavioral_trends", ""),
                },
                "personalization": {
                    "prompt_modifiers": personalization_context.get("prompt_modifiers", ""),
                    "proactive_suggestion": personalization_context.get("proactive_suggestion"),
                },
                "collaborative": {
                    "project_context": collaborative_context.get("project_context", ""),
                    "research_context": collaborative_context.get("research_context", ""),
                    "workspace_connections": len(collaborative_context.get("workspace_connections", [])),
                    "kg_new_concepts": collaborative_context.get("kg_observed", {}).get("new", 0),
                },
            }

        except Exception as e:
            _log.error("process_text error: %s", e)
            await self._set_state(ConversationState.IDLE)
            raise

    # -- Voice-based conversation ------------------------------------------

    async def start_voice_session(self, session_id: str | None = None) -> None:
        """Start a voice conversation session."""
        if self._voice_session_active:
            return

        self._voice_session_active = True
        self._session_id = session_id

        await event_bus.emit("conversation:state", {
            "state": "voice_started",
            "session_id": session_id,
        })

        self._voice_task = asyncio.create_task(self._voice_loop())

    async def stop_voice_session(self) -> None:
        """Stop the voice conversation session."""
        self._voice_session_active = False

        # Interrupt any ongoing speech
        try:
            from tts_engine import tts_engine
            if tts_engine.is_speaking():
                await tts_engine.interrupt()
        except ImportError:
            pass

        # Stop STT
        try:
            from stt_engine import stt_engine
            if stt_engine.is_listening():
                await stt_engine.stop_continuous()
        except ImportError:
            pass

        # Cancel voice task
        if self._voice_task:
            self._voice_task.cancel()
            try:
                await self._voice_task
            except asyncio.CancelledError:
                pass
            self._voice_task = None

        await self._set_state(ConversationState.IDLE)
        await event_bus.emit("conversation:state", {
            "state": "voice_stopped",
        })

    async def _voice_loop(self) -> None:
        """Main voice conversation loop: listen → process → speak → repeat."""
        try:
            from stt_engine import stt_engine
            from tts_engine import tts_engine

            while self._voice_session_active:
                # Listen
                await self._set_state(ConversationState.LISTENING)
                stt_t0 = time.time()
                text = await stt_engine.recognize(timeout=5)
                self._last_stt_latency = time.time() - stt_t0

                if not text:
                    # No speech detected, continue listening
                    await asyncio.sleep(0.1)
                    continue

                # Process
                await self._set_state(ConversationState.PROCESSING)
                result = await self.process_text(text, self._session_id)

                if not self._voice_session_active:
                    break  # Session stopped during processing

                # Speak (with interruption support)
                await self._set_state(ConversationState.SPEAKING)
                tts_t0 = time.time()

                # Use streamed playback for interruption support
                await tts_engine.speak_streamed(result["response"])
                self._last_tts_latency = time.time() - tts_t0

                # Check if interrupted
                if self._state == ConversationState.INTERRUPTED:
                    continue  # Go back to listening

        except asyncio.CancelledError:
            pass
        except Exception as e:
            _log.error("Voice loop error: %s", e)
        finally:
            self._voice_session_active = False
            await self._set_state(ConversationState.IDLE)

    async def interrupt(self) -> None:
        """Interrupt current speech and return to listening."""
        if self._state != ConversationState.SPEAKING:
            return

        await self._set_state(ConversationState.INTERRUPTED)

        try:
            from tts_engine import tts_engine
            await tts_engine.interrupt()
        except ImportError:
            pass

        _log.info("Conversation interrupted by user")

    # -- Diagnostics -------------------------------------------------------

    def get_latency_stats(self) -> dict[str, float]:
        """Return latency measurements for the last turn."""
        return {
            "stt_ms": round(self._last_stt_latency * 1000, 1),
            "brain_ms": round(self._last_brain_latency * 1000, 1),
            "tts_ms": round(self._last_tts_latency * 1000, 1),
            "total_ms": round(
                (self._last_stt_latency + self._last_brain_latency +
                 self._last_tts_latency) * 1000, 1
            ),
        }

    def get_status(self) -> dict[str, Any]:
        """Return current engine status."""
        return {
            "state": self._state.value,
            "voice_active": self._voice_session_active,
            "session_id": self._session_id,
            "turn_count": self._turn_count,
            "latency": self.get_latency_stats(),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

conversation_engine = ConversationEngine()
