"""Protocol definitions for All-Might components.

These protocols define the interfaces between modules,
enabling loose coupling and testability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .domain import ProjectManifest


class Scanner(Protocol):
    """Scans a project directory and produces a ProjectManifest."""

    def scan(self, path: Path) -> ProjectManifest: ...


class Initializer(Protocol):
    """Creates knowledge_graph/, enrichment/, and .claude/ skills from a manifest."""

    def initialize(self, manifest: ProjectManifest, smak_path: Path | None = None) -> None: ...


class SkillGenerator(Protocol):
    """Generates SKILL.md files from project state."""

    def generate(self, config_path: Path) -> str: ...
