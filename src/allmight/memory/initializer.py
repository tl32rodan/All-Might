"""Memory Initializer — bootstraps the agent memory subsystem.

Creates the ``memory/`` directory structure, memory config with store
definitions, memory skills, and slash commands.

Memory stores are managed **independently** from workspace corpora.
Store definitions live in ``memory/config.yaml`` and an internal
search-engine config is generated at ``memory/smak_config.yaml``.

Follows the same pattern as ``detroit_smak/initializer.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .config import MemoryConfigManager
from .episodic import EpisodicMemoryStore
from .semantic import SemanticMemoryStore
from .working import WorkingMemoryManager


class MemoryInitializer:
    """Creates the agent memory workspace."""

    def initialize(self, root: Path) -> None:
        """Bootstrap the memory subsystem at *root*.

        Expects ``config.yaml`` to already exist (run ``allmight init`` first).
        """
        # 1. Create memory config (includes store definitions)
        cfg_mgr = MemoryConfigManager(root)
        cfg = cfg_mgr.initialize()

        # 2. Initialise each memory layer
        working = WorkingMemoryManager(root, budget=cfg.working_memory_budget)
        working.initialize()

        episodic = EpisodicMemoryStore(root)
        episodic.initialize()

        semantic = SemanticMemoryStore(root)
        semantic.initialize()

        # 3. Create memory store directories
        (root / "memory" / "store").mkdir(parents=True, exist_ok=True)

        # 4. Migrate: clean up legacy memory indices from workspace config.yaml
        self._migrate_legacy_indices(root)

        # 5. Generate memory skill
        self._generate_memory_skill(root)

        # 6. Generate memory commands
        self._generate_memory_commands(root)

        # 7. Update CLAUDE.md
        self._update_claude_md(root)

        # 8. Refresh OpenCode compatibility symlinks
        self._refresh_opencode_compat(root)

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def _migrate_legacy_indices(self, root: Path) -> None:
        """Remove memory indices from workspace config.yaml if present.

        Earlier versions incorrectly added ``episodes`` and
        ``semantic_facts`` to the workspace config.  Clean them up.
        """
        config_path = root / "config.yaml"
        if not config_path.exists():
            return

        try:
            from ..config import ConfigManager
            mgr = ConfigManager(root)
            for name in ("episodes", "semantic_facts"):
                if mgr.get_index(name) is not None:
                    mgr.remove_index(name)
        except Exception:
            pass  # config.yaml may not be parseable

    # ------------------------------------------------------------------
    # Skill generation
    # ------------------------------------------------------------------

    def _generate_memory_skill(self, root: Path) -> None:
        """Generate ``.claude/skills/memory/SKILL.md``."""
        skills_dir = root / ".claude" / "skills" / "memory"
        skills_dir.mkdir(parents=True, exist_ok=True)

        content = """\
---
name: agent-memory
description: >-
  Three-layer agent memory system. Guides agents on how to observe,
  recall, consolidate, and manage memories across sessions.
  Working memory (always in context), episodic memory (session history),
  semantic memory (consolidated facts with decay scoring).
---

# Agent Memory System

> All-Might provides a three-layer memory architecture for persistent
> agent learning across sessions.

## Architecture

| Layer | Store | Access | Purpose |
|-------|-------|--------|---------|
| **Working Memory** | `memory/working/MEMORY.md` | Always in context | User model, environment facts, pinned memories |
| **Episodic Memory** | `memory/episodes/` | `/memory-recall` | Searchable session history |
| **Semantic Memory** | `memory/semantic/` | `/memory-recall` | Consolidated facts with decay |

## When to Observe

Record observations during a session when you encounter:

- **User corrections**: "User said X is actually Y"
- **Discovered patterns**: "All handlers follow pattern Z"
- **Important decisions**: "Chose approach A because of B"
- **User preferences**: "User prefers concise responses"
- **Environment facts**: "Build requires Node 18+"

Use `/memory-observe "observation text"` to buffer observations.

## When to Recall

Search memory before:

- Making assumptions about user preferences
- Facing a problem that feels familiar
- Starting work in an area you've visited before
- Needing context from a past session

Use `/memory-recall "query"` to search across all layers.

## When to Update Working Memory

Update working memory for information that should be present in
every session:

- Persistent user preferences
- Critical environment configurations
- Active project goals

Use `/memory-update <section> "content"` where section is one of:
`user_model`, `environment`, `active_goals`, `pinned_memories`.

## When to Consolidate

Run consolidation to convert session episodes into lasting knowledge:

- After several productive sessions
- When you notice recurring patterns
- Periodically (weekly recommended)

Use `/memory-consolidate` to run the consolidation engine.

## Memory × Knowledge Graph

Memory and the knowledge graph reinforce each other:

- Observations about code structure can seed sidecar enrichment
- Corrections about symbol intent should update both memory and sidecars
- Frequently recalled symbols indicate enrichment priority
- Graph communities boost memory retrieval relevance

## Commands

