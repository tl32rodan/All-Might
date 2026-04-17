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

        # 6. Generate memory commands (remember, recall, reflect)
        self._generate_memory_commands(root)

        # 7. Update CLAUDE.md
        self._update_claude_md(root)

        # 8. Refresh OpenCode compatibility (symlinks + opencode.json hooks)
        self._refresh_opencode_compat(root)

        # 9. Generate opencode.json with hooks for OpenCode
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
        (tpl / "package.json").write_text(self._opencode_package_json_content())
        for filename, content in self._opencode_plugin_map().items():
            (tpl / filename).write_text(content)

    def _write_hook_content(self, hooks_dir: Path) -> None:
        """Write hook script content to a directory."""
        (hooks_dir / "memory-nudge.sh").write_text("""\
#!/usr/bin/env bash
# Memory Nudge — Stop hook
# Fires every time the agent finishes a response.
# Reminds it to update memory under the right scope.
set -euo pipefail

cat <<'NUDGE'
[Memory Nudge] Before finishing, ask: what's the scope of what I learned?
- Project-wide (prefs, goals, env facts) → update MEMORY.md
- Per-corpus knowledge → memory/understanding/<workspace>.md
- Per-corpus personal state (open tasks, shortcuts, ad-hoc notes)
    → memory/<kind>/<workspace>.md  (create on demand, e.g. memory/todos/<workspace>.md)
- Worth searching later → append to memory/journal/<workspace>/

Prefer the narrower scope. Never dump per-corpus content into MEMORY.md.
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
decisions, corrections, learned patterns, and per-corpus personal
state (TODOs, shortcuts, ad-hoc notes).

| Command | What it does |
|---------|-------------|
| `/remember` | Save knowledge under the right scope |
| `/recall` | Search past journal entries via SMAK |
| `/reflect` | End-of-session review to keep memory tidy |

### Scope-first principle

Memory is **scope-first**: decide whether something is project-wide,
per-corpus, or a historical log before choosing where to write it.

- `MEMORY.md` — project-wide (always loaded): user prefs, goals, facts
- `memory/understanding/<workspace>.md` — per-corpus knowledge
- `memory/<kind>/<workspace>.md` — per-corpus personal state the
  agent creates on demand (e.g. `memory/todos/<stdcell>.md` for open
  tasks in the `stdcell` corpus). Follow the same
  `<kind>/<workspace>.md` naming as `understanding/`. No directory
  needs to be declared up front.
- `memory/journal/<workspace>/…` — searchable log, queried by `/recall`

When unsure, prefer **narrower scope**: a workspace file beats a
project-wide file beats `journal/general/`.

See `/remember`, `/recall`, and `/reflect` commands for detailed guides.
"""

    def _opencode_plugin_content(self) -> str:
        """Return the OpenCode memory-load.ts plugin content."""
        return """\
/**
 * Memory L1 Loader — OpenCode plugin (All-Might)
 *
 * Primes the agent's context with MEMORY.md (L1) plus the scope-first
 * memory principle. Primes once per session, and re-primes after each
 * compaction — compaction summarises conversation history and dilutes
 * the L1 cache, so we need a fresh injection when the agent resumes.
 *
 * Events subscribed:
 *   session.created   → mark session un-primed (fresh)
 *   session.compacted → mark session un-primed (re-inject next message)
 *   session.deleted   → drop state for the session
 *
 * Hook:
 *   chat.message → inject prefix once per (un-primed) session
 */
import type { Plugin } from "@opencode-ai/plugin";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

const SCOPE_FIRST_PRINCIPLE = `--- Memory Scope-First Principle ---
Before writing anything to memory, decide the scope:
- Project-wide fact / preference / goal → MEMORY.md (L1)
- Per-corpus knowledge → memory/understanding/<workspace>.md (L2)
- Per-corpus personal state (TODOs, shortcuts, ad-hoc notes)
    → memory/<kind>/<workspace>.md  (create on demand)
- Historical / searchable → memory/journal/<workspace>/<date>—<title>.md (L3)

Prefer the narrower scope. Never dump per-corpus content into MEMORY.md
or memory/journal/general/. See /remember for the full guide.
--- End Principle ---`;

// Sessions already primed with MEMORY.md + principle.
// Cleared on session.created / session.compacted so the next chat.message
// re-injects.
const primed = new Set<string>();

function buildPrefix(cwd: string): string {
  const parts: string[] = [];
  const memoryPath = join(cwd, "MEMORY.md");
  if (existsSync(memoryPath)) {
    parts.push(
      "--- Project Memory (MEMORY.md) ---",
      readFileSync(memoryPath, "utf-8"),
      "--- End Project Memory ---",
      ""
    );
  }
  parts.push(SCOPE_FIRST_PRINCIPLE, "");
  return parts.join("\\n");
}

export const MemoryLoadPlugin: Plugin = async ({ directory }: any) => {
  const cwd = (directory as string | undefined) ?? process.cwd();

  return {
    event: async ({ event }: { event: any }) => {
      const type = event?.type;
      const sid = event?.properties?.sessionID ?? "";
      if (!sid) return;
      if (
        type === "session.created" ||
        type === "session.compacted" ||
        type === "session.deleted"
      ) {
        primed.delete(sid);
      }
    },

    "chat.message": async (input: any, output: any) => {
      const sid = input?.sessionID;
      if (!sid) return;
      if (primed.has(sid)) return;

      const text = buildPrefix(cwd);
      if (!text.trim()) return;

      // Prepend as a text part — UserMessage content lives in output.parts
      if (Array.isArray(output?.parts)) {
        output.parts.unshift({ type: "text", text });
        primed.add(sid);
      }
    },
  };
};

export default MemoryLoadPlugin;
"""

    def _remember_trigger_plugin_content(self) -> str:
        """Return the OpenCode remember-trigger.ts plugin content."""
        return """\
/**
 * Remember Trigger — OpenCode plugin (All-Might)
 *
 * Nudges the agent to run /remember at the right moments. Does NOT
 * duplicate /remember's logic — it only times the prompt. Scope and
 * writing are delegated entirely to the /remember command, which is
 * the single source of truth for how memory gets written.
 *
 * Events:
 *   session.idle                     — every NUDGE_EVERY turns, queue nudge
 *   experimental.session.compacting  — queue last-chance nudge pre-compaction
 *   session.created / session.deleted — init / cleanup per-session state
 *
 * Hook:
 *   chat.message — inject any queued nudge as a prefix to the next user turn
 */
import type { Plugin } from "@opencode-ai/plugin";

const NUDGE_EVERY = 5;

type State = { idleCount: number; pendingNudge: string | null };
const sessions = new Map<string, State>();

const SCOPE_REMINDER = [
  "Scope reminder: project-wide \\u2192 MEMORY.md; per-corpus knowledge \\u2192",
  "memory/understanding/<workspace>.md; per-corpus personal state \\u2192",
  "memory/<kind>/<workspace>.md; searchable \\u2192 memory/journal/<workspace>/.",
  "If MEMORY.md > 3000 chars, first move oldest content to L2 or L3.",
].join("\\n");

function nudgeText(turn: number): string {
  return [
    `[Memory Nudge \\u2014 turn ${turn}]`,
    "Did anything worth remembering happen in the last few turns?",
    "If yes, run /remember (it decides the scope and writes).",
    "If nothing stands out, skip.",
    "",
    SCOPE_REMINDER,
  ].join("\\n");
}

function preCompactText(): string {
  return [
    "[Memory Nudge \\u2014 pre-compaction]",
    "Conversation is about to be summarised. Last chance before history is",
    "condensed: run /remember for anything worth persisting (user prefs,",
    "corrections, per-corpus discoveries). Delegate scope and writing to",
    "/remember.",
    "",
    SCOPE_REMINDER,
  ].join("\\n");
}

function ensure(sid: string): State {
  let s = sessions.get(sid);
  if (!s) {
    s = { idleCount: 0, pendingNudge: null };
    sessions.set(sid, s);
  }
  return s;
}

export const RememberTriggerPlugin: Plugin = async () => {
  return {
    event: async ({ event }: { event: any }) => {
      const sid = event?.properties?.sessionID ?? "";
      if (!sid) return;
      const type = event?.type;

      if (type === "session.idle") {
        const s = ensure(sid);
        s.idleCount += 1;
        if (s.idleCount % NUDGE_EVERY === 0) {
          s.pendingNudge = nudgeText(s.idleCount);
        }
      } else if (type === "session.created") {
        sessions.set(sid, { idleCount: 0, pendingNudge: null });
      } else if (type === "session.deleted") {
        sessions.delete(sid);
      }
    },

    "chat.message": async (input: any, output: any) => {
      const sid = input?.sessionID;
      const s = sessions.get(sid);
      if (!s?.pendingNudge) return;
      if (!Array.isArray(output?.parts)) return;
      const nudge = s.pendingNudge;
      s.pendingNudge = null;
      output.parts.unshift({ type: "text", text: nudge });
    },

    // Pre-compaction hook: inject the scope reminder directly into the
    // compaction prompt so the generated summary carries the framing.
    "experimental.session.compacting": async (_input: any, output: any) => {
      if (!output) return;
      const context = output.context ?? (output.context = []);
      if (Array.isArray(context)) {
        context.push(preCompactText());
      }
    },
  };
};

export default RememberTriggerPlugin;
"""

    def _todo_curator_plugin_content(self) -> str:
        """Return the OpenCode todo-curator.ts plugin content."""
        return """\
/**
 * TODO Curator — OpenCode plugin (All-Might)
 *
 * Strategic-layer task accounting. Complements OpenCode's built-in TODO
 * (tactical, per-session) by tracking TODOs across sessions, scoped per
 * corpus. The agent is never left staring at an empty TODO list on
 * session start — unfinished items from previous sessions surface
 * automatically.
 *
 * Three phases:
 *  1. Observe — tool.execute.after with tool="TodoWrite" captures the
 *               latest TODO array into an in-memory session ledger.
 *  2. Curate  — experimental.session.compacting (and session.deleted)
 *               append a dated section to memory/todos/<workspace>.md
 *               with the session's TODOs.
 *  3. Surface — on first tool call that reveals a workspace, load the
 *               "## Open" section from memory/todos/<workspace>.md and
 *               queue it for injection on the next chat.message.
 *
 * Workspace inference: scans any tool's args for a
 * knowledge_graph/<name>/ path fragment. If never seen this session,
 * curation at session end writes under "unscoped" workspace.
 */
import type { Plugin } from "@opencode-ai/plugin";
import { readFileSync, existsSync, mkdirSync, appendFileSync } from "fs";
import { join, dirname } from "path";

type TodoItem = { id?: string; content: string; status: string };
type Ledger = {
  workspace: string | null;
  latest: TodoItem[];
  pendingSurface: string | null;
};

const sessions = new Map<string, Ledger>();

function ensure(sid: string): Ledger {
  let s = sessions.get(sid);
  if (!s) {
    s = { workspace: null, latest: [], pendingSurface: null };
    sessions.set(sid, s);
  }
  return s;
}

const WORKSPACE_RE = /knowledge_graph\\/([^/\\s"']+)/;

function inferWorkspace(args: any): string | null {
  if (!args) return null;
  const haystack = typeof args === "string" ? args : JSON.stringify(args);
  const m = haystack.match(WORKSPACE_RE);
  return m?.[1] ?? null;
}

function loadOpenBacklog(cwd: string, workspace: string): string | null {
  const path = join(cwd, "memory", "todos", `${workspace}.md`);
  if (!existsSync(path)) return null;
  const content = readFileSync(path, "utf-8");
  const marker = "## Open";
  const openIdx = content.indexOf(marker);
  if (openIdx === -1) return null;
  const rest = content.slice(openIdx + marker.length);
  const nextMatch = rest.match(/\\n## /);
  const section = nextMatch ? rest.slice(0, nextMatch.index!) : rest;
  const body = section.trim();
  return body || null;
}

function appendCuration(
  cwd: string,
  workspace: string,
  items: TodoItem[],
): void {
  if (items.length === 0) return;
  const path = join(cwd, "memory", "todos", `${workspace}.md`);
  mkdirSync(dirname(path), { recursive: true });
  if (!existsSync(path)) {
    appendFileSync(
      path,
      `# ${workspace} TODOs\\n\\n## Open\\n\\n## Done\\n\\n## Blocked\\n`,
    );
  }
  const date = new Date().toISOString().slice(0, 10);
  const lines: string[] = [
    "",
    `## Session ${date}`,
    ...items.map((t) => {
      const mark = t.status === "completed" ? "x" : " ";
      const suffix = t.status === "in_progress" ? "  (in progress)" : "";
      return `- [${mark}] ${t.content}${suffix}`;
    }),
    "",
  ];
  appendFileSync(path, lines.join("\\n"));
}

function surfaceText(workspace: string, backlog: string): string {
  return [
    `[TODO Backlog \\u2014 ${workspace}]`,
    "Carried over from previous sessions:",
    backlog,
    "",
    "Decide which items to pull into this session's TODO list (via TodoWrite).",
  ].join("\\n");
}

export const TodoCuratorPlugin: Plugin = async ({ directory }: any) => {
  const cwd = (directory as string | undefined) ?? process.cwd();

  return {
    event: async ({ event }: { event: any }) => {
      const sid = event?.properties?.sessionID ?? "";
      if (!sid) return;
      const type = event?.type;

      if (type === "session.created") {
        ensure(sid);
      } else if (type === "session.deleted") {
        const s = sessions.get(sid);
        if (s) {
          appendCuration(cwd, s.workspace ?? "unscoped", s.latest);
        }
        sessions.delete(sid);
      }
    },

    "tool.execute.after": async (input: any) => {
      const sid = input?.sessionID;
      if (!sid) return;
      const s = ensure(sid);

      if (!s.workspace) {
        const ws = inferWorkspace(input?.args);
        if (ws) {
          s.workspace = ws;
          const backlog = loadOpenBacklog(cwd, ws);
          if (backlog) {
            s.pendingSurface = surfaceText(ws, backlog);
          }
        }
      }

      if (input?.tool === "TodoWrite") {
        const todos = input?.args?.todos;
        if (Array.isArray(todos)) {
          s.latest = todos.map((t: any) => ({
            id: t.id,
            content: t.content ?? t.activeForm ?? "",
            status: t.status ?? "pending",
          }));
        }
      }
    },

    "chat.message": async (input: any, output: any) => {
      const sid = input?.sessionID;
      const s = sessions.get(sid);
      if (!s?.pendingSurface) return;
      if (!Array.isArray(output?.parts)) return;
      const surface = s.pendingSurface;
      s.pendingSurface = null;
      output.parts.unshift({ type: "text", text: surface });
    },

    // Pre-compaction: append session's TODOs to the per-corpus ledger
    // and mention it in the compaction context so the summary doesn't
    // silently lose the curated file reference.
    "experimental.session.compacting": async (input: any, output: any) => {
      const sid = input?.sessionID;
      const s = sid ? sessions.get(sid) : undefined;
      if (!s?.workspace) return;
      appendCuration(cwd, s.workspace, s.latest);
      const context = output?.context ?? (output && (output.context = []));
      if (Array.isArray(context)) {
        context.push(
          `Curated TODO ledger updated at memory/todos/${s.workspace}.md \\u2014 ` +
            "reference it instead of duplicating the list in the summary.",
        );
      }
    },
  };
};

export default TodoCuratorPlugin;
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

## Decide the scope first

Before writing anything, ask: **what is this about?**

| Scope | Location | Examples |
|-------|----------|----------|
| Project-wide | `MEMORY.md` (L1) | user preferences, env facts, active goals |
| Per-corpus knowledge | `memory/understanding/<workspace>.md` (L2) | architecture, key files, debug SOPs |
| Per-corpus personal state | `memory/<kind>/<workspace>.md` | open TODOs, shortcuts, ad-hoc notes |
| Historical / searchable | `memory/journal/<workspace>/…` (L3) | discoveries, decisions, session logs |

**Rule of thumb**: if it applies to one corpus only, put it under a
per-corpus file keyed by workspace name. Never dump per-corpus content
into `MEMORY.md` or into `memory/journal/general/`. When unsure,
prefer the **narrower** scope.

When a new `<kind>` of per-corpus content appears (e.g. a TODO list, a
list of preferred CLI flags, naming conventions), create
`memory/<kind>/<workspace>.md` on demand — follow the same
`<kind>/<workspace>.md` naming as `understanding/`. No new directory
needs to be declared up front.

## What to remember

- **Corpus-specific knowledge**: architecture, patterns, key files, debug SOPs
- **Per-corpus personal state**: open TODOs, ad-hoc notes, shortcuts
- **User corrections**: "User clarified that X means Y"
- **Important decisions**: "Chose Redis over Memcached for pub/sub"
- **User preferences**: "User prefers concise answers"
- **Environment facts**: "Build requires Node 18+"

## How to execute

### 1. Update L2 understanding (primary, for knowledge)

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

### 1b. Per-corpus personal state (create on demand)

If the observation is *mutable per-corpus state* rather than stable
knowledge — open tasks, preferred flags, personal shortcuts — write
to `memory/<kind>/<workspace>.md`. Example for TODOs:

```markdown
# <workspace> TODO

## Open
- [ ] <task> — <optional context / date>

## Done
- [x] <task> — <date completed>
```

Create the file (and its parent directory) on first use. Apply the
same pattern for other kinds you find yourself needing.

### 2. Append to L3 journal (for searchability)

Create a file in `memory/journal/<workspace>/` or `memory/journal/general/`:

```markdown
# <date> — <brief title>

<What you learned, in your own words.>
```

### 3. Update L1 MEMORY.md (only if cross-cutting)

If the observation is truly project-wide (user preference, environment
fact, active goal), update `MEMORY.md` at the project root directly.
If it's about one workspace, do NOT write it here.

## After remembering

1. Log what you remembered to `memory/usage.log` (scope tag enables
   `/reflect` to audit drift):
```
<ISO-8601> remember scope=<project|workspace> workspace=<name|-> kind=<understanding|todos|journal|…> "<brief>"
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
Pick up where you left off, and search past memories.

`/recall` is **not just** a journal search. Before running a query,
scan the per-corpus memory folders so you inherit any unfinished state
left from previous sessions (open TODOs, ad-hoc notes, shortcuts). The
SMAK journal search is the last step, not the first.

## Recall procedure

### 1. L1 — MEMORY.md (already in context)

`MEMORY.md` is injected every turn. Re-read the Project Map, User
Preferences, and Active Goals sections before assuming anything.

### 2. L2 — Per-corpus knowledge

For the workspace(s) relevant to the current task, read
`memory/understanding/<workspace>.md`.

### 3. Scan per-corpus folders generally (pick up where you left off)

List the `memory/` directory. For every subdirectory *other than*
`understanding/`, `journal/`, and `store/` (i.e. every per-corpus
`<kind>/` the agent or a past session has created), look for a file
matching the current workspace:

```bash
ls memory/
# for each <kind>/ present, check:
cat memory/<kind>/<workspace>.md 2>/dev/null
```

Typical kinds you may encounter:
- `memory/todos/<workspace>.md` — open TODOs; check `## Open` for
  anything left unfinished.
- `memory/shortcuts/<workspace>.md` — preferred CLI flags or aliases.
- `memory/notes/<workspace>.md` — ad-hoc workspace notes.

Any `<kind>` can exist — the agent creates them on demand via
`/remember`. Treat unknown kinds the same way: read, decide if
anything is unfinished, and proceed.

### 4. L3 — Journal (SMAK semantic search)

```bash
smak search "<query>" --config memory/smak_config.yaml --index journal --top-k 5 --json
```

Results from `memory/journal/` text files with file path, matched
content, and relevance score.

## When to recall

- At the start of a session touching a known workspace (steps 1-3).
- Before making assumptions about user preferences.
- When facing a problem that seems familiar.
- When the user asks "did we discuss X before?" (step 4).

## After recalling

Log the recall to `memory/usage.log`:
```
<ISO-8601> recall "<query>" results=<N> used=<how many were relevant>
```
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

### 2b. Audit per-corpus scoping

List the files under `memory/` and check that each is scoped correctly
under the **scope-first** principle (see `/remember`):

- Anything in `MEMORY.md` that is really about *one* workspace?
  → Move it to the per-corpus file and leave at most a one-line
  pointer in `MEMORY.md` if the user truly needs it up front.
- Any `memory/journal/general/` entry that is really workspace-specific?
  → Move it under `memory/journal/<workspace>/`.
- Any ad-hoc per-corpus files you (or a past session) created —
  `memory/todos/<workspace>.md`, `memory/shortcuts/<workspace>.md`,
  etc.? → Confirm the name follows `<kind>/<workspace>.md` and the
  content is genuinely workspace-specific.

The goal: no matter what `<kind>` of personalized memory exists, it
lives under a consistent `memory/<kind>/<workspace>.md` path.

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
- **Scope drift**: Count `remember` entries grouped by `scope=` and
  `kind=`. If per-corpus personal state is piling up under
  `scope=project` or `workspace=-`, the agent is being too generic —
  re-scope those entries to their workspace.

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

        # Generate .opencode/package.json so OpenCode's bundled Bun can
        # bun-install the plugin runtime dependency at startup.
        self._write_opencode_package_json(root)

        # Generate OpenCode plugins (L1 loader + remember-trigger + todo-curator)
        self._generate_opencode_plugins(root)

    def _opencode_package_json_content(self) -> str:
        """Return the .opencode/package.json content.

        Only declares what OpenCode's Bun actually needs to install:
        @opencode-ai/plugin (the Plugin type and runtime). fs/path are
        Node built-ins that ship with Bun; no type package is required
        for runtime.
        """
        import json

        manifest = {
            "name": "all-might-opencode",
            "private": True,
            "dependencies": {
                "@opencode-ai/plugin": "latest",
            },
        }
        return json.dumps(manifest, indent=2) + "\n"

    def _write_opencode_package_json(self, root: Path) -> None:
        """Write .opencode/package.json (idempotent, preserves user edits).

        If a package.json already exists, merge @opencode-ai/plugin into
        its dependencies without touching anything else the user added.
        """
        import json

        pkg_path = root / ".opencode" / "package.json"
        pkg_path.parent.mkdir(parents=True, exist_ok=True)

        if pkg_path.exists():
            try:
                existing = json.loads(pkg_path.read_text())
            except (json.JSONDecodeError, OSError):
                existing = {}
            deps = existing.setdefault("dependencies", {})
            deps.setdefault("@opencode-ai/plugin", "latest")
            pkg_path.write_text(json.dumps(existing, indent=2) + "\n")
        else:
            pkg_path.write_text(self._opencode_package_json_content())

    def _generate_opencode_plugins(self, root: Path) -> None:
        """Generate all OpenCode plugins under .opencode/plugins/.

        Writes three plugin files:
        - memory-load.ts   — primes MEMORY.md + scope-first principle per session
        - remember-trigger.ts — nudges the agent to run /remember
        - todo-curator.ts  — tracks TODOs across sessions per corpus
        """
        plugins_dir = root / ".opencode" / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in self._opencode_plugin_map().items():
            (plugins_dir / filename).write_text(content)

    def _opencode_plugin_map(self) -> dict[str, str]:
        """Return mapping of plugin filename → content."""
        return {
            "memory-load.ts": self._opencode_plugin_content(),
            "remember-trigger.ts": self._remember_trigger_plugin_content(),
            "todo-curator.ts": self._todo_curator_plugin_content(),
        }

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
