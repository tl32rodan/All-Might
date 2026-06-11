"""Memory Initializer — bootstraps the L1/L2/L3 agent memory system.

Architecture:
  L1: MEMORY.md at project root (hook-loaded, agent-writable)
  L2: memory/understanding/ per-corpus knowledge (agent reads/writes)
  L3: memory/journal/ + store/ (text files + SMAK vector index)
"""

from __future__ import annotations

from pathlib import Path

from ...core.markers import ALLMIGHT_MARKER_MD, ALLMIGHT_MARKER_TS
from ...core.safe_write import write_guarded
from ...core.skill_io import install_skill
from .config import MemoryConfigManager


_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _read_command_template(name: str) -> str:
    """Read a bundled command-body template as raw Markdown.

    Templates live under ``capabilities/memory/templates/commands/`` so
    the body is editable as Markdown rather than embedded in a Python
    string. The schedule capability established this pattern; memory
    follows it for ``/remember`` and ``/reflect``. ``/recall`` and
    ``/recover`` still inline their bodies — extraction is mechanical
    and tracked as a separate refactor step.
    """
    path = _TEMPLATES_DIR / "commands" / name
    return path.read_text()


def _routed_memory_paths(body: str) -> str:
    """Rewrite bare ``memory/`` paths in command bodies to the
    Part-D personality-routed form ``personalities/<active>/memory/``.

    Command bodies (e.g. ``/remember``, ``/recall``) reference
    per-personality memory under ``memory/...`` for source-code
    readability. At install time this helper prepends the routing
    prefix so the agent — operating from project root cwd — knows
    which personality's memory to act on after resolving
    ``<active>`` per ``ROUTING_PREAMBLE``.

    The substitution is anchored on the trailing slash, so
    ``MEMORY.md`` (uppercase, project root) and the word ``memory``
    alone are never touched.
    """
    return body.replace("memory/", "personalities/<active>/memory/")


def _reminder_nudge_text() -> str:
    """Canonical nudge text — shared byte-equal by both runtimes.

    Injected into the OpenCode ``remember-trigger.ts`` plugin and the
    Claude Code ``memory-nudge.sh`` hook. Keeping a single source means
    a new reminder (e.g. the skills-log bullet) only has to be authored
    once.
    """
    return (
        "[Memory Nudge]\n"
        "Persist what matters before it is lost. Look back at the last few\n"
        "turns and run /remember now UNLESS you can state in one line why\n"
        "nothing this session is worth keeping (/remember decides scope and\n"
        "writes). Worth keeping: user preferences, corrections, decisions,\n"
        "per-corpus discoveries, gotchas — anything a future session needs.\n"
        "\n"
        "Scope reminder (/remember resolves the exact path):\n"
        "project-wide (portable) -> MEMORY.md (L1);\n"
        "per-corpus knowledge -> understanding (L2);\n"
        "per-corpus state -> per-kind notes;\n"
        "searchable -> journal (L3).\n"
        "\n"
        "If you created a new skill or plugin this session -> add a "
        "bullet to the active personality's memory/skills-log.md\n"
        "(date . path . why). Self-evolution leaves a trace."
    )


DEFAULT_L2_WARN_FILES = 100
DEFAULT_L2_WARN_BYTES = 1024 * 1024            # 1 MB
DEFAULT_L3_WARN_FILES = 5000
DEFAULT_L3_WARN_BYTES = 50 * 1024 * 1024       # 50 MB
DEFAULT_L3_STALE_SECONDS = 24 * 3600           # 24 h


