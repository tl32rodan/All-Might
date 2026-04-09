"""Protocol definitions for All-Might components.

These protocols define the interfaces between modules,
enabling loose coupling and testability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .domain import EnrichmentTask, PowerLevel, ProjectManifest


class Scanner(Protocol):
    """Scans a project directory and produces a ProjectManifest."""

    def scan(self, path: Path) -> ProjectManifest: ...


class Initializer(Protocol):
    """Creates the all-might/ workspace and .claude/ skills from a manifest."""

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
