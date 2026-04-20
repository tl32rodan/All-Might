"""Memory Initializer — bootstraps the L1/L2/L3 agent memory system.

Architecture:
  L1: MEMORY.md at project root (hook-loaded, agent-writable)
  L2: memory/understanding/ per-corpus knowledge (agent reads/writes)
  L3: memory/journal/ + store/ (text files + SMAK vector index)
"""

from __future__ import annotations

from pathlib import Path

from .config import MemoryConfigManager


def _reminder_nudge_text() -> str:
    """Canonical nudge text — shared byte-equal by both runtimes.

    Injected into the OpenCode ``remember-trigger.ts`` plugin and the
    Claude Code ``memory-nudge.sh`` hook. Keeping a single source means
    a new reminder (e.g. the skills-log bullet) only has to be authored
    once.
    """
    return (
        "[Memory Nudge]\n"
        "Did anything worth remembering happen in the last few turns?\n"
        "If yes, run /remember (it decides the scope and writes).\n"
        "If nothing stands out, skip.\n"
        "\n"
        "Scope reminder: project-wide (portable) -> MEMORY.md;\n"
        "per-corpus knowledge -> memory/understanding/<workspace>.md;\n"
        "per-corpus personal state -> memory/<kind>/<workspace>.md;\n"
        "searchable -> memory/journal/<workspace>/.\n"
        "\n"
        "If you created a new skill or plugin this session -> append a "
        "bullet to memory/skills-log.md\n"
        "(date . path . why). Self-evolution leaves a trace."
    )


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

        # 4c. Skills log — trace of self-authored skills/plugins
        skills_log = root / "memory" / "skills-log.md"
        if not skills_log.exists():
            skills_log.write_text(self._skills_log_template())

        # 5. Generate hook scripts (nudge + L1 loader)
        self._generate_hooks(root)

        # 5b. Register hooks in .claude/settings.json (idempotent, marker-bounded)
        self._wire_claude_settings(root)

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
        nudge_text = _reminder_nudge_text()
        (hooks_dir / "memory-nudge.sh").write_text(f"""\
#!/usr/bin/env bash
# Memory Nudge — Claude Code Stop hook (throttled per-session)
#
# Fires every Stop. Reads cwd + session_id from stdin JSON. Keeps a
# per-session counter at memory/.nudge-counter-<session_id> (separate
# files per session -> no race across parallel sessions) and emits the
# nudge only when count % reminder_every_turns == 0.
set -euo pipefail

INPUT=$(cat 2>/dev/null || echo "{{}}")
PROJECT_DIR=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd','.'))" 2>/dev/null || echo ".")
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null || echo "")

# Without a session id we can't throttle safely — skip rather than risk
# a race on a shared counter.
if [ -z "$SESSION_ID" ]; then
    exit 0
fi

EVERY=$(python3 -c "
import sys, pathlib
try:
    import yaml  # type: ignore
except ImportError:
    print(5); sys.exit(0)
p = pathlib.Path('$PROJECT_DIR') / 'memory' / 'config.yaml'
try:
    data = yaml.safe_load(p.read_text()) or {{}}
    print(int(data.get('reminder_every_turns', 5)))
except Exception:
    print(5)
" 2>/dev/null || echo 5)

COUNTER_DIR="$PROJECT_DIR/memory"
mkdir -p "$COUNTER_DIR"
COUNTER_FILE="$COUNTER_DIR/.nudge-counter-$SESSION_ID"

COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

if [ "$((COUNT % EVERY))" -eq 0 ]; then
    cat <<'NUDGE'
{nudge_text}
NUDGE
fi
exit 0
""")
        (hooks_dir / "memory-load.sh").write_text("""\
#!/usr/bin/env bash
# L1 Loader — UserPromptSubmit hook
# Injects MEMORY.md content into agent context every turn.
# When memory/.l1-over-cap exists (set by cap_audit after Stop), prepend
# a triage warning *before* MEMORY.md so the agent sees it first.
set -euo pipefail

INPUT=$(cat)
PROJECT_DIR=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd','.'))" 2>/dev/null || echo ".")

NUDGE_FILE="$PROJECT_DIR/memory/.l1-over-cap"
if [ -f "$NUDGE_FILE" ]; then
    OVERFLOW=$(grep '^overflow_bytes:' "$NUDGE_FILE" 2>/dev/null | awk '{print $2}')
    OVERFLOW=${OVERFLOW:-?}
    cat <<NUDGE
\u26a0 L1 over cap by ${OVERFLOW} bytes. Triage required:
- Distill cross-cutting facts; remove stale/duplicate lines.
- Move corpus-specific content to memory/understanding/<workspace>.md.
- Move open TODOs to memory/todos/<workspace>.md.
Run /reflect and complete the cap-triage step (sentinel clears on next Stop).

NUDGE
fi

MEMORY_FILE="$PROJECT_DIR/MEMORY.md"
if [ -f "$MEMORY_FILE" ]; then
    echo "--- Project Memory (MEMORY.md) ---"
    cat "$MEMORY_FILE"
    echo "--- End Project Memory ---"
fi
exit 0
""")
        (hooks_dir / "memory-cap.sh").write_text("""\
#!/usr/bin/env bash
# L1 Cap Audit — Stop hook (F1.5)
# Audits MEMORY.md body size against the cap and writes/removes the
# memory/.l1-over-cap nudge sentinel. NEVER modifies MEMORY.md.
# Must never block Stop.
set -euo pipefail

INPUT=$(cat 2>/dev/null || echo "{}")
PROJECT_DIR=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd','.'))" 2>/dev/null || echo ".")

python3 -m allmight.memory.cap_audit "$PROJECT_DIR" >/dev/null 2>&1 || true
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
        # Canonical nudge text, substituted into the TS plugin so the
        # OpenCode and Claude Code paths share one source of truth.
        shared_nudge = (
            _reminder_nudge_text()
            .replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("${", "\\${")
        )
        template = """\
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

const SHARED_NUDGE = `__SHARED_NUDGE__`;

function nudgeText(turn: number): string {
  return `[Memory Nudge \\u2014 turn ${turn}]\\n` + SHARED_NUDGE;
}

function preCompactText(): string {
  return [
    "[Memory Nudge \\u2014 pre-compaction]",
    "Conversation is about to be summarised. Last chance before history is",
    "condensed: run /remember for anything worth persisting (user prefs,",
    "corrections, per-corpus discoveries). Delegate scope and writing to",
    "/remember.",
    "",
    SHARED_NUDGE,
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
        return template.replace("__SHARED_NUDGE__", shared_nudge)

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

        from .l1_rewriter import DEFAULT_MAX_BYTES, SENTINEL_MARKER

        memory_md.write_text(f"""\
<!-- {SENTINEL_MARKER}={DEFAULT_MAX_BYTES} -->
<!--
  L1 (MEMORY.md) is **portable-only** memory: what is true and useful no
  matter which corpus you work on. Keep it tight; over-cap triggers a
  passive nudge, not auto-eviction.

  Scope test: "still relevant in any workspace?" If no → not L1.

  Everything else belongs elsewhere:
  - Corpus-specific knowledge → memory/understanding/<workspace>.md
  - Open TODOs / session continuity → memory/<kind>/<workspace>.md
  - Searchable history → memory/journal/<workspace>/
-->

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
        for script_name in ("memory-nudge.sh", "memory-load.sh", "memory-cap.sh"):
            script = hooks_dir / script_name
            script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _wire_claude_settings(self, root: Path) -> None:
        """Register All-Might hooks in ``.claude/settings.json``."""
        from .settings_json import merge_hooks

        merge_hooks(
            root / ".claude" / "settings.json",
            {
                "Stop": [
                    {"command": "./.claude/hooks/memory-cap.sh"},
                    {"command": "./.claude/hooks/memory-nudge.sh"},
                ],
                "UserPromptSubmit": [
                    {"command": "./.claude/hooks/memory-load.sh"},
                ],
            },
        )

    def _skills_log_template(self) -> str:
        """Return the initial ``memory/skills-log.md`` body."""
        return (
            "# Self-Authored Skills\n"
            "\n"
            "Append a bullet whenever you write a new skill or plugin:\n"
            "- **YYYY-MM-DD** \u00b7 `path/to/SKILL.md` \u00b7 why you created it\n"
            "\n"
            "<!-- entries below -->\n"
        )

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

Create a file in `memory/journal/<workspace>/` or `memory/journal/general/`.
Wrap it with **v1 frontmatter** so future offline analysis can query the
journal via `allmight memory export --format jsonl`. The freeform body
stays first-class; the frontmatter is mechanical:

```markdown
---
allmight_journal: v1
id: <ISO-8601 timestamp + short hash, e.g. 2026-04-18T10:32-a7f3>
type: discovery        # trajectory | reflection | discovery | decision | correction
workspace: <name>      # or: general
trigger: slash_remember
input: |
  <the user message that led to this, redacted of secrets>
tool_calls: []         # list of {tool, args, verdict: ok|drift|blocked}
output: |
  <your final response summary>
outcome_label: success # success | partial | failure | aborted
tags: [<keywords>]
supersedes: null       # id of an older entry this replaces, or null
created_at: <ISO-8601>
---
# <date> — <brief title>

<What you learned, in your own words.>
```

### 3. Update L1 MEMORY.md (only if portable)

**L1 is portable-only.** The test: "is this still true and useful no
matter which corpus I work on?" If no → it does NOT belong in
`MEMORY.md`.

Portable examples: user preferences, cross-cutting conventions, global
env facts, project-level goals, the project map of workspaces.

Corpus-specific knowledge, open TODOs, and work-in-progress state are
NOT portable and must go to L2 (`memory/understanding/<workspace>.md`)
or `memory/<kind>/<workspace>.md` instead. When unsure, write to the
narrower per-corpus location.

`MEMORY.md` is loaded every turn by a hook, so unbounded growth costs
every agent turn. A Stop hook audits the byte cap and — if exceeded —
writes `memory/.l1-over-cap` to nudge the next turn to triage via
`/reflect`.

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

### 2c. L1 cap triage

Check for the cap-audit nudge sentinel:

```bash
cat memory/.l1-over-cap 2>/dev/null
```

If the file exists, MEMORY.md has grown past its byte cap. Triage
without waiting:

1. Read `MEMORY.md` line by line. For each line, classify it:
   - **Portable** (still useful in *any* corpus) → keep in L1.
   - **Corpus-specific** → move to
     `memory/understanding/<workspace>.md`.
   - **Open TODO / WIP** → move to `memory/todos/<workspace>.md` (or
     the matching `<kind>/<workspace>.md`).
2. Distill duplicates and stale bullets; keep the essence only.
3. Save `MEMORY.md`. The next Stop hook re-audits and removes
   `memory/.l1-over-cap` automatically when the body is back under
   cap.

**The cap never silently evicts anything** — this step is the only
place non-portable content leaves L1.

### 3. Log to L3 — Journal

Summarize what you learned this session as a journal entry in
`memory/journal/<workspace>/` or `memory/journal/general/`. Wrap it with
**v1 frontmatter** (see `/remember` for the full field list) so future
offline analysis can query it:

```markdown
---
allmight_journal: v1
id: <ISO-8601 timestamp + short hash>
type: reflection
workspace: <name>      # or: general
trigger: slash_reflect
input: |
  <what prompted this reflection>
tool_calls: []
output: |
  <the reflection in one line>
outcome_label: success
tags: [<keywords>]
supersedes: null
created_at: <ISO-8601>
---
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
        """Generate opencode.json for OpenCode compatibility.

        OpenCode owns its own reminder throttle inside
        ``remember-trigger.ts`` (in-memory ``Map<sessionID, State>``), so
        ``session_completed`` no longer needs to invoke the shell nudge
        — that hook is now Claude-Code-only, wired via
        ``.claude/settings.json``.

        This function clears any stale All-Might entry in
        ``experimental.hook.session_completed`` (left by older releases)
        while preserving any unrelated user-authored hook entries.
        """
        import json

        opencode_dir = root / ".opencode"
        opencode_dir.mkdir(exist_ok=True)
        opencode_json = opencode_dir / "opencode.json"

        if opencode_json.exists():
            try:
                config = json.loads(opencode_json.read_text())
            except (json.JSONDecodeError, OSError):
                config = {}
        else:
            config = {}

        experimental = config.setdefault("experimental", {})
        hook = experimental.setdefault("hook", {})

        # Drop any session_completed entry that called the shell nudge.
        entries = hook.get("session_completed") or []
        filtered = [
            entry for entry in entries
            if "memory-nudge.sh" not in " ".join(entry.get("command", []))
        ]
        if filtered:
            hook["session_completed"] = filtered
        else:
            hook.pop("session_completed", None)

        if not hook:
            experimental.pop("hook", None)
        if not experimental:
            config.pop("experimental", None)

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

        Writes four plugin files:
        - memory-load.ts   — primes MEMORY.md + scope-first principle per session
        - remember-trigger.ts — throttled per-session nudge (/remember + skills-log)
        - todo-curator.ts  — tracks TODOs across sessions per corpus
        - trajectory-writer.ts — F5: captures structured session trajectory
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
            "trajectory-writer.ts": self._trajectory_writer_plugin_content(),
        }

    def _trajectory_writer_plugin_content(self) -> str:
        """Return the OpenCode trajectory-writer.ts plugin content.

        F5 — captures structured session data (input, tool_calls, output,
        verdicts) and flushes a v1-frontmatter entry to
        memory/journal/<workspace>/<ts>-trajectory.md on session compaction
        or deletion. Transparent to the daily user: no nudges, no context
        injection — just a disk write.
        """
        return """\
/**
 * Trajectory Writer — OpenCode plugin (All-Might, F5)
 *
 * Captures structured session data so future offline analysis
 * (allmight memory export --format jsonl) has something to query.
 * Transparent to the daily user: never injects into the chat; only
 * writes a frontmatter-wrapped markdown file on flush events.
 *
 * Captured per session:
 *   - input     (last user message)
 *   - tool_calls (each {tool, args} from tool.execute.before,
 *                 annotated with verdict from tool.execute.after)
 *   - output    (accumulated agent response summary)
 *   - workspace (inferred from any knowledge_graph/<name>/ path)
 *
 * Flush triggers:
 *   - experimental.session.compacting — last chance before history is summarised
 *   - session.deleted                 — session closed without compaction
 *
 * Hook:
 *   - chat.message — record the latest user input (does NOT mutate output)
 */
import type { Plugin } from "@opencode-ai/plugin";
import { mkdirSync, writeFileSync } from "fs";
import { join } from "path";

type ToolCallRec = { tool: string; args: any; verdict: "ok" | "drift" | "blocked" };

type Trajectory = {
  workspace: string | null;
  input: string;
  tool_calls: ToolCallRec[];
  output: string;
  pendingToolIndex: number | null;
};

const sessions = new Map<string, Trajectory>();

const WORKSPACE_RE = /knowledge_graph\\/([^/\\s"']+)/;

function ensure(sid: string): Trajectory {
  let t = sessions.get(sid);
  if (!t) {
    t = {
      workspace: null,
      input: "",
      tool_calls: [],
      output: "",
      pendingToolIndex: null,
    };
    sessions.set(sid, t);
  }
  return t;
}

function inferWorkspace(args: any): string | null {
  if (!args) return null;
  const haystack = typeof args === "string" ? args : JSON.stringify(args);
  const m = haystack.match(WORKSPACE_RE);
  return m?.[1] ?? null;
}

function yamlEscape(s: string): string {
  // Block literal (|) keeps newlines verbatim; indent by 2 spaces.
  const indented = s.replace(/\\n/g, "\\n  ");
  return "|\\n  " + indented;
}

function flush(cwd: string, sid: string, t: Trajectory): void {
  if (!t.input && t.tool_calls.length === 0) return;
  const workspace = t.workspace ?? "general";
  const now = new Date();
  const iso = now.toISOString();
  const ts = iso.replace(/[:.]/g, "-");
  const id = `${iso.slice(0, 19)}-${sid.slice(0, 6)}`;
  const dir = join(cwd, "memory", "journal", workspace);
  mkdirSync(dir, { recursive: true });
  const path = join(dir, `${ts}-trajectory.md`);

  const outcome = t.tool_calls.some((c) => c.verdict === "drift" || c.verdict === "blocked")
    ? "partial"
    : "success";

  const toolCallsYaml =
    t.tool_calls.length === 0
      ? "[]"
      : "\\n" +
        t.tool_calls
          .map(
            (c) =>
              `  - tool: ${c.tool}\\n` +
              `    args: ${JSON.stringify(c.args)}\\n` +
              `    verdict: ${c.verdict}`,
          )
          .join("\\n");

  const frontmatter =
    "---\\n" +
    "allmight_journal: v1\\n" +
    `id: ${id}\\n` +
    "type: trajectory\\n" +
    `workspace: ${workspace}\\n` +
    "trigger: auto\\n" +
    `input: ${yamlEscape(t.input)}\\n` +
    `tool_calls: ${toolCallsYaml}\\n` +
    `output: ${yamlEscape(t.output)}\\n` +
    `outcome_label: ${outcome}\\n` +
    "tags: []\\n" +
    "supersedes: null\\n" +
    `created_at: ${iso}\\n` +
    "---\\n";

  const body = `# ${iso.slice(0, 10)} \\u2014 session trajectory (${workspace})\\n`;
  writeFileSync(path, frontmatter + body);
}

export const TrajectoryWriterPlugin: Plugin = async ({ directory }: any) => {
  const cwd = (directory as string | undefined) ?? process.cwd();

  return {
    event: async ({ event }: { event: any }) => {
      const sid = event?.properties?.sessionID ?? "";
      if (!sid) return;
      const type = event?.type;

      if (type === "session.created") {
        ensure(sid);
      } else if (type === "session.deleted") {
        const t = sessions.get(sid);
        if (t) flush(cwd, sid, t);
        sessions.delete(sid);
      }
    },

    "chat.message": async (input: any, output: any) => {
      const sid = input?.sessionID;
      if (!sid) return;
      const t = ensure(sid);
      // Capture the last user message verbatim. Never mutate output.parts
      // here — trajectory writing stays transparent to the chat.
      const parts = input?.parts;
      if (Array.isArray(parts)) {
        const texts = parts
          .filter((p: any) => p?.type === "text" && typeof p.text === "string")
          .map((p: any) => p.text);
        if (texts.length > 0) t.input = texts.join("\\n");
      }
      void output;
    },

    "tool.execute.before": async (input: any) => {
      const sid = input?.sessionID;
      if (!sid) return;
      const t = ensure(sid);
      if (!t.workspace) {
        const ws = inferWorkspace(input?.args);
        if (ws) t.workspace = ws;
      }
      t.tool_calls.push({
        tool: String(input?.tool ?? "unknown"),
        args: input?.args ?? {},
        verdict: "ok",
      });
      t.pendingToolIndex = t.tool_calls.length - 1;
    },

    "tool.execute.after": async (input: any) => {
      const sid = input?.sessionID;
      if (!sid) return;
      const t = ensure(sid);
      const idx = t.pendingToolIndex;
      if (idx !== null && t.tool_calls[idx]) {
        const verdict = input?.verdict;
        if (verdict === "drift" || verdict === "blocked" || verdict === "ok") {
          t.tool_calls[idx].verdict = verdict;
        }
      }
      t.pendingToolIndex = null;
    },

    "experimental.session.compacting": async (input: any, output: any) => {
      const sid = input?.sessionID;
      if (!sid) return;
      const t = sessions.get(sid);
      if (t) {
        flush(cwd, sid, t);
        // Reset captured state so post-compaction continues fresh.
        t.input = "";
        t.tool_calls = [];
        t.output = "";
      }
      void output;
    },
  };
};

export default TrajectoryWriterPlugin;
"""

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