| Command | Purpose |
|---------|---------|
| `/memory-observe` | Record an observation for this session |
| `/memory-recall` | Search across all memory layers |
| `/memory-update` | Update a working memory section |
| `/memory-consolidate` | Convert episodes to semantic facts |
| `/memory-status` | Show memory health metrics |
"""
        (skills_dir / "SKILL.md").write_text(content)

    # ------------------------------------------------------------------
    # Command generation
    # ------------------------------------------------------------------

    def _generate_memory_commands(self, root: Path) -> None:
        """Generate memory slash commands in ``.claude/commands/``."""
        commands_dir = root / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)

        (commands_dir / "memory-observe.md").write_text(
            "Record an observation for the current session's episodic memory.\n\n"
            "Usage: `/memory-observe \"<observation>\"`\n\n"
            "Observations are stored in the current session's episode record.\n"
            "They will be consolidated into semantic facts during `/memory-consolidate`.\n\n"
            "Good observations:\n"
            "- User corrections: \"User clarified that X means Y\"\n"
            "- Discovered patterns: \"All API handlers use middleware pattern Z\"\n"
            "- Important decisions: \"Chose Redis over Memcached because of pub/sub needs\"\n"
            "- Environment facts: \"CI requires Python 3.11+\"\n"
        )

        (commands_dir / "memory-recall.md").write_text(
            "Search across all memory layers for relevant past knowledge.\n\n"
            "Usage: `/memory-recall <query>`\n\n"
            "1. Search semantic facts (consolidated knowledge) for matches.\n"
            "2. Search episodic memory (past sessions) for matches.\n"
            "3. Score results using composite retrieval (recency + importance + relevance).\n"
            "4. Present top results with source attribution and confidence scores.\n"
            "5. Update access metadata on retrieved entries (resists future decay).\n\n"
            "Add `--include-dormant` to also search faded memories.\n"
        )

        (commands_dir / "memory-update.md").write_text(
            "Update a section of working memory (MEMORY.md).\n\n"
            "Usage: `/memory-update <section> \"<content>\"`\n\n"
            "Sections:\n"
            "- `user_model` — User preferences, communication style, corrections\n"
            "- `environment` — Build tools, versions, system configurations\n"
            "- `active_goals` — Current objectives and milestones\n"
            "- `pinned_memories` — Critical facts that must always be in context\n\n"
            "Working memory is always loaded at session start. Keep it focused\n"
            "and within the token budget (check with `/memory-status`).\n"
        )

        (commands_dir / "memory-consolidate.md").write_text(
            "Trigger consolidation of recent episodes into semantic facts.\n\n"
            "Usage: `/memory-consolidate`\n\n"
            "1. Read all unconsolidated episodes.\n"
            "2. Extract recurring observations, decisions, and topics.\n"
            "3. Search existing semantic facts for overlap.\n"
            "4. Create new facts, reinforce existing ones, or supersede contradicted facts.\n"
            "5. Mark processed episodes as consolidated.\n"
            "6. Report: facts created, updated, superseded, conflicts detected.\n"
        )

        (commands_dir / "memory-status.md").write_text(
            "Show memory system health metrics.\n\n"
            "Usage: `/memory-status`\n\n"
            "Displays:\n"
            "- Working memory: token usage vs. budget, section breakdown\n"
            "- Episodic memory: total episodes, unconsolidated count\n"
            "- Semantic memory: total facts, average confidence, categories\n"
            "- Decay status: active / fading / dormant entry counts\n"
        )

    # ------------------------------------------------------------------
    # CLAUDE.md update
    # ------------------------------------------------------------------

    def _update_claude_md(self, root: Path) -> None:
        """Append memory system section to CLAUDE.md."""
        claude_md = root / "CLAUDE.md"
        marker = "<!-- ALL-MIGHT-MEMORY -->"

        memory_section = f"""{marker}
## Agent Memory System

This workspace has the **All-Might Agent Memory** subsystem enabled —
a three-layer persistent memory architecture for agent learning.

### Memory Layers

| Layer | Location | Purpose |
|-------|----------|---------|
| Working Memory | `memory/working/MEMORY.md` | Always-in-context facts (user model, environment, goals) |
| Episodic Memory | `memory/episodes/` | Append-only session records, searchable |
| Semantic Memory | `memory/semantic/` | Consolidated facts with confidence scoring and decay |

### Memory Commands

| Command | Purpose |
|---------|---------|
| `/memory-observe` | Record an observation during this session |
| `/memory-recall` | Search past memories across all layers |
| `/memory-update` | Update working memory sections |
| `/memory-consolidate` | Convert episodes into semantic facts |
| `/memory-status` | Check memory health and usage |

### Memory Guardrails

- **ALWAYS** use memory commands — do not hand-edit files in `memory/`.
- Observations are **append-only** — do not modify past episodes.
- Consolidation may **supersede** old facts when corrections are found.
- Working memory has a **token budget** — keep it focused.
- Memory entries have **decay** — frequently accessed memories persist longer.
"""
        if claude_md.exists():
            content = claude_md.read_text()
            if marker in content:
                before = content[: content.index(marker)]
                content = before.rstrip() + "\n\n" + memory_section
            else:
                content = content.rstrip() + "\n\n" + memory_section
            claude_md.write_text(content)
        else:
            claude_md.write_text(f"# Project\n\n{memory_section}")

    # ------------------------------------------------------------------
    # OpenCode compatibility
    # ------------------------------------------------------------------

    def _refresh_opencode_compat(self, root: Path) -> None:
        """Ensure ``AGENTS.md`` symlink exists after memory init.

        Only creates ``AGENTS.md → CLAUDE.md``.  We do NOT touch the
        ``.opencode/`` directory — it is OpenCode's own runtime dir
        (node_modules, plugins, etc.) and pre-creating it causes
        module-resolution errors.  OpenCode reads ``.claude/`` natively.
        """
        import os

        agents_md = root / "AGENTS.md"
        claude_md = root / "CLAUDE.md"
        if claude_md.exists() and not agents_md.exists():
            os.symlink("CLAUDE.md", str(agents_md))
