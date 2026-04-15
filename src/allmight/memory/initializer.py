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
        """Generate memory slash commands — thick operational guides."""
        commands_dir = root / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)

        (commands_dir / "remember.md").write_text("""\
Record an observation worth persisting beyond this session.

## What to remember

- **User corrections**: "User clarified that X means Y"
- **Discovered patterns**: "All handlers follow middleware pattern Z"
- **Important decisions**: "Chose Redis over Memcached for pub/sub"
- **User preferences**: "User prefers concise answers"
- **Environment facts**: "Build requires Node 18+"

## How to execute

1. Write the observation as a YAML episode file in `memory/episodes/YYYY/MM/`:

```yaml
# memory/episodes/2026/04/sess_<session_id>.episode.yaml
id: ep_<random_12hex>
session_id: <current_session_id>
started_at: <ISO timestamp>
ended_at: <ISO timestamp>
summary: "Brief session summary"
observations:
  - "The observation you want to remember"
key_decisions: []
files_touched: []
topics: []
outcome: ""
importance: 0.5
consolidated: false
```

2. Or append to an existing episode file for this session if one exists.

## What to expect

- The observation is stored as part of the session episode
- It will surface when `/recall` searches for related queries
- During `/consolidate`, recurring observations become lasting facts
- Observations are append-only — never modify past episodes

## When NOT to remember

- Trivial observations the agent can re-derive from code
- Information already captured in sidecar enrichment
- Temporary debug notes
""")

        (commands_dir / "recall.md").write_text("""\
Search past memories across all layers.

## How to execute

1. Search `memory/semantic/` for fact files (`.fact.yaml`) whose content
   matches the query keywords.
2. Search `memory/episodes/` for episode files (`.episode.yaml`) whose
   summary or observations match.
3. Score each result using composite scoring:
   - **Recency** (30%): `e^(-hours_since_access / (168 * ln(1 + access_count)))`
   - **Importance** (30%): the entry's stored importance (0–1)
   - **Relevance** (40%): keyword overlap or semantic similarity
4. Return top results sorted by composite score.
5. For each returned fact, bump its `last_accessed` timestamp and
   `access_count` in the YAML file (this makes it resist future decay).

## What to expect

Results from two sources:
- **Semantic facts** (`memory/semantic/fact_*.fact.yaml`): consolidated,
  high-confidence knowledge with categories and source episodes
- **Episodes** (`memory/episodes/YYYY/MM/*.episode.yaml`): raw session
  records with observations, decisions, and file lists

## When to recall

- Before making assumptions about user preferences
- When facing a problem that seems familiar
- When starting work in an area visited in past sessions
- When the user asks "did we discuss X before?"

## Memory decay

Memories that are never accessed decay over time. The Ebbinghaus
forgetting curve `M(t) = e^(-t/S)` means:
- Frequently accessed memories persist (high S from access_count)
- Never-accessed memories fade after ~2 weeks
- Decayed memories still exist on disk but score too low to surface
""")

        (commands_dir / "consolidate.md").write_text("""\
Convert session episodes into lasting semantic facts.

## When to run

- After several productive sessions
- When you notice recurring patterns across episodes
- Periodically (weekly recommended)
- When the user asks to consolidate knowledge

## How to execute

1. List all episode files in `memory/episodes/` that have
   `consolidated: false`.
2. Extract recurring observations and decisions across episodes.
3. For each extracted pattern, search existing facts in
   `memory/semantic/` for overlap (Jaccard similarity >= 0.5).
4. Based on the match:
   - **No match**: create a new fact file in `memory/semantic/`:
     ```yaml
     # memory/semantic/fact_<random_12hex>.fact.yaml
     id: fact_<random_12hex>
     content: "The extracted pattern or knowledge"
     category: "domain_knowledge"  # or: user_preference, convention,
                                   #     correction, architecture_decision
     confidence: 1.0
     created_at: <ISO timestamp>
     updated_at: <ISO timestamp>
     last_accessed: <ISO timestamp>
     access_count: 0
     importance: 0.5
     source_episodes:
       - ep_<source_episode_id>
     supersedes: null
     namespace: default
     ```
   - **Match, consistent**: bump the existing fact's `confidence`
     (min +0.1, max 1.0) and add the source episode to its list
   - **Match, contradictory** (new info negates old): create a new fact
     with `supersedes: <old_fact_id>`, reduce old fact's confidence to 30%
5. Mark processed episodes as `consolidated: true`.
6. Report: facts created, updated, superseded, conflicts detected.

## What to expect

- New `.fact.yaml` files in `memory/semantic/`
- Updated confidence scores on existing facts
- Supersession chains for corrected knowledge
- Episodes marked as consolidated (won't be reprocessed)

## Working memory

If consolidation produces high-importance facts relevant to the user
model or environment, also update `memory/working/MEMORY.md` sections
(`user_model`, `environment`, `active_goals`, `pinned_memories`).
""")

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
