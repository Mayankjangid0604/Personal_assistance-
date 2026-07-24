"""
Knowledge Synthesis Engine for Aisha AI Assistant (Phase 7 Step 3).

Intelligently synthesizes information: concept summarization, contradiction
detection, pattern surfacing, insight clustering, and semantic linking.

Design principles:
    - AISHA supports understanding, NOT declares authoritative truth
    - Output language: "There seems to be...", "You might notice...",
      "A possible connection is..."
    - Never states conclusions as facts
    - Frames synthesis as observations for the user to evaluate
    - Relies on TF-IDF embeddings from semantic_memory

Usage::

    from knowledge_synthesis import knowledge_synthesis

    result = knowledge_synthesis.synthesize([
        "Machine learning requires large datasets",
        "Small data approaches can work with transfer learning",
    ])
    # → detects potential contradiction, surfaces patterns
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from datetime import datetime
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.db import get_connection


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Sentiment signals for contradiction detection
_POSITIVE_SIGNALS = frozenset({
    "good", "great", "excellent", "beneficial", "important", "effective",
    "useful", "helps", "advantage", "positive", "works", "success",
    "can", "possible", "achievable", "strong", "improve",
})

_NEGATIVE_SIGNALS = frozenset({
    "bad", "poor", "harmful", "useless", "ineffective", "fails",
    "disadvantage", "negative", "doesn't", "cannot", "impossible",
    "won't", "never", "weak", "worse", "decline", "problem",
})

_CONTRADICTION_MARKERS = [
    ("however", "but"),
    ("although", "despite"),
    ("contrary", "opposite"),
    ("whereas", "while"),
    ("instead", "rather"),
]

# Human agency language templates
_OBSERVATION_PREFIXES = [
    "There seems to be a connection between",
    "You might notice that",
    "An interesting pattern appears:",
    "These ideas share some common ground around",
    "A possible theme emerging is",
]

_CONTRADICTION_PREFIXES = [
    "These perspectives seem to differ on",
    "There appears to be a tension between",
    "You might want to explore the difference between",
    "An interesting contrast emerges around",
]


# ---------------------------------------------------------------------------
# Knowledge Synthesis Engine
# ---------------------------------------------------------------------------

class KnowledgeSynthesis:
    """
    Synthesizes information with contradiction detection, pattern surfacing,
    and insight clustering.

    Uses semantic_memory for TF-IDF embeddings and similarity.
    Uses cognitive_workspace for workspace node access.
    """

    def __init__(self) -> None:
        # Lazy imports to avoid circular dependencies
        self._semantic = None
        self._workspace = None
        print("  [KnowledgeSynthesis] Initialized")

    def _get_semantic(self):
        if self._semantic is None:
            from semantic_memory import semantic_memory
            self._semantic = semantic_memory
        return self._semantic

    def _get_workspace(self):
        if self._workspace is None:
            from cognitive_workspace import cognitive_workspace
            self._workspace = cognitive_workspace
        return self._workspace

    # ----- Core Synthesis --------------------------------------------------

    def synthesize(
        self,
        texts: list[str],
        context: str | None = None,
    ) -> dict[str, Any]:
        """
        Multi-text synthesis with contradiction/pattern detection.

        Returns:
            summary       -- concise synthesis
            patterns      -- recurring themes
            contradictions -- detected conflicts
            connections   -- semantic links between texts
        """
        if not texts:
            return {
                "summary": "",
                "patterns": [],
                "contradictions": [],
                "connections": [],
            }

        # Generate summary
        summary = self.generate_summary(texts)

        # Detect patterns
        patterns = self.find_patterns(texts)

        # Detect contradictions (pairwise)
        contradictions = []
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                result = self.detect_contradictions(texts[i], texts[j])
                if result.get("has_contradiction"):
                    contradictions.append(result)

        # Find connections
        connections = []
        sem = self._get_semantic()
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                vec_a = sem.embed(texts[i])
                vec_b = sem.embed(texts[j])
                sim = sem.cosine_similarity(vec_a, vec_b)
                if sim > 0.2:
                    connections.append({
                        "text_a_idx": i,
                        "text_b_idx": j,
                        "similarity": round(sim, 3),
                        "observation": self._describe_connection(texts[i], texts[j], sim),
                    })

        return {
            "summary": summary,
            "patterns": patterns,
            "contradictions": contradictions,
            "connections": connections,
        }

    # ----- Contradiction Detection -----------------------------------------

    def detect_contradictions(
        self, text_a: str, text_b: str,
    ) -> dict[str, Any]:
        """
        Identify potentially conflicting information between two texts.

        Uses semantic similarity + opposing sentiment signals.
        """
        sem = self._get_semantic()
        vec_a = sem.embed(text_a)
        vec_b = sem.embed(text_b)
        similarity = sem.cosine_similarity(vec_a, vec_b)

        # Check for opposing sentiment signals
        sentiment_a = self._get_sentiment_polarity(text_a)
        sentiment_b = self._get_sentiment_polarity(text_b)

        has_opposing_sentiment = (
            (sentiment_a > 0 and sentiment_b < 0) or
            (sentiment_a < 0 and sentiment_b > 0)
        )

        # Check for explicit contradiction markers
        combined = f"{text_a.lower()} {text_b.lower()}"
        has_explicit_markers = any(
            m1 in combined or m2 in combined
            for m1, m2 in _CONTRADICTION_MARKERS
        )

        # Contradiction = topically similar + opposing sentiment or explicit markers
        has_contradiction = (
            similarity > 0.15 and
            (has_opposing_sentiment or has_explicit_markers)
        )

        result: dict[str, Any] = {
            "has_contradiction": has_contradiction,
            "similarity": round(similarity, 3),
            "opposing_sentiment": has_opposing_sentiment,
            "explicit_markers": has_explicit_markers,
        }

        if has_contradiction:
            # Generate invitational observation
            shared_topic = self._extract_shared_topic(text_a, text_b)
            import random
            prefix = random.choice(_CONTRADICTION_PREFIXES)
            result["observation"] = f"{prefix} {shared_topic}." if shared_topic else prefix + "."

        return result

    # ----- Pattern Surfacing -----------------------------------------------

    def find_patterns(self, texts: list[str]) -> list[dict[str, Any]]:
        """
        Surface recurring themes/concepts across multiple texts.

        Returns list of patterns with frequency and example texts.
        """
        if len(texts) < 2:
            return []

        from semantic_memory import tokenize

        # Count term frequency across all texts
        term_counts: Counter = Counter()
        term_sources: dict[str, list[int]] = {}

        for i, text in enumerate(texts):
            tokens = set(tokenize(text))
            for token in tokens:
                term_counts[token] += 1
                term_sources.setdefault(token, []).append(i)

        # Patterns = terms appearing in 2+ texts
        patterns = []
        for term, count in term_counts.most_common(10):
            if count >= 2:
                import random
                prefix = random.choice(_OBSERVATION_PREFIXES)
                patterns.append({
                    "theme": term,
                    "frequency": count,
                    "source_indices": term_sources[term],
                    "observation": f"{prefix} '{term}'.",
                })

        return patterns

    # ----- Insight Clustering ----------------------------------------------

    def cluster_insights(
        self, workspace_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Group related workspace nodes into clusters by semantic similarity.

        Returns list of clusters, each with nodes and a label.
        """
        ws = self._get_workspace()
        sem = self._get_semantic()

        if workspace_id:
            nodes = ws.search_nodes("", workspace_id)
            # search_nodes with empty query won't match; get all nodes instead
            ws_data = ws.get_workspace(workspace_id)
            nodes = ws_data.get("nodes", []) if ws_data else []
        else:
            # Get all nodes from active workspaces
            active = ws.get_active_workspaces()
            nodes = []
            for a in active[:5]:  # Limit to 5 workspaces
                ws_data = ws.get_workspace(a["id"])
                if ws_data:
                    nodes.extend(ws_data.get("nodes", []))

        if len(nodes) < 2:
            return []

        # Embed all nodes
        embeddings = []
        for node in nodes:
            vec = sem.embed(node.get("content", ""))
            embeddings.append(vec)

        # Simple single-linkage clustering: merge pairs with similarity > 0.3
        n = len(nodes)
        cluster_ids = list(range(n))  # each node starts in its own cluster

        for i in range(n):
            for j in range(i + 1, n):
                sim = sem.cosine_similarity(embeddings[i], embeddings[j])
                if sim > 0.3:
                    # Merge clusters
                    old_cluster = cluster_ids[j]
                    new_cluster = cluster_ids[i]
                    for k in range(n):
                        if cluster_ids[k] == old_cluster:
                            cluster_ids[k] = new_cluster

        # Group nodes by cluster
        clusters_map: dict[int, list[dict]] = {}
        for i, node in enumerate(nodes):
            cid = cluster_ids[i]
            clusters_map.setdefault(cid, []).append(node)

        # Filter to clusters with 2+ nodes
        clusters = []
        for cid, cluster_nodes in clusters_map.items():
            if len(cluster_nodes) >= 2:
                # Generate cluster label from most common terms
                from semantic_memory import tokenize
                all_tokens: Counter = Counter()
                for cn in cluster_nodes:
                    all_tokens.update(tokenize(cn.get("content", "")))
                top_terms = [t for t, _ in all_tokens.most_common(3)]
                label = ", ".join(top_terms) if top_terms else "cluster"

                clusters.append({
                    "label": label,
                    "node_count": len(cluster_nodes),
                    "nodes": [
                        {"id": n.get("id"), "content": n.get("content", "")[:80]}
                        for n in cluster_nodes
                    ],
                })

        return clusters

    # ----- Summarization ---------------------------------------------------

    def generate_summary(
        self, texts: list[str], max_length: int = 200,
    ) -> str:
        """
        Generate a concise synthesis summary from multiple texts.

        Extracts key sentences and composes a brief overview.
        """
        if not texts:
            return ""

        if len(texts) == 1:
            text = texts[0]
            return text[:max_length] + ("..." if len(text) > max_length else "")

        # Extract the most information-dense sentence from each text
        key_sentences = []
        for text in texts[:5]:  # Limit to 5 texts
            sentences = re.split(r'(?<=[.!?])\s+', text)
            if sentences:
                # Pick the longest sentence as most informative
                best = max(sentences, key=len)
                key_sentences.append(best.strip())

        # Compose summary
        summary_parts = []
        total_len = 0
        for sent in key_sentences:
            if total_len + len(sent) > max_length:
                break
            summary_parts.append(sent)
            total_len += len(sent)

        return " ".join(summary_parts)

    # ----- Semantic Linking ------------------------------------------------

    def get_semantic_links(self, concept: str) -> list[dict[str, Any]]:
        """Find semantically related concepts across all memory."""
        sem = self._get_semantic()
        related = sem.recall(concept, top_k=5)
        return [
            {
                "text": m["text"][:100],
                "similarity": m.get("similarity", 0),
                "tier": m.get("tier", "working"),
            }
            for m in related
        ]

    def suggest_connections(self, text: str) -> list[dict[str, Any]]:
        """
        Suggest related topics from the knowledge graph.

        Returns suggestions with invitational language.
        """
        suggestions = []

        # Check semantic memory
        sem = self._get_semantic()
        related = sem.recall(text, top_k=3, min_score=0.1)

        for mem in related:
            suggestions.append({
                "source": "memory",
                "text": mem["text"][:80],
                "similarity": mem.get("similarity", 0),
                "suggestion": f"This might connect to something you mentioned earlier: '{mem['text'][:60]}...'",
            })

        # Check knowledge graph nodes
        try:
            with get_connection() as conn:
                from semantic_memory import tokenize
                tokens = tokenize(text)
                for token in tokens[:5]:
                    rows = conn.execute(
                        "SELECT concept, importance FROM knowledge_graph_nodes "
                        "WHERE concept LIKE ? ORDER BY importance DESC LIMIT 2",
                        (f"%{token}%",),
                    ).fetchall()
                    for row in rows:
                        suggestions.append({
                            "source": "knowledge_graph",
                            "concept": row["concept"],
                            "importance": row["importance"],
                            "suggestion": f"You've explored '{row['concept']}' before — there could be a connection here.",
                        })
        except Exception:
            pass

        return suggestions[:5]

    # ----- Diagnostics -----------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return knowledge synthesis status."""
        return {
            "engine": "active",
            "capabilities": [
                "synthesis", "contradiction_detection", "pattern_surfacing",
                "insight_clustering", "semantic_linking",
            ],
        }

    # ----- Internal Helpers ------------------------------------------------

    def _get_sentiment_polarity(self, text: str) -> int:
        """Simple sentiment polarity: +1 positive, -1 negative, 0 neutral."""
        lower = text.lower()
        words = set(re.findall(r"[a-z]+", lower))

        pos = len(words & _POSITIVE_SIGNALS)
        neg = len(words & _NEGATIVE_SIGNALS)

        if pos > neg:
            return 1
        elif neg > pos:
            return -1
        return 0

    def _extract_shared_topic(self, text_a: str, text_b: str) -> str:
        """Find the most common shared topic between two texts."""
        from semantic_memory import tokenize
        tokens_a = set(tokenize(text_a))
        tokens_b = set(tokenize(text_b))
        shared = tokens_a & tokens_b

        if shared:
            return ", ".join(sorted(shared)[:3])
        return "this topic"

    def _describe_connection(
        self, text_a: str, text_b: str, similarity: float,
    ) -> str:
        """Generate an invitational observation about a connection."""
        shared_topic = self._extract_shared_topic(text_a, text_b)

        if similarity > 0.6:
            return f"These ideas are closely related around '{shared_topic}'."
        elif similarity > 0.3:
            return f"There seems to be a thematic connection through '{shared_topic}'."
        else:
            return f"A subtle link might exist through '{shared_topic}'."


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

knowledge_synthesis = KnowledgeSynthesis()
