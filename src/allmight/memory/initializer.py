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

    def initialize(self, root: Path, staging: bool = False) -> None:
        """Bootstrap the memory subsystem at *root*.

        Args:
            root: Project root path.
            staging: If True, stage templates to .allmight/templates/
                     instead of writing to working locations.
        """
        if staging:
            self._stage_memory_templates(root)
            return

        # --- Direct init (first time or force) ---

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

        # 4b. Create usage.log for feedback loop
        usage_log = root / "memory" / "usage.log"
        if not usage_log.exists():
            usage_log.write_text("")

        # 5. Generate hook scripts (nudge + L1 loader)
        self._generate_hooks(root)

        # 6. Generate memory skill section
        self._generate_memory_skill(root)

        # 7. Generate memory commands (remember, recall, reflect)
        self._generate_memory_commands(root)

        # 8. Update CLAUDE.md
        self._update_claude_md(root)

        # 9. Refresh OpenCode compatibility (symlinks + opencode.json hooks)
        self._refresh_opencode_compat(root)

        # 10. Generate opencode.json with hooks for OpenCode
        self._generate_opencode_json(root)

    # ------------------------------------------------------------------
    # Staging (re-init)
    # ------------------------------------------------------------------

    def _stage_memory_templates(self, root: Path) -> None:
        """Stage memory templates to .allmight/templates/ for /sync."""
        tpl = root / ".allmight" / "templates"
        tpl.mkdir(parents=True, exist_ok=True)

        # Stage hook scripts
        hooks_tpl = tpl / "hooks"
        hooks_tpl.mkdir(parents=True, exist_ok=True)
        self._write_hook_content(hooks_tpl)

        # Stage memory commands
        cmds_tpl = tpl / "commands"
        cmds_tpl.mkdir(parents=True, exist_ok=True)
        self._write_memory_command_content(cmds_tpl)

        # Stage CLAUDE.md memory section
        (tpl / "memory-md-section.md").write_text(self._memory_claude_md_section())

        # Stage opencode.json and memory-load.ts
        import json
        opencode_config = {
            "experimental": {
                "hook": {
                    "session_completed": [
                        {"command": ["./.claude/hooks/memory-nudge.sh"]}
                    ]
                }
            }
        }
        (tpl / "opencode.json").write_text(json.dumps(opencode_config, indent=2) + "\n")
        (tpl / "memory-load.ts").write_text(self._opencode_plugin_content())

    def _write_hook_content(self, hooks_dir: Path) -> None:
        """Write hook script content to a directory."""
        (hooks_dir / "memory-nudge.sh").write_text("""\
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
        (hooks_dir / "memory-load.sh").write_text("""\
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

    def _write_memory_command_content(self, commands_dir: Path) -> None:
        """Write memory command content to a directory."""
        (commands_dir / "remember.md").write_text(self._remember_command_body())
        (commands_dir / "recall.md").write_text(self._recall_command_body())
        (commands_dir / "reflect.md").write_text(self._reflect_command_body())

    def _memory_claude_md_section(self) -> str:
        """Return the ALL-MIGHT-MEMORY section content for CLAUDE.md."""
        marker = "<!-- ALL-MIGHT-MEMORY -->"
        return f"""{marker}
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

    def _opencode_plugin_content(self) -> str:
        """Return the OpenCode memory-load.ts plugin content."""
        return """\
/**
 * Memory L1 Loader — OpenCode plugin
 *
 * Injects MEMORY.md content into agent context on every message,
 * equivalent to Claude Code's UserPromptSubmit hook.
 */
import { readFileSync, existsSync } from "fs";
import { join } from "path";

export default {
  name: "memory-load",
  "chat.message": async (message: any, context: any) => {
    const memoryPath = join(process.cwd(), "MEMORY.md");
    if (existsSync(memoryPath)) {
      const content = readFileSync(memoryPath, "utf-8");
      const prefix = [
        "--- Project Memory (MEMORY.md) ---",
        content,
        "--- End Project Memory ---",
        "",
      ].join("\\n");
      if (typeof message.content === "string") {
        message.content = prefix + message.content;
      }
    }
    return message;
  },
};
"""

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
        """Generate hook scripts for active memory management."""
        import stat

        hooks_dir = root / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        self._write_hook_content(hooks_dir)

        # Make executable
        for script_name in ("memory-nudge.sh", "memory-load.sh"):
            script = hooks_dir / script_name
            script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

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

### Feedback Loop (`memory/usage.log`)

Every `/remember`, `/recall`, and `/reflect` logs a line to `memory/usage.log`:

```
2026-04-16T10:30:00Z recall "auth patterns" results=3 used=2
2026-04-16T10:35:00Z remember workspace=pll "lock FSM uses 3 states"
2026-04-16T11:00:00Z reflect insights=3
```

During `/reflect`, you read this log and generate insights:
- Topics recalled often → promote to L2 understanding
- Recalls with 0 results → knowledge gaps to fill
- Workspaces remembered often → verify L2 is up to date
- Sessions with no enrichment → missed opportunities?

This closes the loop: **use → measure → improve**.

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
        """Generate /remember, /recall, and /reflect commands."""
        commands_dir = root / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        self._write_memory_command_content(commands_dir)

    def _remember_command_body(self) -> str:
        return """\
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

1. Log what you remembered to `memory/usage.log`:
```
<ISO-8601> remember workspace=<name> "<brief description>"
```

2. Run `smak ingest --config memory/smak_config.yaml` periodically to
   re-index the journal for `/recall` searches.

## What NOT to remember

- Trivial observations re-derivable from code
- Information already captured in sidecar enrichment
- Temporary debug notes
"""

    def _recall_command_body(self) -> str:
        return """\
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

## After recalling

Log the recall to `memory/usage.log`:
```
<ISO-8601> recall "<query>" results=<N> used=<how many were relevant>
```

## Also check

- `MEMORY.md` (L1) — always in context, check first
- `memory/understanding/<workspace>.md` (L2) — per-corpus knowledge
- L3 journal is for things not captured in L1 or L2
"""

    def _reflect_command_body(self) -> str:
        return """\
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

### 4. Usage Review — Feedback Loop

Read `memory/usage.log` and analyze this session's activity:

- **Recalls**: How many `/recall` searches? Were results useful (`used` > 0)?
  - If a topic was recalled often → consider promoting it to L2 understanding
  - If recalls returned 0 results → knowledge gap, write it to journal
- **Remembers**: What categories? Are you remembering broadly or narrowly?
  - All in one workspace → good depth
  - Scattered across many → check if L1 project map needs updating
- **Enrichments**: Did you `/enrich` any symbols this session?
  - If you read code but didn't enrich → were there opportunities missed?
- **Stale L2**: List `memory/understanding/*.md` files. Any not loaded this
  session that haven't been updated in a while? Flag them.

### 5. Generate Insights

Based on your usage review, write 2-3 actionable insights to
`memory/journal/general/` as a reflection entry:

```markdown
# <date> — Reflection Insights

## Usage Summary
- Recalls: N (M useful)
- Remembers: N (topics: ...)
- Enrichments: N symbols

## Insights
- <what worked well>
- <what could improve>
- <knowledge gaps discovered>
```

### 6. Re-index (if needed)

If you added journal entries, re-index for `/recall`:
```bash
smak ingest --config memory/smak_config.yaml
```

### 7. Log the reflection

Append to `memory/usage.log`:
```
<ISO-8601> reflect insights=<N>
```

## When to reflect

- End of a productive session
- After completing a major task
- When the Memory Nudge reminds you
- When the user asks you to consolidate what you learned
"""

    # ------------------------------------------------------------------
    # CLAUDE.md update
    # ------------------------------------------------------------------

    def _update_claude_md(self, root: Path) -> None:
        """Append memory system section to CLAUDE.md."""
        claude_md = root / "CLAUDE.md"
        marker = "<!-- ALL-MIGHT-MEMORY -->"
        memory_section = self._memory_claude_md_section()

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

    def _generate_opencode_json(self, root: Path) -> None:
        """Generate opencode.json with hooks for OpenCode compatibility.

        OpenCode's experimental config hooks support:
        - ``session_completed`` — fires when a session ends (≈ Claude's Stop hook)
        - ``file_edited`` — fires when files are edited

        We configure ``session_completed`` to run the memory-nudge script.

        For the L1 loader (MEMORY.md injection), OpenCode requires a plugin
        since config hooks don't support a ``user_prompt_submit`` equivalent.
        We generate a minimal plugin at ``.opencode/plugins/memory-load.ts``.
        """
        import json

        opencode_dir = root / ".opencode"
        opencode_dir.mkdir(exist_ok=True)
        opencode_json = opencode_dir / "opencode.json"

        # Build the config — merge with existing if present
        if opencode_json.exists():
            try:
                config = json.loads(opencode_json.read_text())
            except (json.JSONDecodeError, OSError):
                config = {}
        else:
            config = {}

        # Ensure experimental.hook structure exists
        experimental = config.setdefault("experimental", {})
        hook = experimental.setdefault("hook", {})

        # session_completed → memory-nudge.sh
        hook["session_completed"] = [
            {
                "command": ["./.claude/hooks/memory-nudge.sh"],
            }
        ]

        opencode_json.write_text(json.dumps(config, indent=2) + "\n")

        # Generate L1 loader plugin for OpenCode
        self._generate_opencode_memory_plugin(root)

    def _generate_opencode_memory_plugin(self, root: Path) -> None:
        """Generate OpenCode plugin that injects MEMORY.md into context."""
        plugins_dir = root / ".opencode" / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        plugin_file = plugins_dir / "memory-load.ts"
        plugin_file.write_text(self._opencode_plugin_content())

    def _refresh_opencode_compat(self, root: Path) -> None:
        """Ensure OpenCode compatibility symlinks exist after memory init."""
        import os

        # --- AGENTS.md → CLAUDE.md ---
        agents_md = root / "AGENTS.md"
        claude_md = root / "CLAUDE.md"
        if claude_md.exists() and not agents_md.exists():
            os.symlink("CLAUDE.md", str(agents_md))

        # --- .opencode/ directory with symlinks into .claude/ ---
        opencode_dir = root / ".opencode"
        claude_dir = root / ".claude"

        if not claude_dir.is_dir():
            return

        opencode_dir.mkdir(exist_ok=True)

        for subdir in ("skills", "commands"):
            source = claude_dir / subdir
            target = opencode_dir / subdir
            if source.is_dir() and not target.exists():
                os.symlink(
                    os.path.relpath(str(source), str(opencode_dir)),
                    str(target),
                )
