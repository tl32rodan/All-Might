"""Unified Retriever — composite-scored search across memory layers.

Merges results from episodic and semantic stores, applies the three-
dimensional scoring formula from Stanford's Generative Agents paper
extended with Ebbinghaus decay:

    score = w_r × recency + w_i × importance + w_rel × relevance

where:
- ``recency``   = decay score from :mod:`decay`
- ``importance`` = entry's stored importance (0–1)
- ``relevance``  = semantic similarity from SMAK vector search (0–1)

Working memory (Layer 1) is NOT searched — it is already in context.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..core.domain import MemoryConfig, RetrievalResult
from .decay import compute_decay_score
from .episodic import EpisodicMemoryStore
from .semantic import SemanticMemoryStore


class UnifiedRetriever:
    """Searches across episodic + semantic stores with composite scoring."""

    def __init__(
        self,
        root: Path,
        config: MemoryConfig | None = None,
    ) -> None:
        self.root = root
        self.config = config or MemoryConfig()
        self.episodic = EpisodicMemoryStore(root)
        self.semantic = SemanticMemoryStore(root)

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        namespace: str = "default",
        include_dormant: bool = False,
    ) -> list[RetrievalResult]:
        """Search all memory layers and return scored results.

        This is a local-only implementation that does keyword matching
        on in-memory stores.  When SMAK is available, the caller can
        enrich ``relevance_score`` with vector similarity.
        """
        candidates: list[RetrievalResult] = []
        now = datetime.now(timezone.utc)
        weights = self.config.retrieval_weights
        w_rec = weights.get("recency", 0.3)
        w_imp = weights.get("importance", 0.3)
        w_rel = weights.get("relevance", 0.4)

        query_lower = query.lower()

        # --- Episodic candidates ---
        episodes = self.episodic.list_episodes(limit=200)
        for ep in episodes:
            relevance = self._text_relevance(query_lower, ep.summary, ep.topics)
            if relevance <= 0:
                continue

            recency = compute_decay_score(ep.started_at, 1, now=now)
            importance = ep.importance

            score = w_rec * recency + w_imp * importance + w_rel * relevance

            if not include_dormant and recency < 0.10:
                continue

            candidates.append(RetrievalResult(
                memory_id=ep.id,
                content=ep.summary,
                memory_type="episode",
                score=score,
                recency_score=recency,
                importance_score=importance,
                relevance_score=relevance,
                source="episodic",
            ))

        # --- Semantic candidates ---
        facts = self.semantic.list_facts(limit=200, namespace=namespace)
        for fact in facts:
            relevance = self._text_relevance(query_lower, fact.content, [fact.category])
            if relevance <= 0:
                continue

            recency = compute_decay_score(
                fact.last_accessed or fact.updated_at or fact.created_at,
                fact.access_count,
                now=now,
            )
            importance = fact.importance

            score = w_rec * recency + w_imp * importance + w_rel * relevance

            if not include_dormant and recency < 0.10:
                continue

            candidates.append(RetrievalResult(
                memory_id=fact.id,
                content=fact.content,
                memory_type="fact",
                score=score,
                recency_score=recency,
                importance_score=importance,
                relevance_score=relevance,
                source="semantic",
            ))

        # Sort by composite score, deduplicate, truncate
        candidates.sort(key=lambda r: r.score, reverse=True)
        seen: set[str] = set()
        unique: list[RetrievalResult] = []
        for c in candidates:
            if c.memory_id not in seen:
                seen.add(c.memory_id)
                unique.append(c)
        return unique[:top_k]

    # ------------------------------------------------------------------
    # SMAK-enhanced retrieval (optional, when bridge is available)
    # ------------------------------------------------------------------

    def retrieve_with_smak(
        self,
        query: str,
        smak_results: list[dict],
        *,
        top_k: int = 5,
        namespace: str = "default",
    ) -> list[RetrievalResult]:
        """Merge SMAK vector search results with local memory search.

        ``smak_results`` should be a list of dicts with at least
        ``{"id": str, "content": str, "score": float, "source": str}``.
        """
        local = self.retrieve(query, top_k=top_k * 2, namespace=namespace)

        now = datetime.now(timezone.utc)
        weights = self.config.retrieval_weights
        w_rec = weights.get("recency", 0.3)
        w_imp = weights.get("importance", 0.3)
        w_rel = weights.get("relevance", 0.4)

        for sr in smak_results:
            local.append(RetrievalResult(
                memory_id=sr.get("id", ""),
                content=sr.get("content", ""),
                memory_type=sr.get("source", "smak"),
                score=w_rel * sr.get("score", 0.0),
                recency_score=0.0,
                importance_score=0.0,
                relevance_score=sr.get("score", 0.0),
                source="smak",
            ))

        local.sort(key=lambda r: r.score, reverse=True)
        return local[:top_k]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _text_relevance(query_lower: str, text: str, extra_terms: list[str] | None = None) -> float:
        """Simple keyword-overlap relevance (0–1).

        This is a stopgap until SMAK vector search is wired in.
        Any word overlap gives a positive signal.
        """
        query_words = set(query_lower.split())
        if not query_words:
            return 0.0

        text_lower = text.lower()
        all_text = text_lower
        if extra_terms:
            all_text += " " + " ".join(t.lower() for t in extra_terms)

        text_words = set(all_text.split())
        overlap = query_words & text_words
        return len(overlap) / len(query_words) if query_words else 0.0
