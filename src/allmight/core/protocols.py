"""Protocol definitions for All-Might components.

These protocols define the interfaces between modules,
enabling loose coupling and testability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .domain import (
    EnrichmentTask,
    Episode,
    MemoryHealth,
    PowerLevel,
    ProjectManifest,
    RetrievalResult,
    SemanticFact,
)


class Scanner(Protocol):
    """Scans a project directory and produces a ProjectManifest."""

    def scan(self, path: Path) -> ProjectManifest: ...


class Initializer(Protocol):
    """Creates config.yaml, enrichment/, panorama/, and .claude/ skills from a manifest."""

    def initialize(self, manifest: ProjectManifest, smak_path: Path | None = None) -> None: ...


class SkillGenerator(Protocol):
    """Generates SKILL.md files from project state."""

    def generate(self, config_path: Path) -> str: ...


class EnrichmentPlanner(Protocol):
    """Produces a prioritized list of enrichment tasks."""

    def plan(self, config_path: Path) -> list[EnrichmentTask]: ...


class PowerTracker(Protocol):
    """Calculates and persists Power Level metrics."""

    def calculate(self, config_path: Path) -> PowerLevel: ...


# ---------------------------------------------------------------------------
# Agent Memory System protocols
# ---------------------------------------------------------------------------


class MemoryWriter(Protocol):
    """Writes memory entries to the appropriate store."""

    def save(self, content: str, memory_type: str, namespace: str = "default", **kwargs: object) -> str: ...


class MemoryRetriever(Protocol):
    """Retrieves memories with composite scoring across layers."""

    def retrieve(self, query: str, top_k: int = 5, namespace: str = "default") -> list[RetrievalResult]: ...


class Consolidator(Protocol):
    """Consolidates episodic memories into semantic facts."""

    def consolidate(self, episodes: list[Episode], namespace: str = "default") -> list[SemanticFact]: ...


class DecayManager(Protocol):
    """Applies Ebbinghaus forgetting curves to memory entries."""

    def apply_decay(self, namespace: str = "default") -> int: ...


class MemoryHealthTracker(Protocol):
    """Calculates memory system health metrics."""

    def calculate(self, config_path: Path) -> MemoryHealth: ...
