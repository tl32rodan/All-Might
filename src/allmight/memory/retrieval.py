"""Unified Retriever — composite-scored search across memory layers.

Merges results from episodic and semantic stores via SMAK vector search,
applies the three-dimensional scoring formula from Stanford's Generative
Agents paper extended with Ebbinghaus decay:

    score = w_r × recency + w_i × importance + w_rel × relevance

where:
- ``recency``   = decay score from :mod:`decay`
- ``importance`` = entry's stored importance (0–1)
- ``relevance``  = SMAK semantic similarity (0–1), with keyword fallback

Working memory (Layer 1) is NOT searched — it is already in context.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..bridge.smak_bridge import SmakBridge, SmakBridgeError
from ..core.domain import MemoryConfig, RetrievalResult
from .decay import compute_decay_score
from .episodic import EpisodicMemoryStore
from .semantic import SemanticMemoryStore

log = logging.getLogger(__name__)


class UnifiedRetriever:
    """Searches across episodic + semantic stores with composite scoring.

    When SMAK is available (and the ``episodes`` / ``semantic_facts``
    indices are ingested), retrieval uses **vector similarity** for the
    relevance dimension.  When SMAK is not available, it falls back to
    keyword-overlap scoring transparently.
    """

    def __init__(
        self,
        root: Path,
        config: MemoryConfig | None = None,
    ) -> None:
        self.root = root
        self.config = config or MemoryConfig()
        self.episodic = EpisodicMemoryStore(root)
        self.semantic = SemanticMemoryStore(root)

        # Attempt to initialise search bridge for semantic search.
        # Uses memory's own config (memory/smak_config.yaml), NOT the
        # workspace config.yaml — memory stores are independent.
        self._bridge: SmakBridge | None = None
        memory_smak_config = root / "memory" / "smak_config.yaml"
        if memory_smak_config.exists():
            try:
                self._bridge = SmakBridge(memory_smak_config)
                self._bridge.health()
            except (SmakBridgeError, Exception):
                self._bridge = None

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        namespace: str = "default",
        include_dormant: bool = False,
    ) -> list[RetrievalResult]:
        """Search all memory layers and return scored results.

        Strategy:
        1. If SMAK is available → vector search ``episodes`` and
           ``semantic_facts`` indices for relevance scores.
        2. Always do a local scan as well (catches entries not yet
           ingested into SMAK).
        3. Merge, apply composite scoring, deduplicate, return top-K.
        """
        now = datetime.now(timezone.utc)
        weights = self.config.retrieval_weights
        w_rec = weights.get("recency", 0.3)
        w_imp = weights.get("importance", 0.3)
        w_rel = weights.get("relevance", 0.4)

        candidates: list[RetrievalResult] = []

        # --- SMAK vector search (when available) ---
        smak_hits = self._smak_search(query, top_k=top_k * 3)
        smak_id_scores: dict[str, float] = {}  # id → relevance from SMAK

        for hit in smak_hits:
            hit_id = hit.get("id", "")
            smak_score = hit.get("score", 0.0)
            smak_id_scores[hit_id] = smak_score

            # Build a candidate from the SMAK hit directly
            source_index = hit.get("index", "")
            memory_type = "episode" if source_index == "episodes" else "fact"
            source_label = "episodic" if memory_type == "episode" else "semantic"

            # Try to load the full record for metadata
            recency, importance = self._load_metadata(
                hit_id, memory_type, now
            )

            score = w_rec * recency + w_imp * importance + w_rel * smak_score

            if not include_dormant and recency < 0.10:
                continue

            candidates.append(RetrievalResult(
                memory_id=hit_id,
                content=hit.get("content", hit.get("text", "")),
                memory_type=memory_type,
                score=score,
                recency_score=recency,
                importance_score=importance,
                relevance_score=smak_score,
                source=source_label,
            ))

        # --- Local scan (catch un-ingested entries + fallback) ---
        query_lower = query.lower()
        seen_ids = {c.memory_id for c in candidates}

        # Episodic
        for ep in self.episodic.list_episodes(limit=200):
            if ep.id in seen_ids:
                continue
            relevance = smak_id_scores.get(
                ep.id,
                self._text_relevance(query_lower, ep.summary, ep.topics),
            )
            if relevance <= 0:
                continue

            recency = compute_decay_score(ep.started_at, 1, now=now)
            score = w_rec * recency + w_imp * ep.importance + w_rel * relevance

            if not include_dormant and recency < 0.10:
                continue

            candidates.append(RetrievalResult(
                memory_id=ep.id,
                content=ep.summary,
                memory_type="episode",
                score=score,
                recency_score=recency,
                importance_score=ep.importance,
                relevance_score=relevance,
                source="episodic",
            ))

        # Semantic facts
        for fact in self.semantic.list_facts(limit=200, namespace=namespace):
            if fact.id in seen_ids:
                continue
            relevance = smak_id_scores.get(
                fact.id,
                self._text_relevance(query_lower, fact.content, [fact.category]),
            )
            if relevance <= 0:
                continue

            recency = compute_decay_score(
                fact.last_accessed or fact.updated_at or fact.created_at,
                fact.access_count,
                now=now,
            )
            score = w_rec * recency + w_imp * fact.importance + w_rel * relevance

            if not include_dormant and recency < 0.10:
                continue

            candidates.append(RetrievalResult(
                memory_id=fact.id,
                content=fact.content,
                memory_type="fact",
                score=score,
                recency_score=recency,
                importance_score=fact.importance,
                relevance_score=relevance,
                source="semantic",
            ))

        # --- Deduplicate, sort, truncate ---
        candidates.sort(key=lambda r: r.score, reverse=True)
        seen: set[str] = set()
        unique: list[RetrievalResult] = []
        for c in candidates:
            if c.memory_id not in seen:
                seen.add(c.memory_id)
                unique.append(c)

        # Bump access metadata on returned results
        for r in unique[:top_k]:
            if r.memory_type == "fact":
                self.semantic.record_access(r.memory_id)

        return unique[:top_k]

    # ------------------------------------------------------------------
    # SMAK integration
    # ------------------------------------------------------------------

    def _smak_search(self, query: str, top_k: int = 15) -> list[dict[str, Any]]:
        """Search SMAK memory indices.  Returns [] if SMAK unavailable."""
        if self._bridge is None:
            return []

        results: list[dict[str, Any]] = []

        for index_name in ("episodes", "semantic_facts"):
            try:
                raw = self._bridge.search(query, index=index_name, top_k=top_k)
                # SMAK returns {"results": [{"id", "text"|"content", "score", ...}]}
                for hit in raw.get("results", []):
                    hit["index"] = index_name
                    results.append(hit)
            except SmakBridgeError:
                log.debug("SMAK search failed for index %s", index_name)
                continue

        return results

    def _load_metadata(
        self,
        entry_id: str,
        memory_type: str,
        now: datetime,
    ) -> tuple[float, float]:
        """Load recency and importance from the local store for a SMAK hit.

        Returns ``(recency_score, importance)`` or sensible defaults.
        """
        if memory_type == "episode":
            ep = self.episodic.get_episode(entry_id)
            if ep:
                return (
                    compute_decay_score(ep.started_at, 1, now=now),
                    ep.importance,
                )
        else:
            fact = self.semantic.get_fact(entry_id)
            if fact:
                return (
                    compute_decay_score(
                        fact.last_accessed or fact.updated_at or fact.created_at,
                        fact.access_count,
                        now=now,
                    ),
                    fact.importance,
                )
        # Defaults when local record not found
        return (0.5, 0.5)

    # ------------------------------------------------------------------
    # Keyword fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _text_relevance(
        query_lower: str,
        text: str,
        extra_terms: list[str] | None = None,
    ) -> float:
        """Simple keyword-overlap relevance (0–1).

        Used as fallback when SMAK is not available or when entries
        have not been ingested yet.
        """
        query_words = set(query_lower.split())
        if not query_words:
            return 0.0

        all_text = text.lower()
        if extra_terms:
            all_text += " " + " ".join(t.lower() for t in extra_terms)

        text_words = set(all_text.split())
        overlap = query_words & text_words
        return len(overlap) / len(query_words) if query_words else 0.0
