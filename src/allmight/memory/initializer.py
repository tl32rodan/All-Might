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
        """Append memory section to the one-for-all SKILL.md.

        Instead of creating a separate skill, we extend the unified
        one-for-all skill with memory instructions.
        """
        skill_path = root / ".claude" / "skills" / "one-for-all" / "SKILL.md"
        if not skill_path.exists():
            return

        marker = "<!-- MEMORY -->"
        memory_section = f"""
{marker}

## Agent Memory

Three-layer persistent memory for learning across sessions.

| Layer | Store | Purpose |
|-------|-------|---------|
| **Working** | `memory/working/MEMORY.md` | Always in context — user model, environment, goals |
| **Episodic** | `memory/episodes/` | Session history — observations, decisions |
| **Semantic** | `memory/semantic/` | Consolidated facts — with confidence and decay |

### Memory Commands

| Command | Purpose |
|---------|---------|
| `/remember` | Record an observation during this session |
| `/recall` | Search past memories across all layers |
| `/consolidate` | Convert session episodes into lasting facts |

### When to Remember

Use `/remember "..."` when you encounter:
- User corrections or preferences
- Discovered patterns or conventions
- Important decisions and their rationale

### When to Recall

Use `/recall "..."` before:
- Making assumptions about user preferences
- Facing a problem that seems familiar
- Starting work in a previously-visited area

### Consolidation

Run `/consolidate` periodically (weekly recommended) to extract lasting
facts from session episodes. The agent can also update working memory
sections (`user_model`, `environment`, `active_goals`, `pinned_memories`)
by editing `memory/working/MEMORY.md` directly.
"""
        content = skill_path.read_text()
        if marker in content:
            before = content[: content.index(marker)]
            content = before.rstrip() + "\n" + memory_section
        else:
            content = content.rstrip() + "\n" + memory_section
        skill_path.write_text(content)

    # ------------------------------------------------------------------
    # Command generation
    # ------------------------------------------------------------------

    def _generate_memory_commands(self, root: Path) -> None:
        """Generate memory slash commands — 3 simple commands."""
        commands_dir = root / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)

        (commands_dir / "remember.md").write_text(
            "Record an observation for the current session.\n\n"
            "Usage: `/remember \"<observation>\"`\n\n"
            "Observations are buffered in the current session's episode and\n"
            "consolidated into lasting facts when you run `/consolidate`.\n\n"
            "Good observations:\n"
            "- User corrections: \"User clarified that X means Y\"\n"
            "- Discovered patterns: \"All handlers use middleware pattern Z\"\n"
            "- Important decisions: \"Chose Redis because of pub/sub needs\"\n"
        )

        (commands_dir / "recall.md").write_text(
            "Search past memories across all layers.\n\n"
            "Usage: `/recall <query>`\n\n"
            "Searches semantic facts and episodic memory, scores by\n"
            "recency + importance + relevance, returns top results.\n"
            "Accessed memories resist future decay.\n"
        )

        (commands_dir / "consolidate.md").write_text(
            "Convert session episodes into lasting semantic facts.\n\n"
            "Usage: `/consolidate`\n\n"
            "1. Read unconsolidated episodes.\n"
            "2. Extract recurring observations and decisions.\n"
            "3. Create, reinforce, or supersede semantic facts.\n"
            "4. Mark processed episodes as consolidated.\n\n"
            "Run periodically (weekly recommended) or after significant work.\n"
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
| `/remember` | Record an observation during this session |
| `/recall` | Search past memories across all layers |
| `/consolidate` | Convert session episodes into lasting facts |

Memory entries have **decay** — frequently accessed memories persist longer.
Run `/status` to check memory health alongside enrichment coverage.
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
