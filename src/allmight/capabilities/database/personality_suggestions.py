"""Canonical personality suggestion catalog.

Seeded by ``allmight init`` into
``.allmight/suggestions/personalities/<name>.yaml`` so the
``/onboard`` skill picks from a deterministic list rather than
inventing names from scratch. Users can edit the seeded files or
drop new ones in; ``/onboard`` reads the directory at runtime.

**Why ``.allmight/suggestions/`` and not ``.allmight/templates/``:**
``.allmight/templates/`` is the ``/sync`` re-init staging area —
files there are transient and may be removed once sync resolves.
Suggestions need a stable home that ``/sync`` does not touch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ...core.markers import ALLMIGHT_MARKER_YAML
from ...core.safe_write import write_guarded


@dataclass(frozen=True)
class PersonalitySuggestion:
    """One canonical suggestion the ``/onboard`` skill can offer."""

    name: str
    """Slug used as the personality name (``allmight add <name>``)."""

    capabilities: tuple[str, ...]
    """Capability names this personality opts into (e.g. ``("database",
    "memory")``)."""

    scope: str
    """One-sentence description of what this personality is for. Shown
    to the user in ``/onboard`` so they can pick."""

    keywords: tuple[str, ...] = ()
    """Words that match this suggestion when the user describes their
    purpose. Empty tuple = ``general`` fallback (always offered)."""


# The catalog. Order matters — `/onboard` presents suggestions in
# this order when matches are tied.
PERSONALITY_SUGGESTIONS: tuple[PersonalitySuggestion, ...] = (
    PersonalitySuggestion(
        name="general",
        capabilities=("database", "memory"),
        scope="General-purpose assistance: code questions, research, memory across sessions.",
        keywords=(),  # always offered as fallback
    ),
    PersonalitySuggestion(
        name="corpus_keeper",
        capabilities=("database", "memory"),
        scope="Codebase indexer + answerer; monorepos, EDA flows, large repos.",
        keywords=(
            "codebase", "search", "index", "indexer",
            "monorepo", "eda", "rag", "corpus", "knowledge graph",
        ),
    ),
    PersonalitySuggestion(
        name="librarian",
        capabilities=("database", "memory"),
        scope=(
            "Offline documentation librarian: curates manuals, library/API "
            "docs, PDK files, and internal wiki into a searchable index; "
            "answers 'look up the docs for X' via /docs when web search / "
            "context7 are unavailable."
        ),
        keywords=(
            "docs", "documentation", "manual", "reference", "library",
            "api", "pdk", "datasheet", "handbook", "wiki", "lookup",
            "web search", "websearch", "context7", "offline", "air-gap",
        ),
    ),
    PersonalitySuggestion(
        name="code_reviewer",
        capabilities=("memory",),
        scope="Reviews patches; uses memory for project conventions.",
        keywords=("review", "reviewer", "pr", "patch", "convention"),
    ),
    PersonalitySuggestion(
        name="debugger",
        capabilities=("database", "memory"),
        scope="Bug triage and root-cause analysis; remembers prior bugs and their fixes.",
        keywords=("debug", "debugger", "bug", "crash", "regression", "incident"),
    ),
    PersonalitySuggestion(
        name="research_assistant",
        capabilities=("memory",),
        scope="Long-running research notes, decisions, references; light on code.",
        keywords=("research", "notes", "decision", "design", "writing", "reference"),
    ),
)


def suggestion_dir(project_root: Path) -> Path:
    """Return ``<project_root>/.allmight/suggestions/personalities``."""
    return project_root / ".allmight" / "suggestions" / "personalities"


def seed_suggestions(project_root: Path, *, force: bool = False) -> None:
    """Write every suggestion in the catalog to the suggestion dir.

    Each file is marker'd so re-init refreshes framework-shipped
    suggestions but preserves user-edited / user-added ones (the
    standard All-Might marker semantics).
    """
    target_dir = suggestion_dir(project_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    for s in PERSONALITY_SUGGESTIONS:
        path = target_dir / f"{s.name}.yaml"
        body = yaml.safe_dump(
            {
                "name": s.name,
                "capabilities": list(s.capabilities),
                "scope": s.scope,
                "keywords": list(s.keywords),
            },
            sort_keys=False,
        )
        content = f"{ALLMIGHT_MARKER_YAML}\n{body}"
        write_guarded(path, content, ALLMIGHT_MARKER_YAML, force=force)
