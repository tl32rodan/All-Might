"""Core domain objects for All-Might.

These dataclasses represent the fundamental concepts that flow through
the entire framework — from Detroit SMAK scanning to One For All generation,
and through the three-layer Agent Memory system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class IndexSpec:
    """A proposed SMAK index specification.

    Maps directly to an entry in config.yaml.
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


# ---------------------------------------------------------------------------
# Agent Memory System — three-layer memory domain objects
# ---------------------------------------------------------------------------


@dataclass
class MemoryEntry:
    """Base unit of agent memory — the atomic record stored in any layer.

    Used as a common envelope for observations, reflections, facts,
    and any other memory content that flows through the system.
    """

    id: str
    content: str
    memory_type: str  # "observation", "reflection", "fact", "correction"
    created_at: str  # ISO 8601
    last_accessed: str  # ISO 8601 — updated on retrieval
    access_count: int = 0
    importance: float = 0.5  # 0.0–1.0, assigned at creation or by LLM
    source_session: str = ""
    tags: list[str] = field(default_factory=list)
    namespace: str = "default"


@dataclass
class Episode:
    """A single agent-session record — Layer 2 (episodic memory).

    Append-only and immutable after creation.  Each session produces
    exactly one Episode summarising what happened.
    """

    id: str
    session_id: str
    started_at: str
    ended_at: str
    summary: str
    key_decisions: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    outcome: str = ""  # "success", "partial", "failure"
    importance: float = 0.5
    consolidated: bool = False


@dataclass
class SemanticFact:
    """A consolidated, versioned knowledge fact — Layer 3 (semantic memory).

    Derived from one or more Episodes through the consolidation process.
    Supports temporal versioning via the *supersedes* chain.
    """

    id: str
    content: str
    category: str  # "user_preference", "convention", "correction",
    # "architecture_decision", "domain_knowledge"
    confidence: float = 1.0
    created_at: str = ""
    updated_at: str = ""
    last_accessed: str = ""
    access_count: int = 0
    importance: float = 0.5
    source_episodes: list[str] = field(default_factory=list)
    supersedes: str | None = None  # ID of the fact this one replaces
    namespace: str = "default"


@dataclass
class MemoryStoreSpec:
    """A memory store definition — lives in ``memory/config.yaml``."""

    name: str  # "journal"
    path: str  # e.g. "./memory/journal"
    store_uri: str  # e.g. "./memory/store/journal"


def _default_stores() -> dict[str, MemoryStoreSpec]:
    return {
        "journal": MemoryStoreSpec(
            name="journal",
            path="./memory/journal",
            store_uri="./memory/store/journal",
        ),
    }


@dataclass
class MemoryConfig:
    """Configuration for the agent memory subsystem (L1/L2/L3)."""

    stores: dict[str, MemoryStoreSpec] = field(default_factory=_default_stores)


# ---------------------------------------------------------------------------
# Merge — combining knowledge bases from separate projects
# ---------------------------------------------------------------------------


@dataclass
class CloneReport:
    """Result of cloning an All-Might project."""

    source: str
    target: str
    timestamp: str
    workspaces_linked: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class MergeReport:
    """Result of merging one All-Might project into another."""

    source: str  # source project path
    timestamp: str  # ISO 8601
    workspaces_added: list[str] = field(default_factory=list)
    workspaces_conflicting: list[str] = field(default_factory=list)
    memory_files_added: list[str] = field(default_factory=list)
    memory_conflicts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    action_needed: list[str] = field(default_factory=list)
