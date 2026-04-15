"""Consolidation Engine — episodic-to-semantic memory conversion.

Reads unconsolidated episodes, extracts recurring patterns, and
creates/updates semantic facts.  Supports both synchronous (in-session,
lightweight) and asynchronous (post-session, thorough) consolidation.

Consolidation is the bridge between Layer 2 (episodic) and Layer 3
(semantic).  The engine implements three operations:

1. **Extract** — identify salient observations across episodes
2. **Match** — find existing semantic facts that overlap
3. **Merge/Create/Supersede** — update the semantic store
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..core.domain import Episode, SemanticFact
from .episodic import EpisodicMemoryStore
from .semantic import SemanticMemoryStore


@dataclass
class ConsolidationReport:
    """Summary of a consolidation run."""

    episodes_processed: int = 0
    facts_created: int = 0
    facts_updated: int = 0
    facts_superseded: int = 0
    conflicts_detected: int = 0
    details: list[str] = field(default_factory=list)


class ConsolidationEngine:
    """Converts episodic memories into semantic facts."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.episodic = EpisodicMemoryStore(root)
        self.semantic = SemanticMemoryStore(root)

    # ------------------------------------------------------------------
    # Full consolidation (async / post-session)
    # ------------------------------------------------------------------

    def consolidate(self, namespace: str = "default") -> ConsolidationReport:
        """Process all unconsolidated episodes.

        1. Read unconsolidated episodes
        2. Extract recurring observations and decisions
        3. For each extracted pattern, search existing facts
        4. Create / update / supersede as appropriate
        5. Mark episodes as consolidated
        """
        report = ConsolidationReport()
        episodes = self.episodic.list_episodes(unconsolidated_only=True, limit=100)

        if not episodes:
            report.details.append("No unconsolidated episodes found.")
            return report

        # --- Extract patterns ---
        observations = self._extract_observations(episodes)
        decisions = self._extract_decisions(episodes)
        topics = self._extract_topics(episodes)

        # --- Process observations ---
        for obs_text, source_eps in observations:
            result = self._process_observation(
                obs_text, source_eps, "domain_knowledge", namespace
            )
            self._apply_result(result, report)

        # --- Process decisions ---
        for dec_text, source_eps in decisions:
            result = self._process_observation(
                dec_text, source_eps, "architecture_decision", namespace
            )
            self._apply_result(result, report)

        # --- Create topic-level facts for recurring topics ---
        for topic, count in topics.most_common(10):
            if count >= 2:
                existing = self._find_matching_fact(topic, namespace)
                if existing is None:
                    ep_ids = [
                        ep.id for ep in episodes if topic in ep.topics
                    ]
                    self.semantic.create_fact(
                        content=f"Recurring topic: {topic}",
                        category="domain_knowledge",
                        importance=min(0.3 + count * 0.1, 0.9),
                        source_episodes=ep_ids,
                        namespace=namespace,
                    )
                    report.facts_created += 1

        # --- Mark episodes as consolidated ---
        for ep in episodes:
            self.episodic.mark_consolidated(ep.id)
            report.episodes_processed += 1

        return report

    # ------------------------------------------------------------------
    # Immediate consolidation (sync / in-session)
    # ------------------------------------------------------------------

    def consolidate_immediate(
        self,
        observation: str,
        session_id: str,
        category: str = "domain_knowledge",
        namespace: str = "default",
    ) -> SemanticFact | None:
        """Lightweight single-observation consolidation.

        Called during a session when something important is observed
        (e.g., a user correction).  Skips the full episode scan.
        """
        existing = self._find_matching_fact(observation, namespace)

        if existing is not None:
            # Reinforce existing fact
            self.semantic.update_fact(
                existing.id,
                confidence=min(existing.confidence + 0.1, 1.0),
                add_source_episodes=[session_id],
            )
            return existing

        # Create new fact
        return self.semantic.create_fact(
            content=observation,
            category=category,
            confidence=0.8,
            importance=0.6,
            source_episodes=[session_id],
            namespace=namespace,
        )

    # ------------------------------------------------------------------
    # Internal — extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_observations(
        episodes: list[Episode],
    ) -> list[tuple[str, list[str]]]:
        """Extract observations with their source episode IDs.

        Groups identical or near-identical observations.
        """
        obs_map: dict[str, list[str]] = {}
        for ep in episodes:
            for obs in ep.observations:
                key = obs.strip().lower()
                if key not in obs_map:
                    obs_map[key] = []
                obs_map[key].append(ep.id)

        return [
            (text, ep_ids)
            for text, ep_ids in obs_map.items()
            if text  # skip empties
        ]

    @staticmethod
    def _extract_decisions(
        episodes: list[Episode],
    ) -> list[tuple[str, list[str]]]:
        """Extract decisions with their source episode IDs."""
        dec_map: dict[str, list[str]] = {}
        for ep in episodes:
            for dec in ep.key_decisions:
                key = dec.strip().lower()
                if key not in dec_map:
                    dec_map[key] = []
                dec_map[key].append(ep.id)

        return [
            (text, ep_ids)
            for text, ep_ids in dec_map.items()
            if text
        ]

    @staticmethod
    def _extract_topics(episodes: list[Episode]) -> Counter:
        """Count topic frequencies across episodes."""
        counter: Counter = Counter()
        for ep in episodes:
            for topic in ep.topics:
                counter[topic.strip().lower()] += 1
        return counter

    # ------------------------------------------------------------------
    # Internal — matching and merging
    # ------------------------------------------------------------------

    def _find_matching_fact(
        self, text: str, namespace: str
    ) -> SemanticFact | None:
        """Find an existing fact that substantially overlaps with text.

        Uses simple word-overlap heuristic.  When SMAK is available,
        this should be replaced with vector similarity search.
        """
        text_words = set(text.lower().split())
        if not text_words:
            return None

        best_fact: SemanticFact | None = None
        best_score = 0.0

        for fact in self.semantic.list_facts(namespace=namespace, limit=200):
            fact_words = set(fact.content.lower().split())
            if not fact_words:
                continue
            overlap = len(text_words & fact_words)
            union = len(text_words | fact_words)
            jaccard = overlap / union if union > 0 else 0.0
            if jaccard > best_score and jaccard >= 0.5:
                best_score = jaccard
                best_fact = fact

        return best_fact

    def _process_observation(
        self,
        text: str,
        source_episodes: list[str],
        category: str,
        namespace: str,
    ) -> _ConsolidationAction:
        """Decide what to do with an extracted observation."""
        existing = self._find_matching_fact(text, namespace)

        if existing is None:
            return _ConsolidationAction(
                action="create",
                text=text,
                category=category,
                source_episodes=source_episodes,
                namespace=namespace,
            )

        # Check for contradiction (very simple heuristic: negation words)
        if self._looks_contradictory(text, existing.content):
            return _ConsolidationAction(
                action="supersede",
                text=text,
                category=category,
                source_episodes=source_episodes,
                namespace=namespace,
                existing_fact_id=existing.id,
            )

        # Reinforce
        return _ConsolidationAction(
            action="update",
            text=text,
            category=category,
            source_episodes=source_episodes,
            namespace=namespace,
            existing_fact_id=existing.id,
        )

    @staticmethod
    def _looks_contradictory(new_text: str, existing_text: str) -> bool:
        """Naive contradiction detection.

        Checks for negation patterns.  A proper implementation would
        use an LLM or NLI model.
        """
        negation_markers = {"not", "no longer", "incorrect", "wrong", "actually", "instead"}
        new_lower = new_text.lower()
        return any(marker in new_lower for marker in negation_markers)

    def _apply_result(
        self, action: _ConsolidationAction, report: ConsolidationReport
    ) -> None:
        """Execute a consolidation action and update the report."""
        if action.action == "create":
            self.semantic.create_fact(
                content=action.text,
                category=action.category,
                importance=0.5,
                source_episodes=action.source_episodes,
                namespace=action.namespace,
            )
            report.facts_created += 1

        elif action.action == "update" and action.existing_fact_id:
            fact = self.semantic.get_fact(action.existing_fact_id)
            if fact:
                self.semantic.update_fact(
                    action.existing_fact_id,
                    confidence=min(fact.confidence + 0.1, 1.0),
                    add_source_episodes=action.source_episodes,
                )
                report.facts_updated += 1

        elif action.action == "supersede" and action.existing_fact_id:
            self.semantic.supersede(
                action.existing_fact_id,
                new_content=action.text,
                category=action.category,
                source_episodes=action.source_episodes,
                namespace=action.namespace,
            )
            report.facts_superseded += 1
            report.conflicts_detected += 1


@dataclass
class _ConsolidationAction:
    """Internal: describes what to do with an extracted observation."""

    action: str  # "create" | "update" | "supersede"
    text: str
    category: str
    source_episodes: list[str]
    namespace: str = "default"
    existing_fact_id: str | None = None
