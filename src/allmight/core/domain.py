"""Core domain objects for All-Might.

These dataclasses represent the fundamental concepts that flow through
the entire framework — from Detroit SMAK scanning to One For All generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class IndexSpec:
    """A proposed SMAK index specification.

    Maps directly to an entry in workspace_config.yaml.
    """

    name: str
    description: str
    paths: list[str]
    uri: str | None = None
    path_env: str | None = None


@dataclass
class ProjectManifest:
    """The result of scanning a project — everything Detroit SMAK discovers.

    This is the input to the Initializer, which uses it to generate
    all workspace artifacts.
    """

    name: str
    root_path: Path
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    directory_map: dict[str, str] = field(default_factory=dict)
    indices: list[IndexSpec] = field(default_factory=list)
    has_path_env: bool = False
    path_env_name: str | None = None


@dataclass
class SymbolInfo:
    """A symbol extracted from a sidecar YAML file."""

    name: str
    file_path: str
    index: str
    has_intent: bool = False
    has_relations: bool = False
    intent: str = ""
    relation_count: int = 0


@dataclass
class PowerLevel:
    """Knowledge graph maturity metrics — the project's 戦力値.

    Tracks how much of the codebase has been enriched with
    human-curated intent and relations.
    """

    total_symbols: int = 0
    enriched_symbols: int = 0
    coverage_pct: float = 0.0
    by_index: dict[str, float] = field(default_factory=dict)
    total_files: int = 0
    files_with_sidecars: int = 0
    total_relations: int = 0
    timestamp: str = ""


@dataclass
class EnrichmentTask:
    """A single enrichment work item — a symbol that needs attention."""

    file_path: str
    symbol: str
    index: str
    reason: str  # e.g. "missing_intent", "no_relations", "stale"
    priority: float = 0.0


@dataclass
class GraphNode:
    """A node in the knowledge graph (for Panorama export)."""

    uid: str
    name: str
    file_path: str
    index: str
    has_intent: bool = False
    intent: str = ""


@dataclass
class GraphEdge:
    """An edge in the knowledge graph (a relation between symbols)."""

    source_uid: str
    target_uid: str
    source_index: str
