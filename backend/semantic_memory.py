"""
Semantic Memory System for Aisha AI Assistant (Phase 3 Step 1).

Provides meaning-based memory retrieval using TF-IDF embeddings stored
as JSON text in SQLite.  Implements a three-tier memory model:

    Working  (~20 entries)  -- current conversation context, fast decay
    Short-term (~200)       -- recent sessions/topics, weekly decay
    Long-term (unlimited)   -- consolidated knowledge, near-permanent

Key design decisions:

* **TF-IDF + numpy** -- lightweight, no PyTorch needed, works on Python 3.14.
* **JSON vectors** -- stored as TEXT, not BLOB.  Human-readable, grep-able,
  portable.  Negligible performance difference at AISHA's scale (<10k vectors).
* **Importance scoring** -- multi-factor: emotion weight, novelty, emphasis,
  conversational depth, reference boosts.
* **Exponential decay** -- each tier has a distinct decay rate lambda.
* **Orchestrator-only mutation** -- this module returns ``MemoryIntent`` dicts
  for writes.  The CognitiveOrchestrator validates and commits them.
  Vocabulary management is internal bookkeeping (not user memory).

Usage::

    from semantic_memory import semantic_memory

    # Generate a store intent (orchestrator commits it)
    intent = semantic_memory.create_store_intent(
        "I have an exam tomorrow", source="conversation", emotion="stressed"
    )

    # Recall related memories (read-only, direct)
    results = semantic_memory.recall("upcoming exams", top_k=5)

    # Get consolidation intents (orchestrator commits them)
    intents = semantic_memory.get_consolidation_intents()
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_VOCAB_SIZE = 256          # Top N terms by document frequency
MIN_TERM_LENGTH = 3           # Ignore tokens shorter than this
WORKING_CAPACITY = 20         # Max working memory entries
SHORT_TERM_CAPACITY = 200     # Max short-term entries

# Decay rates (lambda) per tier
DECAY_RATES = {
    "working":    1.0,        # half-life ~17 hours
    "short_term": 0.05,       # half-life ~14 days
    "long_term":  0.001,      # half-life ~2 years
}

# Tier retrieval weights
TIER_WEIGHTS = {
    "working":    1.5,
    "short_term": 1.0,
    "long_term":  0.8,
}

# Emotion → importance weight (0.0 – 0.3)
EMOTION_WEIGHTS = {
    "neutral":  0.0,
    "happy":    0.15,
    "excited":  0.20,
    "sad":      0.25,
    "stressed": 0.20,
    "angry":    0.20,
    "curious":  0.10,
}

# Stopwords -- filtered during tokenization
_STOPWORDS = frozenset({
    "i", "me", "my", "we", "you", "your", "it", "its", "the", "a", "an",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "can", "may",
    "to", "of", "in", "for", "on", "at", "by", "with", "from", "and", "or",
    "but", "not", "no", "so", "if", "as", "up", "out", "about", "into",
    "that", "this", "what", "which", "who", "how", "when", "where", "why",
    "all", "each", "every", "some", "any", "just", "also", "than", "then",
    "very", "too", "much", "more", "most", "only", "own", "other",
    "hey", "hi", "hello", "thanks", "thank", "please", "ok", "okay",
    "yes", "yeah", "yep", "nah", "nope", "gonna", "wanna", "gotta",
})


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    """Split text into content-bearing lowercase tokens."""
    words = re.findall(r"[a-z]{3,}", text.lower())
    return [w for w in words if w not in _STOPWORDS]


# ---------------------------------------------------------------------------
# Importance Scoring
# ---------------------------------------------------------------------------

def compute_importance(
    text: str,
    emotion: str = "neutral",
    is_explicit_remember: bool = False,
    turn_depth: int = 1,
) -> float:
    """
    Compute importance score for a memory entry (0.0 – 1.0).

    Factors:
        base_score     = 0.3
        emotion_weight = 0.0 – 0.3  (strong emotions → higher)
        emphasis_bonus = 0.3         (user said "remember this")
        depth_bonus    = 0.0 – 0.1   (deeper conversations → higher)
        length_bonus   = 0.0 – 0.1   (longer messages → higher)
    """
    base = 0.3
    emotion_w = EMOTION_WEIGHTS.get(emotion, 0.05)
    emphasis = 0.3 if is_explicit_remember else 0.0
    depth = min(0.1, turn_depth * 0.02)
    length = min(0.1, len(text.split()) * 0.005)

    return min(1.0, base + emotion_w + emphasis + depth + length)


def effective_importance(
    importance: float,
    created_at: str,
    tier: str,
    now: datetime | None = None,
) -> float:
    """
    Apply exponential decay to an importance score.

    effective = importance * e^(-lambda * days_since_creation)
    """
    now = now or datetime.now()
    try:
        created = datetime.fromisoformat(created_at)
    except (ValueError, TypeError):
        return importance

    days = max(0, (now - created).total_seconds() / 86400)
    lam = DECAY_RATES.get(tier, 0.05)
    decay = math.exp(-lam * days)
    return importance * decay


# ---------------------------------------------------------------------------
# Semantic Memory Engine
# ---------------------------------------------------------------------------

class SemanticMemory:
    """
    TF-IDF based semantic memory with tiered storage and importance scoring.

    **Read operations** query SQLite directly.
    **Write operations** return MemoryIntent dicts for the CognitiveOrchestrator.
    Vocabulary management is internal (not user-facing memory).
    """

    def __init__(self) -> None:
        self._vocab: dict[str, int] = {}     # term → index
        self._idf: dict[str, float] = {}     # term → IDF value
        self._vocab_list: list[str] = []     # index → term
        self._total_docs: int = 0
        self._load_vocab()

    # ----- Vocabulary Management (internal bookkeeping) --------------------

    def _load_vocab(self) -> None:
        """Load vocabulary from SQLite."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT term, doc_freq, idf FROM semantic_vocab "
                    "ORDER BY doc_freq DESC LIMIT ?",
                    (MAX_VOCAB_SIZE,),
                ).fetchall()
                self._total_docs = conn.execute(
                    "SELECT COUNT(*) FROM semantic_memory",
                ).fetchone()[0]

            self._vocab = {}
            self._idf = {}
            self._vocab_list = []

            for i, row in enumerate(rows):
                term = row["term"]
                self._vocab[term] = i
                self._idf[term] = row["idf"] if row["idf"] else 1.0
                self._vocab_list.append(term)

            print(f"  [SemanticMemory] Loaded vocab: {len(self._vocab)} terms, "
                  f"{self._total_docs} memories")
        except Exception as e:
            print(f"  [SemanticMemory] Vocab load failed ({e}), starting fresh")

    def update_vocab(self, texts: list[str]) -> None:
        """
        Update the TF-IDF vocabulary from a batch of texts.

        This is internal bookkeeping — writes to semantic_vocab only,
        not to user memory tables.
        """
        # Count document frequency for each term
        doc_freq: Counter = Counter()
        for text in texts:
            unique_terms = set(tokenize(text))
            doc_freq.update(unique_terms)

        total_docs = max(1, self._total_docs + len(texts))

        with get_connection() as conn:
            for term, freq in doc_freq.items():
                idf = math.log(total_docs / (1 + freq))
                conn.execute(
                    "INSERT INTO semantic_vocab (term, doc_freq, idf) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT(term) DO UPDATE SET "
                    "doc_freq = doc_freq + excluded.doc_freq, "
                    "idf = ?",
                    (term, freq, idf, idf),
                )

        self._total_docs = total_docs
        self._load_vocab()

    # ----- Embedding -------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """
        Convert text to a TF-IDF vector (list of floats).

        Dimension = len(vocab).  Returns zero vector if vocab is empty.
        """
        if not self._vocab:
            return []

        tokens = tokenize(text)
        if not tokens:
            return [0.0] * len(self._vocab)

        # Term frequency
        tf = Counter(tokens)
        max_tf = max(tf.values()) if tf else 1

        # Build vector
        vec = [0.0] * len(self._vocab)
        for term, count in tf.items():
            if term in self._vocab:
                idx = self._vocab[term]
                # Normalized TF × IDF
                normalized_tf = count / max_tf
                idf = self._idf.get(term, 1.0)
                vec[idx] = normalized_tf * idf

        # L2 normalize
        arr = np.array(vec, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm

        return arr.tolist()

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0

        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)

        dot = float(np.dot(va, vb))
        na = float(np.linalg.norm(va))
        nb = float(np.linalg.norm(vb))

        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    # ----- MemoryIntent Creators (no direct writes) -----------------------

    def create_store_intent(
        self,
        text: str,
        source: str = "conversation",
        source_id: str | None = None,
        emotion: str = "neutral",
        is_explicit_remember: bool = False,
        turn_depth: int = 1,
    ) -> dict[str, Any]:
        """
        Create a MemoryIntent for storing a new semantic memory.

        Does NOT write to the database.  Returns an intent dict
        for the CognitiveOrchestrator to validate and commit.
        """
        importance = compute_importance(text, emotion, is_explicit_remember, turn_depth)
        embedding = self.embed(text)
        now = datetime.now().isoformat(timespec="seconds")

        return {
            "action": "store",
            "table": "semantic_memory",
            "source_module": "semantic_memory",
            "data": {
                "tier": "working",
                "source": source,
                "source_id": source_id,
                "text": text,
                "embedding": json.dumps(embedding),
                "emotion": emotion,
                "importance": round(importance, 4),
                "access_count": 0,
                "created_at": now,
                "last_accessed": now,
            },
            "importance": round(importance, 4),
        }

    def create_promote_intent(
        self, memory_id: int, new_tier: str,
    ) -> dict[str, Any]:
        """Create a MemoryIntent to promote a memory to a higher tier."""
        return {
            "action": "promote",
            "table": "semantic_memory",
            "source_module": "semantic_memory",
            "data": {"id": memory_id, "tier": new_tier},
            "importance": 0.0,
        }

    def create_boost_intent(
        self, memory_id: int, boost: float = 0.1,
    ) -> dict[str, Any]:
        """Create a MemoryIntent to boost a memory's importance (re-reference)."""
        return {
            "action": "boost",
            "table": "semantic_memory",
            "source_module": "semantic_memory",
            "data": {"id": memory_id, "boost": boost},
            "importance": boost,
        }

    def create_prune_intent(self, memory_id: int) -> dict[str, Any]:
        """Create a MemoryIntent to mark a memory for pruning."""
        return {
            "action": "prune",
            "table": "semantic_memory",
            "source_module": "semantic_memory",
            "data": {"id": memory_id},
            "importance": 0.0,
        }

    # ----- Retrieval (read-only, queries SQLite directly) ------------------

    def recall(
        self,
        query: str,
        top_k: int = 5,
        tiers: list[str] | None = None,
        min_score: float = 0.05,
    ) -> list[dict[str, Any]]:
        """
        Find semantically related memories across all tiers.

        Returns list of dicts sorted by final_score descending:
            {id, text, emotion, tier, importance, effective_importance,
             similarity, final_score, created_at}
        """
        query_vec = self.embed(query)
        if not query_vec or all(v == 0.0 for v in query_vec):
            return []

        allowed_tiers = tiers or ["working", "short_term", "long_term"]

        with get_connection() as conn:
            placeholders = ",".join("?" for _ in allowed_tiers)
            rows = conn.execute(
                f"SELECT id, tier, text, embedding, emotion, importance, "
                f"access_count, created_at, last_accessed "
                f"FROM semantic_memory WHERE tier IN ({placeholders}) "
                f"AND embedding IS NOT NULL",
                allowed_tiers,
            ).fetchall()

        now = datetime.now()
        scored = []

        for row in rows:
            try:
                mem_vec = json.loads(row["embedding"])
            except (json.JSONDecodeError, TypeError):
                continue

            similarity = self.cosine_similarity(query_vec, mem_vec)
            if similarity < 0.01:
                continue

            eff_imp = effective_importance(
                row["importance"], row["created_at"], row["tier"], now,
            )
            tier_w = TIER_WEIGHTS.get(row["tier"], 1.0)
            final_score = similarity * eff_imp * tier_w

            if final_score < min_score:
                continue

            scored.append({
                "id": row["id"],
                "text": row["text"],
                "emotion": row["emotion"],
                "tier": row["tier"],
                "importance": row["importance"],
                "effective_importance": round(eff_imp, 4),
                "similarity": round(similarity, 4),
                "final_score": round(final_score, 4),
                "access_count": row["access_count"],
                "created_at": row["created_at"],
            })

        scored.sort(key=lambda x: x["final_score"], reverse=True)
        return scored[:top_k]

    def recall_by_emotion(
        self, emotion: str, top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve memories associated with a specific emotion."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, tier, text, emotion, importance, created_at "
                "FROM semantic_memory WHERE emotion = ? "
                "ORDER BY importance DESC LIMIT ?",
                (emotion, top_k),
            ).fetchall()

        now = datetime.now()
        return [
            {
                "id": row["id"],
                "text": row["text"],
                "emotion": row["emotion"],
                "tier": row["tier"],
                "importance": row["importance"],
                "effective_importance": round(
                    effective_importance(
                        row["importance"], row["created_at"], row["tier"], now,
                    ), 4
                ),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    # ----- Consolidation (returns intents, doesn't write) -----------------

    def get_consolidation_intents(self) -> list[dict[str, Any]]:
        """
        Generate MemoryIntents for the decay/promote/prune cycle.

        Rules:
        1. Working entries aged >1h with importance >0.4 → promote to short_term
        2. Short-term entries with access_count >=2 OR importance >0.7
           → promote to long_term
        3. Any entry with effective_importance <0.05 → prune
        """
        intents = []
        now = datetime.now()

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, tier, importance, access_count, created_at "
                "FROM semantic_memory",
            ).fetchall()

        for row in rows:
            eff = effective_importance(
                row["importance"], row["created_at"], row["tier"], now,
            )
            age_hours = (now - datetime.fromisoformat(row["created_at"])
                         ).total_seconds() / 3600

            # Pruning (any tier)
            if eff < 0.05:
                intents.append(self.create_prune_intent(row["id"]))
                continue

            # Working → short_term promotion
            if row["tier"] == "working" and age_hours > 1.0 and row["importance"] > 0.4:
                intents.append(self.create_promote_intent(row["id"], "short_term"))

            # Short-term → long_term promotion
            elif row["tier"] == "short_term":
                if row["access_count"] >= 2 or row["importance"] > 0.7:
                    intents.append(self.create_promote_intent(row["id"], "long_term"))

        return intents

    def get_tier_stats(self) -> dict[str, int]:
        """Return count of memories per tier."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT tier, COUNT(*) as cnt FROM semantic_memory GROUP BY tier",
            ).fetchall()
        return {row["tier"]: row["cnt"] for row in rows}

    def get_total_count(self) -> int:
        """Return total number of semantic memories."""
        with get_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM semantic_memory",
            ).fetchone()[0]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

semantic_memory = SemanticMemory()
