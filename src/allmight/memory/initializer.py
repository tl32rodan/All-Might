"""Memory Initializer — bootstraps the L1/L2/L3 agent memory system.

Architecture:
  L1: MEMORY.md at project root (hook-loaded, agent-writable)
  L2: memory/understanding/ per-corpus knowledge (agent reads/writes)
  L3: memory/journal/ + store/ (text files + SMAK vector index)
"""

from __future__ import annotations

from pathlib import Path

from .config import MemoryConfigManager


class MemoryInitializer:
    """Creates the agent memory system."""

    def initialize(self, root: Path) -> None:
        """Bootstrap the memory subsystem at *root*."""
        # 1. Create memory config (defines journal store + SMAK config)
        cfg_mgr = MemoryConfigManager(root)
        cfg_mgr.initialize()

        # 2. Create L1: MEMORY.md at project root
        self._create_memory_md(root)

        # 3. Create L2: understanding/ directory
        (root / "memory" / "understanding").mkdir(parents=True, exist_ok=True)

        # 4. Create L3: journal/ directory + store/
        (root / "memory" / "journal").mkdir(parents=True, exist_ok=True)
        (root / "memory" / "store").mkdir(parents=True, exist_ok=True)

        # 5. Generate hook scripts (nudge + L1 loader)
        self._generate_hooks(root)

        # 6. Generate memory skill section
        self._generate_memory_skill(root)

        # 7. Generate memory commands (remember, recall, reflect)
        self._generate_memory_commands(root)

        # 8. Update CLAUDE.md
        self._update_claude_md(root)

        # 9. Refresh OpenCode compatibility symlinks
        self._refresh_opencode_compat(root)

    # ------------------------------------------------------------------
    # L1: MEMORY.md
    # ------------------------------------------------------------------

    def _create_memory_md(self, root: Path) -> None:
        """Create MEMORY.md at project root (L1 cache).

        This file is loaded every turn via hook. The agent updates it
        as it learns about the project and the user.
        """
        memory_md = root / "MEMORY.md"
        if memory_md.exists():
            return  # don't overwrite agent's work

        memory_md.write_text("""\
# Project Memory

## Project Map

| Workspace | Description |
|-----------|-------------|
| *(no workspaces yet — run `/ingest` after creating one)* | |

See `memory/understanding/<workspace>.md` for detailed per-corpus knowledge.

## User Preferences

*(none recorded yet)*

## Active Goals

*(none set)*

## Key Facts

*(none recorded yet)*
""")

    # ------------------------------------------------------------------
    # Hooks — Memory Nudge + L1 Loader
    # ------------------------------------------------------------------

    def _generate_hooks(self, root: Path) -> None:
        """Generate hook scripts for active memory management.

        Two hooks:
        - memory-nudge.sh (Stop hook): reminds agent to update memory
        - memory-load.sh (UserPromptSubmit hook): injects MEMORY.md into context
        """
        import os
        import stat

        hooks_dir = root / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        # --- Stop hook: Memory Nudge ---
        nudge_script = hooks_dir / "memory-nudge.sh"
        nudge_script.write_text("""\
#!/usr/bin/env bash
# Memory Nudge — Stop hook
# Fires every time the agent finishes a response.
# Reminds it to update memory if it learned something.
set -euo pipefail

cat <<'NUDGE'
[Memory Nudge] Before finishing, consider:
- Did you learn something about a workspace? → Update memory/understanding/<workspace>.md
- Did the user share a preference or correction? → Update MEMORY.md
- Did you discover something worth logging? → Append to memory/journal/
NUDGE
exit 0
""")
        nudge_script.chmod(nudge_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        # --- UserPromptSubmit hook: L1 Loader ---
        loader_script = hooks_dir / "memory-load.sh"
        loader_script.write_text("""\
#!/usr/bin/env bash
# L1 Loader — UserPromptSubmit hook
# Injects MEMORY.md content into agent context every turn.
set -euo pipefail

INPUT=$(cat)
PROJECT_DIR=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd','.'))" 2>/dev/null || echo ".")

MEMORY_FILE="$PROJECT_DIR/MEMORY.md"
if [ -f "$MEMORY_FILE" ]; then
    echo "--- Project Memory (MEMORY.md) ---"
    cat "$MEMORY_FILE"
    echo "--- End Project Memory ---"
fi
exit 0
""")
        loader_script.chmod(loader_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # ------------------------------------------------------------------
    # Skill generation
    # ------------------------------------------------------------------

    def _generate_memory_skill(self, root: Path) -> None:
        """Append memory section to the one-for-all SKILL.md."""
        skill_path = root / ".claude" / "skills" / "one-for-all" / "SKILL.md"
        if not skill_path.exists():
            return

        marker = "<!-- MEMORY -->"
        memory_section = f"""
{marker}

## Agent Memory — L1 / L2 / L3

Three-tier persistent memory, organized like cache/RAM/disk.

| Tier | Location | Loaded | Managed by |
|------|----------|--------|------------|
| **L1** | `MEMORY.md` (project root) | Every turn (hook) | Agent writes |
| **L2** | `memory/understanding/<workspace>.md` | On workspace entry | Agent reads/writes |
| **L3** | `memory/journal/` | Via `/recall` (SMAK search) | Agent appends |

### L1 — MEMORY.md (Cache)

Always in context. Contains:
- **Project map** — brief intro for each workspace
- **User preferences** — communication style, tools, conventions
- **Active goals** — what the agent is currently working on
- **Key facts** — cross-cutting knowledge

Update `MEMORY.md` directly as you learn. Keep it concise.

### L2 — Understanding (RAM)

Per-corpus knowledge in `memory/understanding/<workspace>.md`:
- Source code / document roadmap
- Architecture overview and key files
- Debug SOP and known issues
- Patterns, conventions, and gotchas

Read the relevant file when entering a workspace. Update as you work.
Create new files for new workspaces.

### L3 — Journal (Disk)

Append-only text files in `memory/journal/`. Organized by workspace or topic:
```
memory/journal/
├── stdcell/
│   └── 2026-04-15-dq-clocking.md
├── pll/
│   └── 2026-04-15-lock-fsm.md
└── general/
    └── user-prefs.md
```

Searched via SMAK vector index (`memory/store/`).

### Memory Commands

| Command | Purpose |
|---------|---------|
| `/remember` | Write to L2 understanding + append L3 journal entry |
| `/recall` | Search L3 journal via SMAK |
| `/reflect` | End-of-session review: tidy L1, update L2, log to L3 |

### Memory Nudge (Stop Hook)

A Stop hook at `.claude/hooks/memory-nudge.sh` fires after every agent
response. It reminds you to update memory if you learned something.
This is deterministic — it always fires, unlike advisory instructions.

A UserPromptSubmit hook at `.claude/hooks/memory-load.sh` injects
`MEMORY.md` content into context every turn, making L1 truly always-loaded.
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
        """Generate /remember and /recall commands."""
        commands_dir = root / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)

        (commands_dir / "remember.md").write_text("""\
Record something worth persisting beyond this session.

## What to remember

- **Corpus-specific knowledge**: architecture, patterns, key files, debug SOPs
- **User corrections**: "User clarified that X means Y"
- **Important decisions**: "Chose Redis over Memcached for pub/sub"
- **User preferences**: "User prefers concise answers"
- **Environment facts**: "Build requires Node 18+"

## How to execute

### 1. Update L2 understanding (primary)

If the observation is about a specific workspace, update or create
`memory/understanding/<workspace>.md`:

```markdown
## Architecture
(what you learned about the codebase structure)

## Key Files
(important files and what they do)

## Debug SOP
(how to diagnose common issues)
```

### 2. Append to L3 journal (for searchability)

Create a file in `memory/journal/<workspace>/` or `memory/journal/general/`:

```markdown
# <date> — <brief title>

<What you learned, in your own words.>
```

### 3. Update L1 MEMORY.md (if cross-cutting)

If the observation is project-wide (user preference, environment fact,
active goal), update `MEMORY.md` at the project root directly.

## After remembering

Run `smak ingest --config memory/smak_config.yaml` periodically to
re-index the journal for `/recall` searches.

## What NOT to remember

- Trivial observations re-derivable from code
- Information already captured in sidecar enrichment
- Temporary debug notes
""")

        (commands_dir / "recall.md").write_text("""\
Search past memories across the journal.

## How to execute

```bash
smak search "<query>" --config memory/smak_config.yaml --index journal --top-k 5 --json
```

## What to expect

Results from `memory/journal/` text files. Each result contains:
- File path and matched content
- Relevance score

## When to recall

- Before making assumptions about user preferences
- When facing a problem that seems familiar
- When starting work in an area visited in past sessions
- When the user asks "did we discuss X before?"

## Also check

- `MEMORY.md` (L1) — always in context, check first
- `memory/understanding/<workspace>.md` (L2) — per-corpus knowledge
- L3 journal is for things not captured in L1 or L2
""")

        (commands_dir / "reflect.md").write_text("""\
Structured self-reflection to maintain memory quality.

Run periodically (end of session, after major work) to keep memory
accurate and tidy.

## Steps

### 1. Review L1 — MEMORY.md

Read `MEMORY.md` at project root. Ask yourself:
- Is the Project Map still accurate? Any new workspaces to add?
- Are Active Goals still current? Remove completed ones.
- Any Key Facts that are stale or wrong?

Update directly if anything changed.

### 2. Review L2 — Understanding

For each workspace you worked on this session, read
`memory/understanding/<workspace>.md`. Ask:
- Did I learn new architecture details? Add them.
- Did I discover a debug SOP or gotcha? Document it.
- Is the Key Files section still accurate?

Create the file if it doesn't exist yet.

### 3. Log to L3 — Journal

Summarize what you learned this session as a journal entry in
`memory/journal/<workspace>/` or `memory/journal/general/`:

```markdown
# <date> — <brief title>

<Summary of discoveries, decisions, and insights.>
```

### 4. Re-index (if needed)

If you added journal entries, re-index for `/recall`:
```bash
smak ingest --config memory/smak_config.yaml
```

## When to reflect

- End of a productive session
- After completing a major task
- When the Memory Nudge reminds you
- When the user asks you to consolidate what you learned
""")

    # ------------------------------------------------------------------
    # CLAUDE.md update
    # ------------------------------------------------------------------

    def _update_claude_md(self, root: Path) -> None:
        """Append memory system section to CLAUDE.md."""
        claude_md = root / "CLAUDE.md"
        marker = "<!-- ALL-MIGHT-MEMORY -->"

        memory_section = f"""{marker}
## Agent Memory

The agent can **remember things across sessions**: preferences,
decisions, corrections, and learned patterns.

| Command | What it does |
|---------|-------------|
| `/remember` | Save knowledge to understanding files and journal |
| `/recall` | Search past journal entries via SMAK |
| `/reflect` | End-of-session review to keep memory tidy |

Memory is organized in three tiers:
- **MEMORY.md** — always loaded, project map and user preferences
- **memory/understanding/** — per-corpus knowledge, loaded on workspace entry
- **memory/journal/** — searchable log, accessed via `/recall`

The `one-for-all` skill has the complete operational guide.
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
        """Ensure AGENTS.md symlink exists after memory init."""
        import os

        agents_md = root / "AGENTS.md"
        claude_md = root / "CLAUDE.md"
        if claude_md.exists() and not agents_md.exists():
            os.symlink("CLAUDE.md", str(agents_md))
