"""
Cognitive Orchestrator for Aisha AI Assistant (Phase 3 Step 3).

The sole authority for all memory mutations in the Phase 3 cognitive system.
No module writes directly to semantic_memory, episodes, or life_patterns
tables -- they return MemoryIntent dicts that the orchestrator validates,
scores, deduplicates, and commits.

Responsibilities:
    1. Collect MemoryIntents from all cognitive modules
    2. Validate intents (bounds checking, duplicate prevention)
    3. Score and normalize importance
    4. Commit validated intents to SQLite
    5. Run periodic consolidation (decay + promotion + pruning)
    6. Provide unified recall across semantic + episodic memory
    7. Log every mutation for auditing

Architecture::

    User Turn
      |
      v
    CognitiveOrchestrator.process_turn()
      |-- semantic_memory.create_store_intent()
      |-- episodic_memory.extract_intents()
      |-- [future: cognitive agents]
      |
      v
    validate_intents()  -->  commit_intents()
      |
      v
    SQLite (semantic_memory / episodes / life_patterns)

Usage::

    from cognitive_orchestrator import orchestrator

    # After every conversation turn
    enrichment = await orchestrator.process_turn(
        user_input, response, emotion, session_id
    )

    # Periodic consolidation
    await orchestrator.consolidate()

    # Unified recall
    memories = orchestrator.recall("exam stress")
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection

_log = logging.getLogger("aisha.orchestrator")


# ---------------------------------------------------------------------------
# Intent Validation
# ---------------------------------------------------------------------------

_VALID_ACTIONS = {"store", "promote", "boost", "prune"}
_VALID_TABLES = {
    "semantic_memory", "episodes", "life_patterns", "cognitive_plans",
    # Phase 7: Knowledge Graph
    "knowledge_graph_nodes", "knowledge_graph_edges",
}


def _validate_intent(intent: dict) -> bool:
    """Validate a MemoryIntent dict. Returns True if valid."""
    if not isinstance(intent, dict):
        return False
    if intent.get("action") not in _VALID_ACTIONS:
        return False
    if intent.get("table") not in _VALID_TABLES:
        return False
    if "data" not in intent or not isinstance(intent["data"], dict):
        return False
    # Importance must be in [0, 1]
    imp = intent.get("importance", 0.5)
    if not (0.0 <= imp <= 1.0):
        return False
    return True


# ---------------------------------------------------------------------------
# Cognitive Orchestrator
# ---------------------------------------------------------------------------

class CognitiveOrchestrator:
    """
    Central nervous system of the Phase 3 cognitive architecture.

    Sole writer to all memory tables.  Collects MemoryIntents from
    modules, validates, and commits.
    """

    def __init__(self) -> None:
        # Import here to avoid circular imports at module level
        from semantic_memory import semantic_memory
        from episodic_memory import episodic_memory

        self._semantic = semantic_memory
        self._episodic = episodic_memory

        # Phase 7: Knowledge Graph (lazy-loaded to avoid circular imports)
        self._knowledge_graph = None

        # Mutation journal
        self._mutation_count: int = 0
        self._last_consolidation: float = 0.0

        print("  [Orchestrator] Cognitive Orchestrator initialized")

    def _get_knowledge_graph(self):
        """Lazy-load the knowledge graph to avoid circular imports."""
        if self._knowledge_graph is None:
            try:
                from knowledge_graph import knowledge_graph
                self._knowledge_graph = knowledge_graph
            except ImportError:
                pass  # Phase 7 not available
        return self._knowledge_graph

    # ----- Turn Processing -------------------------------------------------

    def process_turn(
        self,
        user_input: str,
        response: str,
        emotion: str = "neutral",
        session_id: str | None = None,
        handler: str = "general",
    ) -> dict[str, Any]:
        """
        Process a conversation turn through the cognitive pipeline.

        1. Collect MemoryIntents from semantic + episodic engines
        2. Validate and commit intents
        3. Return enrichment context for response generation

        Returns dict with:
            semantic_recall  -- related memories
            episodic_context -- life context summary
            intents_committed -- number of intents committed
        """
        t0 = time.time()
        all_intents: list[dict] = []

        # Check if user explicitly asked to remember
        is_remember = self._is_explicit_remember(user_input)

        # 1. Semantic memory: store user input
        if len(user_input.split()) >= 3:  # Skip trivial inputs
            store_intent = self._semantic.create_store_intent(
                text=user_input,
                source="conversation",
                source_id=session_id,
                emotion=emotion,
                is_explicit_remember=is_remember,
            )
            all_intents.append(store_intent)

            # Update vocab with new text
            self._semantic.update_vocab([user_input])

        # 2. Episodic memory: extract life events
        episode_intents = self._episodic.extract_intents(
            user_input, emotion, session_id,
        )
        all_intents.extend(episode_intents)

        # 3. Validate and commit
        committed = self._commit_intents(all_intents)

        # 4. Recall related context (for response enrichment)
        semantic_recall = self._semantic.recall(user_input, top_k=3)
        episodic_context = self._episodic.get_context_summary()

        # 5. Boost accessed memories
        for mem in semantic_recall:
            boost = self._semantic.create_boost_intent(mem["id"], 0.05)
            self._commit_intents([boost])

        # 6. Phase 7: Update knowledge graph from this turn
        kg_updates = 0
        try:
            kg = self._get_knowledge_graph()
            if kg:
                kg_updates = kg.update_from_conversation(
                    user_input, response, emotion,
                )
        except Exception as e:
            _log.debug("Knowledge graph update skipped: %s", e)

        elapsed = time.time() - t0

        return {
            "semantic_recall": semantic_recall,
            "episodic_context": episodic_context,
            "intents_committed": committed,
            "kg_updates": kg_updates,
            "latency_ms": round(elapsed * 1000, 1),
        }

    def _is_explicit_remember(self, text: str) -> bool:
        """Check if the user explicitly asked AISHA to remember something."""
        lower = text.lower()
        signals = [
            "remember this", "remember that", "don't forget",
            "keep this in mind", "note this", "save this",
            "remember my", "store this",
        ]
        return any(s in lower for s in signals)

    # ----- Intent Commitment (sole write path) ----------------------------

    def _commit_intents(self, intents: list[dict]) -> int:
        """Validate and commit a batch of MemoryIntents. Returns count committed."""
        committed = 0

        for intent in intents:
            if not _validate_intent(intent):
                _log.debug("Invalid intent rejected: %s", intent.get("action"))
                continue

            try:
                action = intent["action"]
                table = intent["table"]
                data = intent["data"]

                if action == "store":
                    committed += self._commit_store(table, data)
                elif action == "promote":
                    committed += self._commit_promote(table, data)
                elif action == "boost":
                    committed += self._commit_boost(table, data)
                elif action == "prune":
                    committed += self._commit_prune(table, data)

                self._mutation_count += 1

            except Exception as e:
                _log.error("Intent commit failed (%s/%s): %s",
                           intent.get("action"), intent.get("table"), e)

        return committed

    def _commit_store(self, table: str, data: dict) -> int:
        """INSERT a new row."""
        # Deduplication: check if very similar text exists recently
        if table == "semantic_memory":
            text = data.get("text", "")
            with get_connection() as conn:
                existing = conn.execute(
                    "SELECT id FROM semantic_memory "
                    "WHERE text = ? AND created_at > datetime('now', '-1 hour')",
                    (text,),
                ).fetchone()
                if existing:
                    return 0  # Skip duplicate

        if table == "life_patterns":
            pattern = data.get("pattern", "")
            with get_connection() as conn:
                existing = conn.execute(
                    "SELECT id FROM life_patterns WHERE pattern = ?",
                    (pattern,),
                ).fetchone()
                if existing:
                    # Update frequency instead of inserting duplicate
                    conn.execute(
                        "UPDATE life_patterns SET frequency = frequency + 1, "
                        "last_seen = ? WHERE id = ?",
                        (data.get("last_seen", datetime.now().isoformat()), existing["id"]),
                    )
                    return 1

        # Build INSERT
        columns = list(data.keys())
        values = [data[c] for c in columns]
        placeholders = ", ".join("?" for _ in columns)
        col_str = ", ".join(columns)

        with get_connection() as conn:
            conn.execute(
                f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})",
                values,
            )

        return 1

    def _commit_promote(self, table: str, data: dict) -> int:
        """UPDATE a row using all fields in data (except 'id')."""
        memory_id = data.get("id")
        if not memory_id:
            return 0

        # Build SET clause from all non-id keys
        update_fields = {k: v for k, v in data.items() if k != "id"}
        if not update_fields:
            return 0

        set_clause = ", ".join(f"{k} = ?" for k in update_fields)
        values = list(update_fields.values()) + [memory_id]

        with get_connection() as conn:
            conn.execute(
                f"UPDATE {table} SET {set_clause} WHERE id = ?",
                values,
            )
        return 1

    def _commit_boost(self, table: str, data: dict) -> int:
        """Boost a memory's importance and access count."""
        memory_id = data.get("id")
        boost = data.get("boost", 0.05)
        if not memory_id:
            return 0

        now = datetime.now().isoformat(timespec="seconds")
        with get_connection() as conn:
            conn.execute(
                f"UPDATE {table} SET "
                f"importance = MIN(1.0, importance + ?), "
                f"access_count = access_count + 1, "
                f"last_accessed = ? WHERE id = ?",
                (boost, now, memory_id),
            )
        return 1

    def _commit_prune(self, table: str, data: dict) -> int:
        """Delete a memory entry (hard prune)."""
        memory_id = data.get("id")
        if not memory_id:
            return 0

        with get_connection() as conn:
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (memory_id,))
        return 1

    # ----- Consolidation --------------------------------------------------

    def consolidate(self) -> dict[str, int]:
        """
        Run the decay/promotion/pruning cycle.

        Returns counts of actions taken.
        """
        t0 = time.time()
        intents = self._semantic.get_consolidation_intents()

        promoted = 0
        pruned = 0

        for intent in intents:
            if not _validate_intent(intent):
                continue
            action = intent["action"]
            if action == "promote":
                self._commit_intents([intent])
                promoted += 1
            elif action == "prune":
                self._commit_intents([intent])
                pruned += 1

        # Phase 8: Consolidated Knowledge Structures self-organization
        try:
            from knowledge_organization import knowledge_organizer
            knowledge_organizer.decay_edges()
            knowledge_organizer.merge_duplicate_concepts()
        except Exception as e:
            _log.error("Knowledge graph self-organization failed: %s", e)

        self._last_consolidation = time.time()
        elapsed = time.time() - t0

        if promoted > 0 or pruned > 0:
            _log.info("Consolidation: promoted=%d, pruned=%d, took=%.0fms",
                      promoted, pruned, elapsed * 1000)

        return {"promoted": promoted, "pruned": pruned, "elapsed_ms": round(elapsed * 1000)}

    # ----- Unified Recall -------------------------------------------------

    def recall(
        self,
        query: str,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """
        Unified recall across semantic + episodic memory + knowledge graph.

        Returns dict with:
            semantic    -- semantically related memories
            episodes    -- related life events
            patterns    -- detected patterns
            kg_context  -- knowledge graph neighbors (Phase 7)
        """
        semantic = self._semantic.recall(query, top_k=top_k)
        episodes = self._episodic.get_recent_episodes(limit=top_k)
        patterns = self._episodic.get_patterns(limit=3)

        # Phase 7: Knowledge graph context
        kg_context: list[dict] = []
        try:
            kg = self._get_knowledge_graph()
            if kg:
                concepts = kg.extract_concepts_from_text(query)
                for concept in concepts[:3]:
                    neighbors = kg.get_neighbors(concept)
                    for n in neighbors[:3]:
                        kg_context.append({
                            "concept": n["concept"],
                            "via": concept,
                            "relationship": n["relationship"],
                            "weight": n["weight"],
                        })
        except Exception:
            pass  # Knowledge graph not available or error

        return {
            "semantic": semantic,
            "episodes": episodes,
            "patterns": patterns,
            "kg_context": kg_context,
        }

    # ----- Diagnostics ----------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return orchestrator status and stats."""
        tier_stats = self._semantic.get_tier_stats()
        return {
            "mutation_count": self._mutation_count,
            "total_memories": self._semantic.get_total_count(),
            "tier_stats": tier_stats,
            "vocab_size": len(self._semantic._vocab),
            "last_consolidation": self._last_consolidation,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

orchestrator = CognitiveOrchestrator()
