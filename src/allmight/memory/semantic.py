"""Semantic Memory Store — Layer 3 of the agent memory system.

Manages consolidated, versioned knowledge facts in ``memory/semantic/``.
Facts are derived from episodes through the consolidation process and
support temporal versioning via ``supersedes`` chains (Graphiti pattern).

File layout::

    memory/semantic/
    ├── fact_a1b2c3d4e5f6.fact.yaml
    ├── fact_f6e5d4c3b2a1.fact.yaml
    └── ...
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..core.domain import SemanticFact


class SemanticMemoryStore:
    """Creates, reads, updates, and searches semantic facts."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.facts_dir = root / "memory" / "semantic"

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_fact(
        self,
        content: str,
        category: str,
        *,
        confidence: float = 1.0,
        importance: float = 0.5,
        source_episodes: list[str] | None = None,
        supersedes: str | None = None,
        namespace: str = "default",
    ) -> SemanticFact:
        """Create and persist a new semantic fact."""
        now = datetime.now(timezone.utc).isoformat()
        fact_id = f"fact_{uuid.uuid4().hex[:12]}"

        fact = SemanticFact(
            id=fact_id,
            content=content,
            category=category,
            confidence=confidence,
            created_at=now,
            updated_at=now,
            last_accessed=now,
            access_count=0,
            importance=importance,
            source_episodes=source_episodes or [],
            supersedes=supersedes,
            namespace=namespace,
        )

        self._persist(fact)
        return fact

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_fact(self, fact_id: str) -> SemanticFact | None:
        """Load a single fact by ID."""
        path = self.facts_dir / f"{fact_id}.fact.yaml"
        if path.exists():
            return self._load(path)
        # Fallback: scan all (for IDs that don't match filename exactly)
        for p in self.facts_dir.glob("*.fact.yaml"):
            f = self._load(p)
            if f and f.id == fact_id:
                return f
        return None

    def list_facts(
        self,
        *,
        category: str | None = None,
        namespace: str = "default",
        limit: int = 100,
    ) -> list[SemanticFact]:
        """List facts, optionally filtered by category and namespace."""
        facts: list[SemanticFact] = []
        if not self.facts_dir.exists():
            return facts

        for path in sorted(self.facts_dir.glob("*.fact.yaml"), reverse=True):
            fact = self._load(path)
            if fact is None:
                continue
            if namespace != "default" and fact.namespace != namespace:
                continue
            if category and fact.category != category:
                continue
            facts.append(fact)
            if len(facts) >= limit:
                break

        return facts

    def count(self) -> int:
        """Total number of stored facts."""
        if not self.facts_dir.exists():
            return 0
        return sum(1 for _ in self.facts_dir.glob("*.fact.yaml"))

    def avg_confidence(self) -> float:
        """Average confidence across all facts."""
        facts = self.list_facts(limit=10000)
        if not facts:
            return 0.0
        return sum(f.confidence for f in facts) / len(facts)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_fact(
        self,
        fact_id: str,
        *,
        content: str | None = None,
        confidence: float | None = None,
        importance: float | None = None,
        add_source_episodes: list[str] | None = None,
    ) -> SemanticFact | None:
        """Update fields of an existing fact.  Returns updated fact or None."""
        fact = self.get_fact(fact_id)
        if fact is None:
            return None

        now = datetime.now(timezone.utc).isoformat()

        if content is not None:
            fact.content = content
        if confidence is not None:
            fact.confidence = confidence
        if importance is not None:
            fact.importance = importance
        if add_source_episodes:
            fact.source_episodes = list(
                set(fact.source_episodes) | set(add_source_episodes)
            )
        fact.updated_at = now

        self._persist(fact)
        return fact

    def record_access(self, fact_id: str) -> SemanticFact | None:
        """Bump access metadata (for decay resistance).  Returns updated fact."""
        fact = self.get_fact(fact_id)
        if fact is None:
            return None
        fact.last_accessed = datetime.now(timezone.utc).isoformat()
        fact.access_count += 1
        self._persist(fact)
        return fact

    def supersede(
        self,
        old_fact_id: str,
        new_content: str,
        *,
        category: str | None = None,
        source_episodes: list[str] | None = None,
        namespace: str = "default",
    ) -> SemanticFact | None:
        """Create a new fact that supersedes an old one.

        The old fact's confidence is reduced.  Returns the new fact.
        """
        old = self.get_fact(old_fact_id)
        if old is None:
            return None

        # Reduce old fact's confidence
        self.update_fact(old_fact_id, confidence=old.confidence * 0.3)

        # Create successor
        return self.create_fact(
            content=new_content,
            category=category or old.category,
            confidence=1.0,
            importance=old.importance,
            source_episodes=source_episodes,
            supersedes=old_fact_id,
            namespace=namespace,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _persist(self, fact: SemanticFact) -> None:
        """Write fact to YAML file."""
        self.facts_dir.mkdir(parents=True, exist_ok=True)
        path = self.facts_dir / f"{fact.id}.fact.yaml"

        data = {
            "id": fact.id,
            "content": fact.content,
            "category": fact.category,
            "confidence": fact.confidence,
            "created_at": fact.created_at,
            "updated_at": fact.updated_at,
            "last_accessed": fact.last_accessed,
            "access_count": fact.access_count,
            "importance": fact.importance,
            "source_episodes": fact.source_episodes,
            "supersedes": fact.supersedes,
            "namespace": fact.namespace,
        }

        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    @staticmethod
    def _load(path: Path) -> SemanticFact | None:
        """Deserialise a SemanticFact from YAML."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return SemanticFact(
                id=data["id"],
                content=data.get("content", ""),
                category=data.get("category", ""),
                confidence=data.get("confidence", 1.0),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                last_accessed=data.get("last_accessed", ""),
                access_count=data.get("access_count", 0),
                importance=data.get("importance", 0.5),
                source_episodes=data.get("source_episodes", []),
                supersedes=data.get("supersedes"),
                namespace=data.get("namespace", "default"),
            )
        except Exception:
            return None

    def initialize(self) -> None:
        """Create the semantic facts directory."""
        self.facts_dir.mkdir(parents=True, exist_ok=True)