def compute_size_watch_text(
    root,
    *,
    l2_warn_files: int = DEFAULT_L2_WARN_FILES,
    l2_warn_bytes: int = DEFAULT_L2_WARN_BYTES,
    l3_warn_files: int = DEFAULT_L3_WARN_FILES,
    l3_warn_bytes: int = DEFAULT_L3_WARN_BYTES,
    l3_stale_seconds: int = DEFAULT_L3_STALE_SECONDS,
) -> str:
    """Return the ``[Memory Size Watch]`` block, or empty string.

    Walks ``personalities/*/memory/`` and reports per-personality
    L2 / L3 counts + sizes. Threshold-crossing personalities get
    additional warning lines. Empty memory layout (or no
    personalities) returns "" so the watch is invisible until there
    is something worth watching.

    Work item E' — see ``docs/plan.md``.
    """
    import time
    from pathlib import Path as _Path
    root = _Path(root)
    personalities = root / "personalities"
    if not personalities.is_dir():
        return ""

    last_ingest_path = root / ".allmight" / "last_ingest"
    if last_ingest_path.exists():
        try:
            last_ingest_age = time.time() - last_ingest_path.stat().st_mtime
        except OSError:
            last_ingest_age = None
    else:
        last_ingest_age = None

    blocks: list[str] = []
    for personality_dir in sorted(personalities.iterdir()):
        memory_dir = personality_dir / "memory"
        if not memory_dir.is_dir():
            continue
        # L2 stats
        l2_dir = memory_dir / "understanding"
        l2_files = list(l2_dir.glob("*.md")) if l2_dir.is_dir() else []
        l2_count = len(l2_files)
        l2_bytes = sum(
            (f.stat().st_size for f in l2_files if f.is_file()),
            start=0,
        )
        # L3 stats
        l3_dir = memory_dir / "journal"
        l3_files = list(l3_dir.rglob("*.md")) if l3_dir.is_dir() else []
        l3_count = len(l3_files)
        l3_bytes = sum(
            (f.stat().st_size for f in l3_files if f.is_file()),
            start=0,
        )

        if l2_count == 0 and l3_count == 0:
            continue

        lines = [f"- **{personality_dir.name}**:"]
        lines.append(f"  - L2: {l2_count} files / {l2_bytes // 1024} KB")
        lines.append(f"  - L3: {l3_count} files / {l3_bytes // 1024} KB")
        # Warnings
        if l2_count >= l2_warn_files or l2_bytes >= l2_warn_bytes:
            lines.append(
                "  - L2 over threshold — approaching the L2-RAG "
                "decision point at 200 files (see docs/plan.md non-goal)."
            )
        if l3_count >= l3_warn_files or l3_bytes >= l3_warn_bytes:
            lines.append(
                "  - L3 over threshold — consider `smak ingest --rebuild` "
                "or trimming old journal entries."
            )
        if (
            last_ingest_age is not None
            and last_ingest_age > l3_stale_seconds
        ):
            hours = int(last_ingest_age // 3600)
            lines.append(
                f"  - L3 index stale (>{hours}h since last ingest)."
            )
        blocks.append("\n".join(lines))

    if not blocks:
        return ""
    return "[Memory Size Watch]\n" + "\n".join(blocks)


def _l2_index_schema() -> str:
    """Canonical schema for ``memory/understanding/_index.md``.

    Single source of truth used by both ``/remember`` (writer) and
    ``/recall`` (reader). When this format changes, both command
    bodies pick up the new schema automatically because they embed
    this helper's output.

    The schema is the **description**, not the file content. The
    agent regenerates the actual ``_index.md`` from the schema each
    time L2 is written.

    Work item D' — see ``docs/plan.md``.
    """
    return (
        "```markdown\n"
        "# Understanding Index\n"
        "<!-- regenerated by /remember whenever L2 is written -->\n"
        "\n"
        "- **<workspace>**: <N sections>, last updated <ISO-8601>\n"
        "  - <one-line topic summary, <=80 chars>\n"
        "  - <another topic summary, <=80 chars>\n"
        "- **<another workspace>**: <N sections>, last updated <ISO-8601>\n"
        "  - <topic summary>\n"
        "```"
    )


class MemoryInitializer:
    """Creates the agent memory system."""

    def __init__(self) -> None:
        # Defaults so legacy callers (anything bypassing initialize)
        # still resolve to the old root-level layout.
        self._instance_root: Path | None = None
        self._instance_rel: str = ""

    def initialize_globals(
        self,
        root: Path,
        *,
        force: bool = False,
        staging: bool = False,
    ) -> None:
        """Project-wide install — root MEMORY.md, ``.opencode/`` commands +
        plugins, recover skill, Claude Code memory hooks, memory-history mirror.

        Per-personality data (``personalities/<n>/memory/``, ROLE.md,
        STATUS.md) lives in :meth:`initialize`. The memory-history
        mirror is initialised here on the global state; :meth:`initialize`
        re-syncs it after per-instance writes so any drift from
        ROLE.md / STATUS.md / config.yaml lands in the seed commit too.
        Both calls are idempotent.

        The two Claude Code hook scripts (``memory_load.py`` and
        ``memory_history.py``) mirror their OpenCode plugin siblings;
        their settings.json registration is wired by the project-level
        bridge in :mod:`allmight.core.claude_bridge` (called by
        :func:`core.personalities.write_init_scaffold`).
        """
        if staging:
            self._stage_memory_templates(root)
        else:
            self._create_memory_md(root)
            self._generate_memory_commands(root, force=force)
            self._generate_opencode_json(root, force=force)
            self._install_recover_skill(root, force=force)
        # Claude Code hooks: internal infrastructure mirroring the
        # OpenCode plugins. Written on EVERY init (fresh or re-init) —
        # they carry our marker, write_guarded protects user-edited
        # versions, and projects that predate the .claude/ mirror layer
        # need them backfilled. Placing them only in the ``else`` branch
        # is the bug we used to ship: re-init silently left them
        # missing while .claude/settings.json kept registering them,
        # producing "no such file" errors on every Stop event (and
        # those errors got fed back as user prompts by the OMO
        # claude-code-hooks bridge).
        self._write_claude_memory_load_hook(root, force=force)
        self._write_claude_memory_history_hook(root, force=force)
        self._init_memory_history(root)

    def initialize(
        self,
        root: Path,
        staging: bool = False,
        instance_root: Path | None = None,
        force: bool = False,
    ) -> None:
        """Bootstrap globals + one personality's memory subtree.

        Args:
            root: Project root path. Always holds ``MEMORY.md``.
            staging: If True, stage templates to .allmight/templates/
                     instead of writing to working locations.
            instance_root: Personality instance directory under
                ``personalities/<name>/``. The memory data dir lives
                here. When ``None`` (legacy callers) writes go under
                ``root`` to preserve the pre-personalities layout.
            force: If True, regenerate framework-owned files
                (``.opencode/plugins/*.ts``, generated commands,
                ROLE.md) even when the on-disk file is missing the
                All-Might marker. **Never touches user data**:
                ``MEMORY.md``, ``memory/journal/``,
                ``memory/understanding/``, ``memory/store/``, and
                ``memory/usage.log`` always preserve existing content.
        """
        self._instance_root = instance_root
        self._instance_rel = self._compute_instance_rel(root, instance_root)

        # Project-wide writes (idempotent — also seeds memory-history)
        self.initialize_globals(root, force=force, staging=staging)

        if staging:
            return

        # Per-instance writes
        memory_dir = self._memory_dir(root)

        # 1. Create memory config (defines journal store + SMAK config)
        cfg_mgr = MemoryConfigManager(root, memory_root=memory_dir)
        cfg_mgr.initialize()

        # 2. L2: understanding/
        (memory_dir / "understanding").mkdir(parents=True, exist_ok=True)

        # 3. L3: journal/ + store/
        (memory_dir / "journal").mkdir(parents=True, exist_ok=True)
        (memory_dir / "store").mkdir(parents=True, exist_ok=True)

        # 4. usage.log for feedback loop
        usage_log = memory_dir / "usage.log"
        if not usage_log.exists():
            usage_log.write_text("")

        # 5. skills-log.md — trace of self-authored skills/plugins
        skills_log = memory_dir / "skills-log.md"
        if not skills_log.exists():
            skills_log.write_text(self._skills_log_template())

        # 6. Lessons-learned curator workflow (_inbox/, _reviewed/)
        lessons = memory_dir / "lessons_learned"
        (lessons / "_inbox").mkdir(parents=True, exist_ok=True)
        (lessons / "_reviewed").mkdir(parents=True, exist_ok=True)

        # 7. STATUS.md — rolling per-personality state
        self._write_status_md()

        # 8. ROLE.md
        self._write_role_md(root, force=force)

        # 9. Memory-history mirror runs LAST so the seed commit captures
        #    everything we just wrote (MEMORY.md, ROLE.md, plugins,
        #    command files, etc.). Idempotent. Failures are non-fatal.
        self._init_memory_history(root)

    def _init_memory_history(self, root: Path) -> None:
        """Idempotently initialise ``.allmight/memory-history/``.

        Runs on every ``initialize()`` call (including the staging
        path) so projects that were init'd before this feature
        shipped pick up the recovery mirror on their next ``allmight
        init`` without needing ``--force``. Failures must not block
        init — surface as a warning and continue.
        """
        try:
            from .history import MemoryHistory

            MemoryHistory().init(root)
        except Exception as exc:
            import sys
            print(
                f"warning: memory-history init failed ({exc}); "
                "auto-recovery snapshots will not be available. "
                "Run `allmight memory snapshot` after fixing.",
                file=sys.stderr,
            )

    def _install_recover_skill(self, root: Path, force: bool = False) -> None:
        """Install the ``/recover`` SKILL.md (command body lives in
        ``_write_memory_command_content``)."""
        from .recover_skill_content import RECOVER_SKILL_BODY

        install_skill(
            root,
            name="recover",
            description=(
                "Restore memory data from the .allmight/memory-history/ "
                "snapshot mirror. Use when the user wants to undo an "
                "accidental memory edit, restore a deleted file, or roll "
                "back to an earlier state."
            ),
            skill_body=RECOVER_SKILL_BODY,
            force=force,
        )

    # ------------------------------------------------------------------
    # Instance-root helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_instance_rel(root: Path, instance_root: Path | None) -> str:
        """Return the instance dir as a forward-slash relative segment.

        Empty string when there's no instance dir (legacy layout) so
        path-string substitutions collapse cleanly to bare ``memory/``.
        """
        if instance_root is None or instance_root == root:
            return ""
        return instance_root.relative_to(root).as_posix() + "/"

    def _memory_dir(self, root: Path) -> Path:
        """The on-disk directory holding journal/store/understanding."""
        if self._instance_root is None or self._instance_root == root:
            return root / "memory"
        return self._instance_root / "memory"

    def _agent_surface_dirs(self, root: Path) -> tuple[Path, Path]:
        """Return (commands_dir, plugins_dir) — always project-global ``.opencode/``.

        Part-D: memory capability writes its share of
        ``.opencode/{commands,plugins}/`` once per project.
        Per-personality access goes through the upward symlink
        ``personalities/<p>/commands → ../../.opencode/commands``
        written by ``compose``.
        """
        return root / ".opencode" / "commands", root / ".opencode" / "plugins"

    @property
    def _mem_root_rel(self) -> str:
        """Path to the memory dir relative to project root, ``memory`` style."""
        return self._instance_rel + "memory"

    # ------------------------------------------------------------------
    # Staging (re-init)
    # ------------------------------------------------------------------

    def _stage_memory_templates(self, root: Path) -> None:
        """Stage memory templates to .allmight/templates/ for /sync."""
        tpl = root / ".allmight" / "templates"
        tpl.mkdir(parents=True, exist_ok=True)

        # Stage memory commands
        cmds_tpl = tpl / "commands"
        cmds_tpl.mkdir(parents=True, exist_ok=True)
        self._write_memory_command_content(cmds_tpl)

        # Stage ROLE / AGENTS section.
        if self._instance_root is not None and self._instance_root != root:
            inst_rel = self._instance_root.relative_to(root)
            staged_role = tpl / inst_rel / "ROLE.md"
            staged_role.parent.mkdir(parents=True, exist_ok=True)
            write_guarded(staged_role, self._role_md_body(), ALLMIGHT_MARKER_MD)
        else:
            # Legacy: stage marker-fenced section file like before.
            marker = "<!-- ALL-MIGHT-MEMORY -->"
            body = self._role_md_body()
            if body.startswith(ALLMIGHT_MARKER_MD):
                body = body[len(ALLMIGHT_MARKER_MD):].lstrip("\n")
            (tpl / "memory-md-section.md").write_text(f"{marker}\n{body}")

        # Stage opencode.json and plugins
        import json
        opencode_config = {}
        (tpl / "opencode.json").write_text(json.dumps(opencode_config, indent=2) + "\n")
        (tpl / "package.json").write_text(self._opencode_package_json_content())
        for filename, content in self._opencode_plugin_map().items():
            write_guarded(tpl / filename, content, ALLMIGHT_MARKER_TS)

    def _write_memory_command_content(
        self, commands_dir: Path, force: bool = False,
    ) -> None:
        """Write memory command content (``/remember``, ``/reflect``, ``/recall``, ``/recover``).

        ``/remember`` and ``/reflect`` are separate commands again
        (split from the merged ``/remember``+``Reflect`` body):
        ``/remember`` records a single observation; ``/reflect`` runs
        the periodic memory audit (staleness, scope drift, L1 cap
        triage). Keeping them apart lets each body stay short enough
        for less-capable models in air-gap deployments to follow.

        ``/recover`` wraps the ``allmight memory log/diff/restore`` CLI
        with the dialog needed to pick the right snapshot when a user
        wants to undo an accidental memory edit. The CLI stays
        available for scripting; ``/recover`` is the human-friendly
        facade.
        """
        from .recover_skill_content import RECOVER_COMMAND_BODY

        write_guarded(
            commands_dir / "remember.md",
            self._remember_command_body(),
            ALLMIGHT_MARKER_MD,
            force=force,
        )
        write_guarded(
            commands_dir / "reflect.md",
            self._reflect_command_body(),
            ALLMIGHT_MARKER_MD,
            force=force,
        )
        write_guarded(
            commands_dir / "recall.md",
            self._recall_command_body(),
            ALLMIGHT_MARKER_MD,
            force=force,
        )
        write_guarded(
            commands_dir / "recover.md",
            RECOVER_COMMAND_BODY,
            ALLMIGHT_MARKER_MD,
            force=force,
        )

    def _role_md_body(self) -> str:
        """Return the memory keeper's ROLE.md body."""
        return f"""{ALLMIGHT_MARKER_MD}
# Memory Keeper

You remember things across sessions for this project: preferences,
decisions, corrections, learned patterns, and per-corpus personal
state (TODOs, shortcuts, ad-hoc notes).
(*corpus = workspace; see the corpus keeper's role for the
definition*)

### Capabilities

| Command | What it does |
|---------|-------------|
| `/remember` | Save a single observation under the right scope |
| `/reflect` | End-of-session audit: cap triage, scope drift, insights |
| `/recall` | Search past journal entries via SMAK |
| `/recover` | Restore an accidentally edited or deleted memory file |

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
- `memory/lessons_learned/_inbox/<ts>-<unix-user>.md` — Mode-2
  (shared instance) curator-audited memory: write freely during a
  session; the curator periodically promotes / discards / moves
  entries to `_reviewed/`

When unsure, prefer **narrower scope**: a workspace file beats a
project-wide file beats `journal/general/`.

### STATUS.md — rolling personality state

Beside this `ROLE.md` lives `STATUS.md`: the personality's *current*
state surface (Active focus, Recent topics, Open threads,
last_activity). Treat it as the personality's **dashboard**:

- The frontmatter `last_activity` is bumped on every `/remember`.
- Active focus is one line; the long form lives in journal entries.
- Recent topics is FIFO ~5 entries.
- Open threads carry across sessions; the agent reads them at
  session start to know "what's still open under this role".

Other personalities reading the project map (in `MEMORY.md`) see
each personality's Active focus inline; for richer context they
open the relevant `STATUS.md`. See `/remember` for the maintenance
contract.

### Active personality — single source of truth

The **active personality** lives as a one-line callout at the top
of `MEMORY.md`:

```markdown
> **Active personality**: lab
```

`MEMORY.md` is loaded into your prompt every turn (via the memory-
load hook), so the callout is always visible. There is no separate
state file, no CLI command, no plugin sigil — just one line you
read and write.

When the user says "switch to <name>" (or any equivalent: "act as
the reviewer", "let's use ops for this", etc.), update that line
via the Edit tool:

1. Verify `<name>` exists in the Project Map table.
2. `Edit` `MEMORY.md`, replacing the body of the
   `> **Active personality**:` line with `<name>`.
3. Acknowledge in your response: "Switched to `<name>`."
4. Behave as `<name>` from this turn forward — read its
   `personalities/<name>/STATUS.md` to load context.

If the active line is missing or stale, fall back to the
`> **Default personality**:` callout (also in `MEMORY.md`, set on
first `/onboard`).

### Routing across personalities

You are not the memory keeper for *one* personality alone — you
maintain coherence **across** every personality the project hosts.
When the user shares a fact, decision, or correction, your job is
to figure out which personality(ies) it lives under and act
accordingly, even if the active personality is not the right home.

The routing contract:

- Read the active personality from `MEMORY.md`'s
  `> **Active personality**:` callout. That is the *default* for
  per-corpus writes.
- Read each candidate personality's `STATUS.md` (Active focus,
  Recent topics) and `ROLE.md` to figure out which one matches
  the topic of the current observation.
- If the active matches the topic → write under it as usual.
- If a different personality matches → tell the user "this looks
  like it belongs to `<X>`, switch first?" Never auto-switch.
- If the observation is cross-cutting → write to project-wide L1
  (`MEMORY.md` Key Facts) and add pointers in each relevant
  personality. Don't duplicate bodies.

`/remember` and `/recall` have step-by-step procedures; this
section sets the principle they implement.

See `/remember` and `/recall` commands for detailed guides.
"""

    def _opencode_plugin_content(self) -> str:
        """Return the OpenCode memory-load.ts plugin content."""
        from ...core.plugin_telemetry import TS_HEARTBEAT_SNIPPET
        return ("""\
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
import { readFileSync, existsSync, readdirSync, statSync } from "fs";
import { join } from "path";
import { spawn } from "child_process";

""" + TS_HEARTBEAT_SNIPPET + """
// Memory Size Watch thresholds — pinned in both TS and Python.
// If you change them here, change them in
// _claude_memory_load_hook_content too. See docs/plan.md E'.
const L2_WARN_FILES = 100;
const L2_WARN_BYTES = 1048576;       // 1 MB
const L3_WARN_FILES = 5000;
const L3_WARN_BYTES = 52428800;      // 50 MB
const L3_STALE_SECONDS = 86400;      // 24 h

function _statsFor(dir: string, recurse: boolean): { count: number; bytes: number } {
  let count = 0;
  let bytes = 0;
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return { count: 0, bytes: 0 };
  }
  for (const name of entries) {
    const full = join(dir, name);
    let st;
    try {
      st = statSync(full);
    } catch {
      continue;
    }
    if (st.isDirectory()) {
      if (recurse) {
        const sub = _statsFor(full, true);
        count += sub.count;
        bytes += sub.bytes;
      }
    } else if (name.endsWith(".md")) {
      count += 1;
      bytes += st.size;
    }
  }
  return { count, bytes };
}

function computeSizeWatch(cwd: string): string {
  const personalitiesDir = join(cwd, "personalities");
  if (!existsSync(personalitiesDir)) return "";
  let lastIngestAge: number | null = null;
  const lastIngest = join(cwd, ".allmight", "last_ingest");
  if (existsSync(lastIngest)) {
    try {
      lastIngestAge = (Date.now() / 1000) - (statSync(lastIngest).mtimeMs / 1000);
    } catch { /* leave null */ }
  }
  let entries: string[];
  try {
    entries = readdirSync(personalitiesDir).sort();
  } catch {
    return "";
  }
  const blocks: string[] = [];
  for (const name of entries) {
    const memDir = join(personalitiesDir, name, "memory");
    if (!existsSync(memDir)) continue;
    const l2 = _statsFor(join(memDir, "understanding"), false);
    const l3 = _statsFor(join(memDir, "journal"), true);
    if (l2.count === 0 && l3.count === 0) continue;
    const lines: string[] = [`- **${name}**:`];
    lines.push(`  - L2: ${l2.count} files / ${Math.floor(l2.bytes / 1024)} KB`);
    lines.push(`  - L3: ${l3.count} files / ${Math.floor(l3.bytes / 1024)} KB`);
    if (l2.count >= L2_WARN_FILES || l2.bytes >= L2_WARN_BYTES) {
      lines.push("  - L2 over threshold — approaching the L2-RAG decision point at 200 files (see docs/plan.md non-goal).");
    }
    if (l3.count >= L3_WARN_FILES || l3.bytes >= L3_WARN_BYTES) {
      lines.push("  - L3 over threshold — consider `smak ingest --rebuild`.");
    }
    if (lastIngestAge !== null && lastIngestAge > L3_STALE_SECONDS) {
      const hours = Math.floor(lastIngestAge / 3600);
      lines.push(`  - L3 index stale (>${hours}h since last ingest).`);
    }
    blocks.push(lines.join("\\n"));
  }
  if (blocks.length === 0) return "";
  return "[Memory Size Watch]\\n" + blocks.join("\\n");
}

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

// L3 auto-ingest drain — see docs/plan.md work item C'. On every fresh
// session, if the Stop hook left an `.allmight/ingest.pending` marker
// behind, spawn `allmight memory ingest --incremental` fire-and-forget.
// Embedding cost (5–30s) runs off the hot path; the CLI clears the
// marker on success.
function maybeDrainIngest(cwd: string): void {
  try {
    const pending = join(cwd, ".allmight", "ingest.pending");
    if (!existsSync(pending)) return;
    const child = spawn("allmight", ["memory", "ingest", "--incremental"], {
      cwd,
      stdio: "ignore",
      detached: true,
    });
    child.unref();
    child.on("error", () => {
      // allmight not on PATH — silent. Next session re-tries.
    });
  } catch {
    // Plugin must never throw.
  }
}

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
  const sizeWatch = computeSizeWatch(cwd);
  if (sizeWatch) {
    parts.push(sizeWatch, "");
  }
  return parts.join("\\n");
}

export const MemoryLoadPlugin: Plugin = async ({ directory }: any) => {
  const cwd = (directory as string | undefined) ?? process.cwd();

  return {
    event: async ({ event }: { event: any }) => {
      emitHeartbeat("memory-load", cwd);
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
      if (type === "session.created") {
        // Drain any L3 ingest the previous session marked as pending.
        maybeDrainIngest(cwd);
      }
    },

    "chat.message": async (input: any, output: any) => {
      emitHeartbeat("memory-load", cwd);
      const sid = input?.sessionID;
      if (!sid) return;
      if (primed.has(sid)) return;

      const text = buildPrefix(cwd);
      if (!text.trim()) return;

      // Prepend as a text part — UserMessage content lives in output.parts.
      // Each Part requires id / sessionID / messageID (see OpenCode's
      // TextPart schema in session/message-v2.ts); omitting them makes
      // SyncEvent.run reject the mutated part with "sessionID required".
      const mid = output?.message?.id;
      if (!mid) return;
      if (!Array.isArray(output?.parts)) return;
      output.parts.unshift({
        id: "prt_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10),
        sessionID: sid,
        messageID: mid,
        type: "text",
        text,
        synthetic: true,
      });
      primed.add(sid);
      emitHeartbeat("memory-load.injected", cwd);
    },
  };
};

export default MemoryLoadPlugin;
""")

    def _remember_trigger_plugin_content(self) -> str:
        """Return the OpenCode remember-trigger.ts plugin content."""
        from ...core.plugin_telemetry import TS_HEARTBEAT_SNIPPET
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

__TS_HEARTBEAT_SNIPPET__
const NUDGE_EVERY = 3;

type State = { idleCount: number; pendingNudge: string | null };
const sessions = new Map<string, State>();

const SHARED_NUDGE = `__SHARED_NUDGE__`;

function nudgeText(turn: number): string {
  return `[Memory Nudge \\u2014 turn ${turn}]\\n` + SHARED_NUDGE;
}

function preCompactText(): string {
  return [
    "[Memory Nudge \\u2014 pre-compaction]",
    "Conversation is about to be summarised — this is a forced checkpoint.",
    "Before history is condensed you MUST: (1) run /reflect to audit this",
    "session, then (2) run /remember for anything worth persisting (user",
    "prefs, corrections, per-corpus discoveries). Skipping is allowed only",
    "if you state in one line why nothing is worth keeping. Delegate scope",
    "and writing to /remember.",
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

export const RememberTriggerPlugin: Plugin = async ({ directory }: any) => {
  const cwd = (directory as string | undefined) ?? process.cwd();

  return {
    event: async ({ event }: { event: any }) => {
      emitHeartbeat("remember-trigger", cwd);
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
      emitHeartbeat("remember-trigger", cwd);
      const sid = input?.sessionID;
      if (!sid) return;
      const s = sessions.get(sid);
      if (!s?.pendingNudge) return;
      if (!Array.isArray(output?.parts)) return;
      // Each Part requires id / sessionID / messageID (see OpenCode's
      // TextPart schema in session/message-v2.ts); omitting them makes
      // SyncEvent.run reject the mutated part with "sessionID required".
      const mid = output?.message?.id;
      if (!mid) return;
      const nudge = s.pendingNudge;
      s.pendingNudge = null;
      output.parts.unshift({
        id: "prt_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10),
        sessionID: sid,
        messageID: mid,
        type: "text",
        text: nudge,
        synthetic: true,
      });
      emitHeartbeat("remember-trigger.injected", cwd);
    },

    // Pre-compaction hook: inject the scope reminder directly into the
    // compaction prompt so the generated summary carries the framing.
    "experimental.session.compacting": async (input: any, output: any) => {
      emitHeartbeat("remember-trigger", cwd);
      const sid = input?.sessionID;
      if (!sid) return;
      if (!output) return;
      const context = output.context ?? (output.context = []);
      if (Array.isArray(context)) {
        context.push(preCompactText());
        emitHeartbeat("remember-trigger.injected", cwd);
      }
    },
  };
};

export default RememberTriggerPlugin;
"""
        return (
            template
            .replace("__SHARED_NUDGE__", shared_nudge)
            .replace("__TS_HEARTBEAT_SNIPPET__", TS_HEARTBEAT_SNIPPET)
        )

    def _todo_curator_plugin_content(self) -> str:
        """Return the OpenCode todo-curator.ts plugin content."""
        from ...core.plugin_telemetry import TS_HEARTBEAT_SNIPPET
        template = """\
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
 * database/<name>/ path fragment. If never seen this session,
 * curation at session end writes under "unscoped" workspace.
 */
import type { Plugin } from "@opencode-ai/plugin";
import { readFileSync, existsSync, mkdirSync, appendFileSync, readdirSync } from "fs";
import { join, dirname } from "path";

__TS_HEARTBEAT_SNIPPET__

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

const WORKSPACE_RE = /database\\/([^/\\s"']+)/;

function inferWorkspace(args: any): string | null {
  if (!args) return null;
  const haystack = typeof args === "string" ? args : JSON.stringify(args);
  const m = haystack.match(WORKSPACE_RE);
  return m?.[1] ?? null;
}

function memoryDirForWorkspace(cwd: string, workspace: string): string {
  const personalitiesDir = join(cwd, "personalities");
  if (existsSync(personalitiesDir)) {
    let entries: string[] = [];
    try { entries = readdirSync(personalitiesDir); } catch { entries = []; }
    // First: a personality that owns this workspace under its database/
    for (const name of entries) {
      if (existsSync(join(personalitiesDir, name, "database", workspace))) {
        return join(personalitiesDir, name, "memory");
      }
    }
    // Fallback: first personality with a memory/ subdir
    for (const name of entries.sort()) {
      const memDir = join(personalitiesDir, name, "memory");
      if (existsSync(memDir)) return memDir;
    }
  }
  return join(cwd, "memory");
}

function loadOpenBacklog(cwd: string, workspace: string): string | null {
  const path = join(memoryDirForWorkspace(cwd, workspace), "todos", `${workspace}.md`);
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
  const path = join(
    memoryDirForWorkspace(cwd, workspace), "todos", `${workspace}.md`,
  );
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
      emitHeartbeat("todo-curator", cwd);
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
      emitHeartbeat("todo-curator", cwd);
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
      emitHeartbeat("todo-curator", cwd);
      const sid = input?.sessionID;
      if (!sid) return;
      const s = sessions.get(sid);
      if (!s?.pendingSurface) return;
      if (!Array.isArray(output?.parts)) return;
      // Each Part requires id / sessionID / messageID (see OpenCode's
      // TextPart schema in session/message-v2.ts); omitting them makes
      // SyncEvent.run reject the mutated part with "sessionID required".
      const mid = output?.message?.id;
      if (!mid) return;
      const surface = s.pendingSurface;
      s.pendingSurface = null;
      output.parts.unshift({
        id: "prt_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10),
        sessionID: sid,
        messageID: mid,
        type: "text",
        text: surface,
        synthetic: true,
      });
      emitHeartbeat("todo-curator.injected", cwd);
    },

    // Pre-compaction: append session's TODOs to the per-corpus ledger
    // and mention it in the compaction context so the summary doesn't
    // silently lose the curated file reference.
    "experimental.session.compacting": async (input: any, output: any) => {
      emitHeartbeat("todo-curator", cwd);
      const sid = input?.sessionID;
      const s = sid ? sessions.get(sid) : undefined;
      if (!s?.workspace) return;
      appendCuration(cwd, s.workspace, s.latest);
      const context = output?.context ?? (output && (output.context = []));
      if (Array.isArray(context)) {
        const ledger = join(
          memoryDirForWorkspace(cwd, s.workspace),
          "todos", `${s.workspace}.md`,
        );
        context.push(
          `Curated TODO ledger updated at ${ledger} \\u2014 ` +
            "reference it instead of duplicating the list in the summary.",
        );
        emitHeartbeat("todo-curator.injected", cwd);
      }
    },
  };
};

export default TodoCuratorPlugin;
"""
        return template.replace("__TS_HEARTBEAT_SNIPPET__", TS_HEARTBEAT_SNIPPET)

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

> **Active personality**: *(set on first `/onboard`, or change in chat: "switch to <name>")*

## Project Map

| Personality | Capabilities | Scope | Active focus |
|-------------|--------------|-------|--------------|
| *(no personalities yet — run `/onboard` after `allmight init`)* | | | |

See each personality's `STATUS.md` for richer rolling state
(active focus, recent topics, open threads). The "Active focus"
column above is a one-line summary; STATUS.md has the long form.
See `memory/understanding/<workspace>.md` for detailed per-corpus
knowledge.

## User Preferences

*(none recorded yet)*

## Active Goals

*(none set)*

## Key Facts

*(none recorded yet)*
""")
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

    def _generate_memory_commands(
        self, root: Path, force: bool = False,
    ) -> None:
        """Generate /remember and /recall commands."""
        commands_dir, _ = self._agent_surface_dirs(root)
        commands_dir.mkdir(parents=True, exist_ok=True)
        self._write_memory_command_content(commands_dir, force=force)

    def _remember_command_body(self) -> str:
        """Load the ``/remember`` body from the bundled template.

        The template ships as a plain Markdown file under
        ``capabilities/memory/templates/commands/remember.md`` so the
        body can be edited as Markdown (lintable, diff-friendly) rather
        than as a 480-line Python string. The same path-rewrite contract
        applies: every bare ``memory/`` is rewritten to
        ``personalities/<active>/memory/`` by ``_routed_memory_paths``,
        and ``ROUTING_PREAMBLE`` is prepended so the agent resolves
        ``<active>``.
        """
        from ...core.routing import ROUTING_PREAMBLE
        body = _read_command_template("remember.md")
        return ROUTING_PREAMBLE + _routed_memory_paths(body)

    def _reflect_command_body(self) -> str:
        """Load the ``/reflect`` body from the bundled template.

        ``/reflect`` was previously folded into ``/remember`` as a
        ``## Reflect`` section. Track Wave 2 split them back apart so
        less-capable agents in air-gap deployments can follow each
        body without reading past their attention window.
        """
        from ...core.routing import ROUTING_PREAMBLE
        body = _read_command_template("reflect.md")
        return ROUTING_PREAMBLE + _routed_memory_paths(body)

    def _recall_command_body(self) -> str:
        from ...core.routing import ROUTING_PREAMBLE
        # Same path-rewrite contract as ``_remember_command_body``.
        body = """\
Pick up where you left off, and search past memories.

`/recall` is **not just** a journal search. Before running a query,
scan the per-corpus memory folders so you inherit any unfinished state
left from previous sessions (open TODOs, ad-hoc notes, shortcuts). The
SMAK journal search is the last step, not the first.

## Recall procedure

### 1. L1 — MEMORY.md (already in context)

`MEMORY.md` is injected every turn. Re-read the Project Map, User
Preferences, and Active Goals sections before assuming anything.

### 2. L2 — Per-corpus knowledge (index-first)

Read `memory/understanding/_index.md` first. It is the TOC for L2 —
small (target <500 tokens), regenerated by `/remember` whenever L2
changes. The schema:

""" + _l2_index_schema() + """

From the index, **pick** the workspace(s) the query touches based on
the listed topic summaries. Only then read the full
`memory/understanding/<workspace>.md` for those workspaces.

If `_index.md` is missing or stale: fall back to listing
`memory/understanding/*.md` directly and reading the relevant ones,
then nudge: "the L2 index needs regenerating — `/remember` does
this on the next L2 write".

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

## Switch hint — when results live under a different personality

If the active personality (from `MEMORY.md`'s
`> **Active personality**:` callout) is `<Y>` but the most relevant
`/recall` results are in `<X>`'s journal/understanding, surface
this to the user *before* showing the full results:

> "Top hits are from `<X>`, not the active `<Y>`. Switch to `<X>`
> for full context?"

This is a **hint, not an action**. You never auto-switch. If the
user accepts, `Edit` `MEMORY.md` to update the callout to `<X>`
and proceed with the recall in that personality's context.

If results are split roughly equally across personalities, present
them grouped by personality and let the user pick.

## After recalling

Log the recall to `memory/usage.log`:
```
<ISO-8601> recall "<query>" results=<N> used=<how many were relevant>
```
"""
        return ROUTING_PREAMBLE + _routed_memory_paths(body)

    # ------------------------------------------------------------------
    # ROLE.md (per-personality role description)
    # ------------------------------------------------------------------

    def _write_role_md(self, root: Path, force: bool = False) -> None:
        """Write the memory keeper's role description **once**.

        ROLE.md is user-owned: ``/onboard`` rewrites the body to
        describe the personality's actual role, and the All-Might
        marker on line 1 typically survives that edit. Pre-fix,
        ``write_guarded`` saw the marker and overwrote on every
        re-init; under ``--force`` the overwrite happened even
        without a marker, silently destroying user content.

        ROLE.md is now **write-once at the framework level**. We
        emit a starter template only when no file exists. ``--force``
        is reserved for plugin/command/hook regeneration; user role
        descriptions are always preserved. To deliberately reset
        ROLE.md, the user removes the file and re-runs init.

        ``force`` is accepted for backward-compat in the call signature
        but intentionally ignored on this path.

        Legacy direct-call mode (no ``instance_root``) still splices
        a marker-fenced section into root AGENTS.md for backward
        compat with tests / clone / merge that bypass the registry.
        Removed once those callers migrate (§B.6.3).
        """
        if self._instance_root is not None and self._instance_root != root:
            target = self._instance_root / "ROLE.md"
            if target.exists():
                # User-owned. Never overwrite — including under --force.
                return
            self._instance_root.mkdir(parents=True, exist_ok=True)
            write_guarded(
                target,
                self._role_md_body(),
                ALLMIGHT_MARKER_MD,
            )
        else:
            self._write_legacy_agents_md(root)

    def _write_legacy_agents_md(self, root: Path) -> None:
        """Splice the memory section into root AGENTS.md (legacy path)."""
        agents_md = root / "AGENTS.md"
        if agents_md.is_symlink():
            agents_md.unlink()

        marker = "<!-- ALL-MIGHT-MEMORY -->"
        body = self._role_md_body()
        if body.startswith(ALLMIGHT_MARKER_MD):
            body = body[len(ALLMIGHT_MARKER_MD):].lstrip("\n")
        section = f"{marker}\n{body}"

        if agents_md.exists():
            content = agents_md.read_text()
            if marker in content:
                before = content[: content.index(marker)]
                content = before.rstrip() + "\n\n" + section
            else:
                content = content.rstrip() + "\n\n" + section
            agents_md.write_text(content)
        else:
            agents_md.write_text(f"# Project\n\n{section}")

    # ------------------------------------------------------------------
    # STATUS.md (Part-F: rolling per-personality state)
    # ------------------------------------------------------------------

    def _write_status_md(self) -> None:
        """Write a starter ``personalities/<p>/STATUS.md`` if missing.

        STATUS.md captures the personality's *current* state — active
        focus, recent topics, open threads, last activity — and is
        maintained by ``/remember`` over time. The framework only
        seeds the empty template; once anything is written, the file
        is user-/agent-owned and never overwritten on re-init (same
        write-once contract as ``ROLE.md``).

        No-op for legacy callers that don't pass an
        ``instance_root``: STATUS.md only makes sense per personality.
        """
        if self._instance_root is None or self._instance_root == self._instance_root.parent.parent:
            # Defensive: a missing or root-equal instance_root means
            # we're in the legacy single-instance layout. Skip — the
            # caller hasn't asked for per-personality state.
            return
        target = self._instance_root / "STATUS.md"
        if target.exists():
            return  # write-once
        self._instance_root.mkdir(parents=True, exist_ok=True)
        target.write_text(self._status_md_template())

    def _status_md_template(self) -> str:
        """Return the empty STATUS.md starter body.

        Schema is v1, frontmatter-fenced, three rolling sections.
        Agents fill these in via ``/remember``; humans can read or
        edit any section directly.
        """
        from datetime import datetime, timezone
        iso = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
        return (
            f"{ALLMIGHT_MARKER_MD}\n"
            "---\n"
            "allmight_status: v1\n"
            f"last_activity: {iso}\n"
            "---\n"
            f"# {self._instance_root.name if self._instance_root else 'personality'} — Status\n"
            "\n"
            "## Active focus\n"
            "*(no focus yet — agent updates this on /remember)*\n"
            "\n"
            "## Recent topics\n"
            "*(none yet — keep ~5 most recent, FIFO)*\n"
            "\n"
            "## Open threads\n"
            "*(none yet — long-running TODOs the agent should resume)*\n"
        )

    # ------------------------------------------------------------------
    # OpenCode compatibility
    # ------------------------------------------------------------------

    def _generate_opencode_json(
        self, root: Path, force: bool = False,
    ) -> None:
        """Generate opencode.json for OpenCode compatibility.

        Idempotent and non-destructive: ``$schema`` is only set when
        absent, so a project pointed at a corporate mirror keeps its
        own schema URL. The registry-driven init also calls
        ``write_init_scaffold`` which does the same thing — both
        callers must use ``setdefault`` semantics, otherwise a
        re-init overwrites the user's choice.
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

        config.setdefault("$schema", "https://opencode.ai/config.json")

        opencode_json.write_text(json.dumps(config, indent=2) + "\n")

        # Generate .opencode/package.json so OpenCode's bundled Bun can
        # bun-install the plugin runtime dependency at startup.
        self._write_opencode_package_json(root)

        # Generate .opencode/tsconfig.json so contributors and CI can
        # type-check the generated plugins via ``npx tsc --noEmit``.
        self._write_opencode_tsconfig(root)

        # Generate OpenCode plugins (L1 loader + remember-trigger + todo-curator)
        self._generate_opencode_plugins(root, force=force)

    def _opencode_package_json_content(self) -> str:
        """Return the .opencode/package.json content.

        Runtime dep: ``@opencode-ai/plugin`` (the Plugin type and
        runtime hooks). fs/path/process are Node built-ins; Bun
        provides them at runtime, so no runtime install is required.

        Dev deps are declared so contributors and CI can type-check
        the generated plugins via ``npx tsc --noEmit``:
          * ``@types/node`` — types for the Node built-ins the
            plugins use (fs, path, process).
          * ``typescript`` — pinned major version so the type-check
            output is reproducible across machines.
        Without ``@types/node``, ``tsc`` reports a wave of false
        ``Cannot find module 'fs'`` / ``Cannot find name 'process'``
        errors on framework-clean code.
        """
        import json

        manifest = {
            "name": "all-might-opencode",
            "private": True,
            "dependencies": {
                "@opencode-ai/plugin": "latest",
            },
            "devDependencies": {
                "@types/node": "^22",
                "typescript": "^5.4",
            },
        }
        return json.dumps(manifest, indent=2) + "\n"

    def _opencode_tsconfig_content(self) -> str:
        """Return the .opencode/tsconfig.json content.

        Tuned for the OpenCode runtime + the All-Might-emitted plugins:

        * ``target: ES2022`` — Bun runs ES2022 natively.
        * ``module: ESNext`` + ``moduleResolution: bundler`` — match
          how Bun resolves dependencies of ``@opencode-ai/plugin``.
        * ``types: ["node"]`` — explicit so Node built-ins
          (``fs``/``path``/``process``) resolve from
          ``@types/node`` without requiring the plugin author to
          remember to import them.
        * ``skipLibCheck: true`` — silences noise from transitive
          ``effect`` / ``fast-check`` ``.d.ts`` files which are not
          our concern.
        * ``strict: true`` + ``noEmit: true`` — type-check only;
          surface bugs early; never produce build artefacts.
        * ``include: ["plugins/**/*.ts"]`` — the only files we
          actually own and want checked.
        """
        import json

        config = {
            "compilerOptions": {
                "target": "ES2022",
                "module": "ESNext",
                "moduleResolution": "bundler",
                "strict": True,
                "skipLibCheck": True,
                "types": ["node"],
                "noEmit": True,
                "esModuleInterop": True,
                "lib": ["ES2022"],
            },
            "include": ["plugins/**/*.ts"],
        }
        return json.dumps(config, indent=2) + "\n"

    def _write_opencode_tsconfig(self, root: Path) -> None:
        """Write .opencode/tsconfig.json (idempotent, preserves user edits).

        If a tsconfig.json already exists (e.g. user customised the
        compiler options), leave it alone. The default we ship is
        good enough for ``tsc --noEmit`` to pass on the generated
        plugins, but customisation is the user's prerogative.
        """
        path = root / ".opencode" / "tsconfig.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return
        path.write_text(self._opencode_tsconfig_content())

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

    def _generate_opencode_plugins(
        self, root: Path, force: bool = False,
    ) -> None:
        """Generate all OpenCode plugins inside the instance plugins/ dir.

        Composition (registry-driven) symlinks each plugin under root
        ``.opencode/plugins/``; the legacy direct path is used when no
        instance_root is supplied.

        ``force`` propagates to ``write_guarded`` so ``allmight init
        --force`` actually regenerates plugins that the user edited
        out of marker. Without this, a hand-edited plugin would
        survive ``--force`` and the user has no clean way to recover
        the framework version short of ``rm`` followed by re-init.

        Writes four plugin files:
        - memory-load.ts   — primes MEMORY.md + scope-first principle per session
        - memory-history.ts — post-turn auto-snapshot of memory data
        - remember-trigger.ts — throttled per-session nudge (/remember + skills-log)
        - todo-curator.ts  — tracks TODOs across sessions per corpus
        """
        _, plugins_dir = self._agent_surface_dirs(root)
        plugins_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in self._opencode_plugin_map().items():
            write_guarded(
                plugins_dir / filename, content, ALLMIGHT_MARKER_TS,
                force=force,
            )

    def _write_claude_memory_load_hook(
        self, root: Path, force: bool = False,
    ) -> None:
        """Write ``.claude/hooks/memory_load.py`` — Claude Code mirror.

        Pairs with ``.opencode/plugins/memory-load.ts``. Both inject
        the same MEMORY.md content plus the scope-first principle so
        the agent's L1 cache stays warm across sessions and after
        compaction. When you change one, change the other (see All-
        Might ``CLAUDE.md`` -> Editor Compatibility).

        The settings.json registration is written by the project-level
        bridge in ``core.claude_bridge``; this method only emits the
        script body.
        """
        from ...core.claude_bridge import CLAUDE_HOOK_MARKER

        hooks_dir = root / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        target = hooks_dir / "memory_load.py"
        write_guarded(target, self._claude_memory_load_hook_content(),
                      CLAUDE_HOOK_MARKER, force=force)
        target.chmod(0o755)

    def _write_claude_memory_history_hook(
        self, root: Path, force: bool = False,
    ) -> None:
        """Write ``.claude/hooks/memory_history.py`` — Claude Code mirror.

        Pairs with ``.opencode/plugins/memory-history.ts``. Both
        spawn ``allmight memory snapshot`` after every agent turn to
        capture per-turn recovery points. ``core.claude_bridge``
        registers it on the ``Stop`` event in
        ``.claude/settings.json``.
        """
        from ...core.claude_bridge import CLAUDE_HOOK_MARKER

        hooks_dir = root / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        target = hooks_dir / "memory_history.py"
        write_guarded(target, self._claude_memory_history_hook_content(),
                      CLAUDE_HOOK_MARKER, force=force)
        target.chmod(0o755)

    def _claude_memory_load_hook_content(self) -> str:
        """Return the memory-load hook body for Claude Code.

        Functionally equivalent to the OpenCode memory-load.ts plugin:
        reads project-root MEMORY.md and prepends the scope-first
        principle, emitting the result as ``additionalContext`` for
        SessionStart / PreCompact.
        """
        from ...core.plugin_telemetry import PY_HEARTBEAT_SNIPPET
        template = '''\
#!/usr/bin/env python3
# all-might generated — DO NOT EDIT.
#
# Mirror of .opencode/plugins/memory-load.ts. Changes here MUST land in
# the .ts plugin too; see All-Might CLAUDE.md -> Editor Compatibility.
"""Memory-load hook for Claude Code (SessionStart, PreCompact).

Primes the agent with MEMORY.md (L1) plus the scope-first memory
principle. Same content the OpenCode memory-load plugin injects via
chat.message.

Also drains any L3 SMAK ingest pending from the previous session —
see docs/plan.md work item C'.
"""
import json
import os
import subprocess
import sys
from pathlib import Path


__PY_HEARTBEAT_SNIPPET__


def _maybe_drain_ingest(cwd):
    # L3 auto-ingest drain — fires once per fresh session. If the
    # Stop hook left `.allmight/ingest.pending` behind, spawn
    # `allmight memory ingest --incremental` fire-and-forget. The
    # CLI clears the marker on success.
    try:
        pending = Path(cwd) / ".allmight" / "ingest.pending"
        if not pending.exists():
            return
        subprocess.Popen(
            ["allmight", "memory", "ingest", "--incremental"],
            cwd=str(cwd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError):
        # allmight not on PATH — silent. Next session re-tries.
        pass


# Memory Size Watch thresholds — see docs/plan.md work item E'.
L2_WARN_FILES = 100
L2_WARN_BYTES = 1048576       # 1 MB
L3_WARN_FILES = 5000
L3_WARN_BYTES = 52428800      # 50 MB
L3_STALE_SECONDS = 86400      # 24 h


def _compute_size_watch(cwd):
    # Inline copy of allmight.capabilities.memory.initializer
    # .compute_size_watch_text — keeps the hook self-contained.
    import time as _time
    root = Path(cwd)
    personalities = root / "personalities"
    if not personalities.is_dir():
        return ""
    last_ingest_path = root / ".allmight" / "last_ingest"
    if last_ingest_path.exists():
        try:
            last_age = _time.time() - last_ingest_path.stat().st_mtime
        except OSError:
            last_age = None
    else:
        last_age = None
    blocks = []
    for personality_dir in sorted(personalities.iterdir()):
        memory_dir = personality_dir / "memory"
        if not memory_dir.is_dir():
            continue
        l2_dir = memory_dir / "understanding"
        l2_files = list(l2_dir.glob("*.md")) if l2_dir.is_dir() else []
        l2_count = len(l2_files)
        l2_bytes = sum(
            (f.stat().st_size for f in l2_files if f.is_file()),
            start=0,
        )
        l3_dir = memory_dir / "journal"
        l3_files = list(l3_dir.rglob("*.md")) if l3_dir.is_dir() else []
        l3_count = len(l3_files)
        l3_bytes = sum(
            (f.stat().st_size for f in l3_files if f.is_file()),
            start=0,
        )
        if l2_count == 0 and l3_count == 0:
            continue
        lines = [f"- **{personality_dir.name}**:"]
        lines.append(f"  - L2: {l2_count} files / {l2_bytes // 1024} KB")
        lines.append(f"  - L3: {l3_count} files / {l3_bytes // 1024} KB")
        if l2_count >= L2_WARN_FILES or l2_bytes >= L2_WARN_BYTES:
            lines.append(
                "  - L2 over threshold — approaching the L2-RAG "
                "decision point at 200 files (see docs/plan.md non-goal)."
            )
        if l3_count >= L3_WARN_FILES or l3_bytes >= L3_WARN_BYTES:
            lines.append(
                "  - L3 over threshold — consider `smak ingest --rebuild`."
            )
        if last_age is not None and last_age > L3_STALE_SECONDS:
            hours = int(last_age // 3600)
            lines.append(
                f"  - L3 index stale (>{hours}h since last ingest)."
            )
        blocks.append("\\n".join(lines))
    if not blocks:
        return ""
    return "[Memory Size Watch]\\n" + "\\n".join(blocks)

SCOPE_FIRST_PRINCIPLE = """--- Memory Scope-First Principle ---
Before writing anything to memory, decide the scope:
- Project-wide fact / preference / goal -> MEMORY.md (L1)
- Per-corpus knowledge -> memory/understanding/<workspace>.md (L2)
- Per-corpus personal state (TODOs, shortcuts, ad-hoc notes)
    -> memory/<kind>/<workspace>.md  (create on demand)
- Historical / searchable -> memory/journal/<workspace>/<date>-<title>.md (L3)

Prefer the narrower scope. Never dump per-corpus content into MEMORY.md
or memory/journal/general/. See /remember for the full guide.
--- End Principle ---"""


def main() -> int:
    _hb("memory_load")
    cwd = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    _maybe_drain_ingest(cwd)
    parts: list[str] = []
    size_watch = _compute_size_watch(cwd)
    memory_md = cwd / "MEMORY.md"
    if memory_md.is_file():
        try:
            body = memory_md.read_text(encoding="utf-8")
        except OSError:
            body = ""
        if body:
            parts.append("--- Project Memory (MEMORY.md) ---")
            parts.append(body.rstrip())
            parts.append("--- End Project Memory ---")
            parts.append("")
    parts.append(SCOPE_FIRST_PRINCIPLE)
    if size_watch:
        parts.append("")
        parts.append(size_watch)
    text = "\\n".join(parts).strip()
    if not text:
        return 0

    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        payload = {}
    event = payload.get("hook_event_name") or "SessionStart"

    _hb("memory_load.injected")
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": text,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''
        return template.replace("__PY_HEARTBEAT_SNIPPET__", PY_HEARTBEAT_SNIPPET)

    def _opencode_plugin_map(self) -> dict[str, str]:
        """Return mapping of plugin filename → content."""
        return {
            "memory-load.ts": self._opencode_plugin_content(),
            "memory-history.ts": self._memory_history_plugin_content(),
            "remember-trigger.ts": self._remember_trigger_plugin_content(),
            "todo-curator.ts": self._todo_curator_plugin_content(),
        }

    def _memory_history_plugin_content(self) -> str:
        """OpenCode plugin: post-turn auto-snapshot of memory data.

        Spawns ``allmight memory snapshot`` (fire-and-forget) on:

        * ``chat.message`` — every agent turn. Captures the granular
          recovery point users want for "I just deleted that file"
          mistakes.
        * ``experimental.session.compacting`` — pre-compaction
          fallback so any drift inside the compaction window lands
          in the mirror before context is rewritten.
        * ``session.deleted`` — final session-end fallback.

        Sibling Claude Code hook is ``.claude/hooks/memory_history.py``
        (see ``_claude_memory_history_hook_content``); both surfaces
        share the same CLI entry point, so behaviour is identical.

        Errors are swallowed: a plugin must never block the user's
        turn. If ``allmight`` isn't on PATH (e.g. a non-pip install),
        snapshots stop silently — recovery via ``allmight memory
        snapshot`` by hand still works.
        """
        from ...core.plugin_telemetry import TS_HEARTBEAT_SNIPPET
        template = """\
/**
 * Memory History — OpenCode plugin (All-Might)
 *
 * Post-turn / session-boundary auto-snapshot of personality memory
 * data into .allmight/memory-history/. Backs accidental-delete
 * recovery via `allmight memory restore`.
 *
 * Hooks:
 *   - chat.message               — granular per-turn snapshot
 *   - experimental.session.compacting — pre-compaction fallback
 *   - session.deleted            — final session-end fallback
 *
 * Spawns `allmight memory snapshot --trigger=... --session-id=...`
 * fire-and-forget. Errors are swallowed (plugin must not block).
 */
import type { Plugin } from "@opencode-ai/plugin";
import { spawn } from "child_process";
import {
  existsSync, statSync, readdirSync, mkdirSync, closeSync, openSync,
} from "fs";
import { join, dirname } from "path";

__TS_HEARTBEAT_SNIPPET__

// L3 auto-ingest marker-write — see docs/plan.md work item C'. If any
// journal entry is newer than `.allmight/last_ingest`, touch
// `.allmight/ingest.pending` so the next session.created drain
// triggers `allmight memory ingest --incremental`. Inline (no module
// import) so the hook stays self-contained and fast.
function maybeMarkIngestPending(cwd: string): void {
  try {
    const lastIngest = join(cwd, ".allmight", "last_ingest");
    let cutoff = 0;
    if (existsSync(lastIngest)) {
      cutoff = statSync(lastIngest).mtimeMs;
    }
    const personalitiesDir = join(cwd, "personalities");
    if (!existsSync(personalitiesDir)) return;
    const personalities = readdirSync(personalitiesDir);
    for (const p of personalities) {
      const journal = join(personalitiesDir, p, "memory", "journal");
      if (!existsSync(journal)) continue;
      if (anyFileNewer(journal, cutoff)) {
        const pending = join(cwd, ".allmight", "ingest.pending");
        mkdirSync(dirname(pending), { recursive: true });
        closeSync(openSync(pending, "w"));
        return;
      }
    }
  } catch {
    // Plugin must never throw.
  }
}

function anyFileNewer(dir: string, cutoff: number): boolean {
  // Recursive walk; short-circuits on first newer file.
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return false;
  }
  for (const name of entries) {
    const full = join(dir, name);
    let st;
    try {
      st = statSync(full);
    } catch {
      continue;
    }
    if (st.isDirectory()) {
      if (anyFileNewer(full, cutoff)) return true;
    } else if (st.mtimeMs > cutoff) {
      return true;
    }
  }
  return false;
}

function snapshot(cwd: string, trigger: string, sid?: string): void {
  const args = ["memory", "snapshot", `--trigger=${trigger}`];
  if (sid) args.push(`--session-id=${sid}`);
  try {
    const child = spawn("allmight", args, {
      cwd,
      stdio: "ignore",
      detached: true,
    });
    // Detach so the plugin returns immediately; the snapshot runs
    // in the background. unref() lets the parent exit independently.
    child.unref();
    child.on("error", () => {
      // allmight not on PATH or other spawn failure — silent.
    });
  } catch {
    // Best-effort: a plugin must never throw.
  }
}

export const MemoryHistoryPlugin: Plugin = async ({ directory }: any) => {
  const cwd = (directory as string | undefined) ?? process.cwd();

  return {
    "chat.message": async (input: any, _output: any) => {
      emitHeartbeat("memory-history", cwd);
      const sid = input?.sessionID;
      snapshot(cwd, "chat-message", sid);
      maybeMarkIngestPending(cwd);
      void _output;
    },

    "experimental.session.compacting": async (input: any, _output: any) => {
      emitHeartbeat("memory-history", cwd);
      const sid = input?.sessionID;
      snapshot(cwd, "session-compacting", sid);
      void _output;
    },

    event: async ({ event }: any) => {
      emitHeartbeat("memory-history", cwd);
      const type = String(event?.type ?? "");
      if (type === "session.deleted") {
        const sid = event?.properties?.sessionID;
        snapshot(cwd, "session-deleted", sid);
      }
    },
  };
};

export default MemoryHistoryPlugin;
"""
        return template.replace("__TS_HEARTBEAT_SNIPPET__", TS_HEARTBEAT_SNIPPET)

    def _claude_memory_history_hook_content(self) -> str:
        """Claude Code hook: mirror of ``memory-history.ts``.

        Reads JSON from stdin (the hook input), spawns ``allmight
        memory snapshot``, returns an empty hook output. Used as a
        ``Stop`` hook so it fires once per agent turn (the closest
        Claude Code analogue to OpenCode's ``chat.message``).
        """
        from ...core.plugin_telemetry import PY_HEARTBEAT_SNIPPET
        template = """\
#!/usr/bin/env python3
\"\"\"All-Might memory-history hook — Claude Code mirror of memory-history.ts.

Stop hook: spawns ``allmight memory snapshot`` after every agent
turn. Backs accidental-delete recovery via ``allmight memory
restore``. Errors are swallowed; the hook must never block.

The OpenCode sibling is ``.opencode/plugins/memory-history.ts``;
both surfaces call the same CLI so behaviour is identical.
\"\"\"
import json
import os
import subprocess
import sys
from pathlib import Path


__PY_HEARTBEAT_SNIPPET__

def _maybe_mark_ingest_pending(cwd):
    # L3 auto-ingest marker — see docs/plan.md work item C'. If any
    # journal entry is newer than `.allmight/last_ingest`, touch
    # `.allmight/ingest.pending` so the next SessionStart drain
    # triggers `allmight memory ingest --incremental`. Inline (no
    # all-might module import) so the hook stays self-contained.
    try:
        root = Path(cwd)
        last_ingest = root / ".allmight" / "last_ingest"
        cutoff = last_ingest.stat().st_mtime if last_ingest.exists() else 0.0
        personalities = root / "personalities"
        if not personalities.is_dir():
            return
        for journal_dir in personalities.glob("*/memory/journal"):
            for entry in journal_dir.rglob("*.md"):
                try:
                    if entry.stat().st_mtime > cutoff:
                        pending = root / ".allmight" / "ingest.pending"
                        pending.parent.mkdir(parents=True, exist_ok=True)
                        pending.touch()
                        return
                except OSError:
                    continue
    except OSError:
        pass  # hook must never block


def main() -> None:
    _hb("memory_history")
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    cwd = payload.get("cwd") or os.getcwd()
    sid = (payload.get("session_id") or "")[:32]

    args = ["allmight", "memory", "snapshot", "--trigger=stop-hook"]
    if sid:
        args.append(f"--session-id={sid}")

    try:
        subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError):
        # allmight not on PATH or spawn failed — silent. Recovery via
        # `allmight memory snapshot` by hand still works.
        pass

    _maybe_mark_ingest_pending(cwd)

    # Empty output means: don't block, no extra context to inject.
    print("{}")


if __name__ == "__main__":
    main()
"""
        return template.replace("__PY_HEARTBEAT_SNIPPET__", PY_HEARTBEAT_SNIPPET)

