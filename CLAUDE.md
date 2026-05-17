# All-Might Development

## After Code Changes

After modifying initializer, skill templates, commands, or memory init:

1. Run tests: `PYTHONPATH=src python -m pytest tests/`
2. If the change touches code that generates TypeScript (e.g. OpenCode
   plugins under
   `src/allmight/capabilities/memory/initializer.py::_opencode_plugin_map`),
   also type-check the generated output:
   `cd /tmp/demo && allmight init . && tsc --noEmit --skipLibCheck .opencode/plugins/*.ts`
   Python tests only verify strings written — they cannot catch
   wrong-shape API calls in the generated `.ts`.
3. **If the change touches an OpenCode plugin, the matching Claude
   Code hook MUST also be updated** (see *Editor Compatibility* below).
   The two surfaces share a behavioural contract; updating one and
   leaving the other stale is a regression even when tests pass.

## Planning Workflow

When the task requires designing before coding:

- **Write plan files incrementally to disk via the Edit tool.** Do
  not stream a long single-shot response. Stream-idle timeouts have
  lost whole plans before; write each section, save, then continue.
- **Confirm core premises before drafting.** Naming choices
  (Part D's `database` and `memory` *capabilities* vs. the
  deprecated `corpus_keeper` / `memory_keeper` template names) and
  non-negotiable rules — surface assumptions and ask for
  confirmation in 30 seconds, instead of redrafting after rejection.
- **Close every design session with a written artifact.** Plan
  files and CLAUDE.md additions both count; chat memory does not.

## Project Structure

```
All-Might/                          ← This repo (the framework)
├── src/allmight/                    ← Framework source code
│   ├── capabilities/                ← Built-in capability templates
│   │   ├── database/                ← knowledge-graph workspaces + /search /sync /onboard /one-for-all /all-for-one
│   │   └── memory/                  ← L1/L2/L3 agent memory + /remember (Record + Reflect) + /recall
│   ├── personalities/               ← Deprecation shim only — re-exports allmight.capabilities
│   ├── bridge/                      ← SMAK CLI subprocess wrapper (internal)
│   ├── config/                      ← config.yaml manager
│   ├── core/                        ← Domain models + capability framework
│   │   └── routing.py               ← ROUTING_PREAMBLE for command bodies
│   ├── enrichment/                  ← Enrichment policy (advisory)
│   ├── migrate/                     ← One-shot upgrader for pre-Part-C projects
│   ├── hub/                         ← Multi-workspace hub templates (deprecated)
│   └── cli.py                       ← CLI entry: init, add, list, clone, migrate, memory, share
├── tests/                           ← Test suite
└── docs/
```

## Key Files to Know

| File | What it generates |
|------|-------------------|
| `core/personalities.py` | Capability framework: Template (with `install` + optional `install_globals`), Personality, registry, `compose` (downward symlinks for personality-specific entries), `compose_agents_md`, `slugify_instance_name`, `role-load.ts` scaffold |
| `core/routing.py` | `ROUTING_PREAMBLE` prepended to every routed command body |
| `core/skill_io.py` | Shared `install_skill(root, name, description, skill_body, command_body=None)` — writes `.opencode/skills/<name>/SKILL.md` + optional `.opencode/commands/<name>.md` |
| `core/state.py` | Centralized `.allmight/*.yaml` I/O: `read_onboard` / `write_onboard` plus re-exports of `read_registry` / `write_registry` |
| `capabilities/database/__init__.py` | TEMPLATE with `_install_globals` (project-wide) + `_install` (per-personality); cli_options for --sos/--writable; default_instance_name = `knowledge` |
| `capabilities/database/initializer.py` | `initialize_globals(root, ...)` writes `.opencode/` skills/commands + `.allmight/mode`; `initialize(...)` adds per-personality `database/` workspace + ROLE.md |
| `capabilities/database/personality_suggestions.py` | Canonical suggestion catalog; `seed_suggestions(root)` writes the marker'd YAML files to `.allmight/suggestions/personalities/` |
| `capabilities/database/onboard_skill_content.py` | The `/onboard` skill body (~85 lines): one purpose question, match catalog, `allmight add` shell-out, default-personality callout |
| `capabilities/database/one_for_all_skill_content.py` | The `/one-for-all` skill body + command body (1 personality → 1 bundle, PII review, manifest with `derived_from` lineage) |
| `capabilities/database/all_for_one_skill_content.py` | The `/all-for-one` skill body + command body (N sources → 1 target, per-capability merge with dialog, ROLE.md prose reconciliation) |
| `capabilities/memory/__init__.py` | TEMPLATE with `_install_globals` + `_install`; no cli_options; default_instance_name = `memory` |
| `capabilities/memory/initializer.py` | `initialize_globals(root, ...)` writes root MEMORY.md + `.opencode/` commands+plugins + memory-history mirror; `initialize(...)` adds per-personality memory subtree |
| `capabilities/database/scanner.py` | Detects languages, frameworks, proposes indices |
| `migrate/migrator.py` | One-shot upgrader for pre-Part-C projects |

## Personality Platform Conventions (Part D)

These rules are non-negotiable; proposals that violate them have been
rejected before and will be rejected again.

- **A personality is a *role*, not a tool.** Personalities are
  user-defined (e.g. `stdcell_owner`, `pll_owner`,
  `code_reviewer`); the framework provides **capabilities**
  (`database`, `memory`) which a personality can opt into. The
  legacy names `corpus_keeper` / `memory_keeper` were renamed to
  `database` / `memory` and are deprecated. The legacy
  `detroit_smak` is also deprecated — do not re-introduce.
- **One global slash-command surface.** Every project has exactly
  one `.opencode/commands/`, one `.opencode/skills/`, one
  `.opencode/plugins/`. No per-personality command namespacing.
  Capability templates write the globals **once** into `.opencode/`
  on install — not into per-instance copies. The agent decides
  which personality to act for from conversation context plus the
  `> **Default personality**: <name>` callout in `MEMORY.md`.
- **Generic command bodies.** No emitted body may contain a
  literal personality name. The placeholder is
  `personalities/<active>/<capability>/...` and the leading
  ``ROUTING_PREAMBLE`` (`core/routing.py`) teaches the agent how
  to resolve `<active>`. Pinned by
  `tests/test_command_body_generic.py` and
  `tests/test_routing_preamble.py`.
- **Compose direction is downward.** Each personality dir holds
  real, initially empty `commands/` and `skills/` subdirs (the
  agent may write personality-specific entries at runtime).
  ``compose()`` projects every per-personality entry into
  `.opencode/<kind>/<basename>` as a relative symlink so OpenCode
  picks it up. The opposite (upward symlinks
  `personalities/<p>/commands → ../../.opencode/commands`) was
  briefly tried in commit 5 and reverted — every personality
  aliasing the same global set defeats the per-personality slot.
- **Plugins are project-wide.** `_COMPOSED_KINDS = ("skills",
  "commands")` — `plugins/` is intentionally **not** projected
  per-personality. Plugins are global hooks; they iterate
  `personalities/*/memory/` at runtime to find the right data dir.
- **Two-tier model.** Every capability is a `PersonalityTemplate`
  (the *kind* — registered as a module-level `TEMPLATE` constant
  inside `src/allmight/capabilities/<name>/__init__.py`) plus
  zero-or-more `Personality` instances. The framework
  instantiates the instance; the template never instantiates itself.
  A single personality can hold multiple capabilities
  (``capabilities=[...]`` on the `Personality` dataclass).
- **No Composer pattern.** Templates do not mix runtime state
  across capabilities, do not share helpers via mutable globals,
  and do not coordinate at install time. Each `template.install`
  runs in isolation and writes only its share. If two templates
  need the same data, they each compute it from `InstallContext`;
  cross-capability state flows through the file system, never
  through process memory.
- **One root `AGENTS.md`, composed from per-personality `ROLE.md`.**
  `compose_agents_md` stitches every personality's ROLE.md into
  the single root `AGENTS.md`. The scaffold-owned `role-load.ts`
  plugin re-injects each ROLE.md at every `chat.message` for an
  un-primed session — same pattern as `memory-load.ts` keeping
  `MEMORY.md` warm after compaction.
- **Two-stage bootstrap (Track A).** `allmight init` is a CLI
  scaffold — no personality is created at install time. It writes
  `.opencode/` globals, `AGENTS.md`, `MEMORY.md`, an empty registry,
  and seeds a suggestion catalog at
  `.allmight/suggestions/personalities/*.yaml` (a stable home,
  distinct from `.allmight/templates/` which is `/sync` re-init
  staging). The agent-side `/onboard` skill (owned by `database`)
  handles the personality-decision phase: asks the user about
  purpose, matches against suggestions, and calls `allmight add
  <name> --capabilities <list>` once per chosen suggestion so
  ROLE.md, the marker, the capability table, and the registry row
  are written deterministically by Python — never by the agent
  free-form. Multi-personality stays first-class — `/onboard` can
  create one or many. The fallback when the user has no specific
  purpose is the `general` suggestion (database + memory).
- **`/reflect` is folded into `/remember`.** The `/remember.md`
  body has two top-level sections (`# Record` and `# Reflect`);
  the agent picks based on trigger context. Do not re-introduce
  a separate `/reflect` command.
- **Personality transfer is themed One For All / All For One.**
  Cross-project moves go through two agent-driven surfaces:
  - `/one-for-all` (skill, with PII review) — bundle a single
    personality outward (1 → 1). Writes a directory bundle with
    `manifest.yaml` (including a `derived_from` lineage list),
    `ROLE.md`, and per-capability data dirs minus `store/`.
  - `/all-for-one` (skill, with per-file dialog) — absorb N sources
    (bundles or in-project personalities) into 1 target (new or
    existing). Owns all merge semantics: `database/` workspace name
    clashes, `memory/understanding/` overwrites, `memory/journal/`
    append + dedupe, ROLE.md prose reconciliation. Records every
    source in the target's `derived_from` registry list.

  The standalone `allmight import` CLI was removed in Track C — it
  was a mechanical single-bundle path that the agent skills now
  cover. `allmight share pull <git-url>` still installs single
  bundles when they arrive over a git remote (using the internal
  `cli._import_bundle` helper).

  Do not re-introduce `allmight import`, `allmight merge`, a CLI
  `--force` overwrite, or a separate `/export` / `/import` skill
  pair — the OFA / AFO asymmetry is the design.

## Architecture Layers

| Layer | What | For whom |
|-------|------|----------|
| README.md | How to talk to the agent | Human |
| AGENTS.md (in workspace) | What capabilities exist | Agent (high-level) |
| Skills/Commands | How to execute operations (smak CLI) | Agent (low-level) |
| CLI | `init`, `add`, `list`, `clone`, `migrate`, `memory`, `share` | Human (bootstrap + lifecycle) |

---

## Memory Layer Strategy

The `memory` capability stores three tiers with **different loading
strategies per tier**. Mixing them up produces token explosions or
stale results.

| Tier | Storage | Loading strategy | Why this tier, not another |
|------|---------|------------------|----------------------------|
| **L1** `MEMORY.md` | Project root | Always in context (memory-load hook injects every session start + post-compaction) | It *is* the project-wide truth; searching it makes no sense |
| **L2** `personalities/<p>/memory/understanding/` | Per-personality | **TOC + on-demand single-file read** via `understanding/_index.md` | Structured knowledge; narrative integrity matters; RAG chunking fragments meaning |
| **L3** `personalities/<p>/memory/journal/` | Per-personality | **SMAK vector search** invoked by `/recall` | Append-only, unbounded growth, narrative-weak — RAG is the right primitive |

### L3 auto-ingest closure

`/recall` is only as useful as the SMAK index is fresh. Manual
`smak ingest` is unreliable — agents forget. The closure:

1. `memory-history.ts` Stop hook (per turn) — if any journal file is
   newer than `.allmight/ingest.pending`, touch the marker. Cheap
   (≤10 ms); never runs the embedder on the hot path.
2. `memory-load.ts` `session.created` handler — if the marker exists,
   spawn `smak ingest --incremental` async and clear the marker on
   success.

Trade-off: same-session `/recall` may miss the just-written entry
(acceptable — the agent still has it in context). Next session sees
the indexed version. Embedding cost (5–30 s) never blocks a turn.

### Non-goals (locked decisions — see `docs/plan.md`)

- **No L2 RAG until L2 demonstrably crosses ~200 files** for any
  single personality. The L2 TOC mechanism keeps the same access
  pattern viable up to that scale. Proposing L2 embedding before
  that threshold regresses on a decision already made — point
  the proposer at `docs/plan.md` first.
- **No SQLite memory store** (pro-workflow's choice). YAML + git
  mirror keeps memory human-readable, diff-able, and recoverable.
  SMAK provides the vector layer where it is justified (L3 only).
- **No `/distill` slash command.** Incremental pattern detection is
  folded into `/remember#Record`. Batch distillation, if ever
  needed, becomes a CLI (`allmight memory distill`) that calls the
  Claude API directly — out of the agent's context window entirely.

---

## Editor Compatibility

`.opencode/` is the canonical agent surface; `.claude/` is a
**generated mirror** so a single `allmight init` produces a project
both OpenCode and Claude Code can drive without forking source of
truth. The mirror has three layers, each with a different sync model:

| Asset | Source of truth | Mirror | Sync model |
|---|---|---|---|
| Slash commands | `.opencode/commands/*.md` | `.claude/commands` (dir symlink) | Symlink — adding a new command is automatically visible on both sides |
| Skills | `.opencode/skills/<name>/` | `.claude/skills` (dir symlink) | Same |
| Agent context | `AGENTS.md`, `MEMORY.md`, `personalities/*/ROLE.md` | root `CLAUDE.md` (`@`-import shim) | Single set of files, both editors read |
| Runtime hooks | `.opencode/plugins/*.ts` | `.claude/hooks/*.py` + `.claude/settings.json` | **Hand-mirrored** — updates to one require updates to the other |
| Per-personality subagents | `personalities/<name>/ROLE.md` | `.opencode/agents/<name>.md` (pointer with `prompt: "{file:…}"`) | **OpenCode-only.** Claude Code's subagent format differs; not mirrored yet. |

The bridge is wired by `src/allmight/core/claude_bridge.py`
(project-level pieces: root `CLAUDE.md`, dir symlinks, settings.json,
`role_load.py`, `reflection.py`) plus per-capability hook scripts (e.g.
`MemoryInitializer._claude_memory_load_hook_content` mirroring
`memory-load.ts`). The personality-subagent projection lives in
`core/personalities.py::compose_role_agents`.

### Personality subagents (`.opencode/agents/<name>.md`)

Each personality is exposed to OpenCode as a **subagent** so the
user can `@<name>` mention it from any conversation without
Tab-switching out of their main session. The generated file is a
thin pointer:

```yaml
---
description: "<role_summary>"
mode: subagent
prompt: "{file:../personalities/<name>/ROLE.md}"
---
<!-- all-might generated -->
```

This keeps `ROLE.md` as the single source of truth — editing
`personalities/<name>/ROLE.md` changes the agent's behaviour
without re-running `allmight init`.

Why `mode: subagent` (not `primary`):

- Primary agents are session-level — the user `Tab`-switches to one
  and the whole conversation becomes that agent. That fights All-
  Might's "no default personality switching" UX.
- Subagents are `@`-mentioned for one task at a time; the user's
  main conversation persists.

The directory is `.opencode/agents/` (plural). Singular `agent/` is
also accepted by OpenCode for backwards compatibility, but plural
is canonical.

On re-init: `compose_role_agents` rewrites all-might-owned agent
files in place; a user-customised file (without our marker) is
preserved and the fresh template is staged at
`.allmight/templates/agents/<name>.md` for `/sync` to merge.

### Dual-platform invariant for plugin/hook changes

When you change an OpenCode plugin, the Claude Code hook script that
mirrors it **must** be updated in the same commit:

| OpenCode plugin (`.ts`) | Claude Code hook (`.py`) |
|---|---|
| `memory-load.ts` | `memory_load.py` (in `MemoryInitializer`) |
| `memory-history.ts` | `memory_history.py` (in `MemoryInitializer`) — `Stop` hook |
| `role-load.ts` | `role_load.py` (in `core.claude_bridge`) |
| `reflection.ts` | `reflection.py` (in `core.claude_bridge`) — `UserPromptSubmit` hook |
| `remember-trigger.ts` | *(not yet mirrored — see TODO in claude_bridge)* |
| `usage-logger.ts` | *(not yet mirrored)* |
| `trajectory-writer.ts` | *(not yet mirrored)* |

The two scripts are not generated from a shared template; each is
hand-authored in its native language because the runtime contracts
differ (TS plugin returns objects mutating chat parts; Claude Code
hook reads JSON from stdin and prints JSON to stdout). The
behavioural equivalence is enforced by:

- `tests/test_claude_bridge.py::TestHooksRunCleanly` — runs each
  generated hook end-to-end and asserts the JSON output shape.
- `tests/test_memory_init.py::test_writes_claude_memory_load_hook` —
  pins the memory-load hook content alongside its OpenCode sibling.

If you skip the dual update, the OpenCode and Claude Code surfaces
will silently drift, and bug reports will look like "behaviour
depends on which editor I open the project with" — by the time
anyone notices, several plugin generations may be stale.

**Forward note.** The hand-maintained table above is today's source
of truth. Work item A' in `docs/plan.md` replaces it with a
declarative `PLUGIN_MANIFEST` in
`src/allmight/core/plugin_telemetry.py` — each plugin declares the
platform capabilities it requires, and the manifest decides whether
a Claude Code mirror is possible at all (some OpenCode capabilities
like `session.idle` have no Claude Code equivalent — those plugins
stay OC-only by design, **not** as a TODO). Until the manifest
lands, every plugin add/remove must update both this table *and*
`KNOWN_OPENCODE_PLUGINS` / `KNOWN_CLAUDE_HOOKS`.

### Plugin observability (heartbeats)

Every plugin / hook touches a marker file when it fires:

```
.allmight/plugins/heartbeats/oc/<plugin-basename>   # OpenCode .ts
.allmight/plugins/heartbeats/cc/<hook-basename>     # Claude Code .py
```

`allmight plugin status` reads these markers and prints last-fired
mtimes per surface. Plugins that have never fired show
`never fired` — the signal to investigate.

The two snippets that emit heartbeats live in
`src/allmight/core/plugin_telemetry.py` as `TS_HEARTBEAT_SNIPPET`
(inlined into every generated `.ts` plugin) and `PY_HEARTBEAT_SNIPPET`
(inlined into every generated Claude `.py` hook). When you add a new
plugin or hook:

1. Inline the matching snippet near the top of the generated file.
2. Call `emitHeartbeat("<name>", cwd)` (TS) or `_hb("<name>")` (Python)
   inside every top-level event handler / hook entry point.
3. Register the name in `KNOWN_OPENCODE_PLUGINS` or
   `KNOWN_CLAUDE_HOOKS` in `core/plugin_telemetry.py` so `plugin
   status` lists it explicitly (even before its first fire).

The design rationale and the **plugin-reduction plan** (which existing
plugins are likely to be deleted, reduced, or rewired once we have
heartbeat data) live in `docs/plugin-observability.md`. Read it before
proposing structured / JSONL telemetry — touch-file simplicity is
deliberate.

### Interaction with `oh-my-opencode` (OMO)

OMO 4.x ships a built-in hook called `claude-code-hooks` that scans
`.claude/settings.json` and re-runs every Claude Code hook from
**inside OpenCode** on equivalent OpenCode lifecycle events. For an
All-Might project this is doubly broken:

1. **Duplicate fire.** We already emit OpenCode-native plugins
   (`memory-history.ts`, `memory-load.ts`, `reflection.ts`,
   `role-load.ts`) for every Claude hook we mirror, so the bridge
   makes each one fire twice.
2. **Failure cascade.** If anything in `.claude/settings.json` points
   at a hook script that does not exist (which used to happen on
   re-init — see the regression test
   `test_reinit_staging_path_still_writes_claude_hooks`), OMO
   honours Claude Code's "Stop hook with exit ≠ 0 injects stderr as
   next user prompt" semantics. The error text gets fed back into
   the next turn with no chance to cancel.

We deliberately do **not** auto-write `.opencode/oh-my-opencode.json`
into the init scaffold to disable the bridge — touching a
third-party tool's config from inside our init is overreach.
Affected users add it themselves at the project level:

```json
{
  "disabled_hooks": ["claude-code-hooks"]
}
```

When the dual-platform invariant tempts someone to skip writing a
Claude hook ("we have an OpenCode plugin, isn't that enough?"), this
interaction is the reason the answer is still no. The Claude side
must always exist as a real, executable file with our marker —
that's what makes OMO's mirror harmless instead of fatal.

---

## Design Philosophy

### 1. What All-Might Generates (Target Workspace Structure)

An All-Might project holds **one or more personalities**, each with
**one or more capabilities** opted in. The personality dir holds
`ROLE.md` plus per-capability data dirs (`database/`, `memory/`)
plus initially-empty `commands/` and `skills/` slots. The
project-wide `.opencode/` holds the **globals** — search.md,
remember.md, the role-load plugin — plus downward symlinks for any
personality-specific entries.

Example with 3 EDA-flow personalities:

```
my-chip-project/                          ← One All-Might project
├── AGENTS.md                             ← composed from each ROLE.md
├── MEMORY.md                             ← project map + > **Default personality**: ... callout
│
├── .opencode/                            ← project-wide
│   ├── opencode.json                     ← $schema only (init scaffold)
│   ├── package.json                      ← @opencode-ai/plugin (init scaffold)
│   ├── skills/
│   │   ├── onboard/SKILL.md              ← real file (capability-written)
│   │   ├── one-for-all/SKILL.md
│   │   ├── all-for-one/SKILL.md
│   │   └── sync/SKILL.md
│   ├── commands/
│   │   ├── search.md                     ← real file (capability global)
│   │   ├── remember.md
│   │   ├── recall.md
│   │   ├── onboard.md
│   │   ├── one-for-all.md
│   │   ├── all-for-one.md
│   │   ├── sync.md
│   │   └── stdcell-special.md            ← downward symlink → personalities/stdcell_owner/commands/...
│   └── plugins/{role-load,reflection,memory-load,memory-history,remember-trigger,todo-curator,trajectory-writer,usage-logger}.ts
│
├── personalities/
│   ├── stdcell_owner/
│   │   ├── ROLE.md
│   │   ├── commands/                     ← real, empty initially; agent may add custom commands here
│   │   ├── skills/                       ← same
│   │   ├── database/                     ← per-personality SMAK workspaces
│   │   │   ├── stdcell/{config.yaml, store/}
│   │   │   └── pll/{config.yaml, store/}
│   │   └── memory/
│   │       ├── config.yaml
│   │       ├── smak_config.yaml
│   │       ├── understanding/{stdcell.md, pll.md}    ← L2
│   │       ├── journal/{stdcell/, general/}          ← L3
│   │       └── store/                                  ← L3 SMAK vector index
│   ├── pll_owner/
│   └── code_reviewer/                    ← only memory capability — no database/
│
└── .allmight/
    ├── personalities.yaml                ← Records installed personalities (Part-D shape)
    ├── onboard.yaml                      ← What `/onboard` should classify
    ├── templates/                        ← Re-init staging (when applicable)
    └── memory-history/                   ← Local git mirror tracking memory data
        ├── .git/                         ← Bookkeeping (separate from project's main .git)
        ├── .gitignore                    ← Excludes store/ (SMAK vector indices)
        ├── MEMORY.md                     ← Mirror of project-root MEMORY.md
        └── personalities/<name>/         ← Mirror of ROLE.md + memory data + database config.yaml
```

**SMAK indexes source files in-place** — no files are ever copied
into the All-Might project. Only the vector index (`store/`) and
SMAK config (`config.yaml`) live inside each personality's
`database/` workspaces.

**Sidecar files** (`.sidecar.yaml`) live beside the source code
they describe (at `$DDI_ROOT_PATH/...`), NOT inside the All-Might
project.

**Memory recovery** — every memory write is auto-snapshotted into
`.allmight/memory-history/.git` by the post-turn hook
(`memory-history.ts` / `memory_history.py`). Accidentally deleted
or overwritten data is recoverable via `allmight memory log` +
`allmight memory restore <file> [--rev <sha>]`. SMAK vector
indices (`store/`) are excluded from the mirror — they're
rebuildable out-of-band via the `smak ingest` CLI. The mirror's
`.git` is separate from the project's main `.git` so neither side
sees the other in `git status`.

`allmight init` is **idempotent and safe in pre-populated
directories.** Files that carry an All-Might marker
(`ALLMIGHT_MARKER_MD`, `_TS`, `_YAML`) are auto-replaced; files you
authored at e.g. `.opencode/commands/search.md` are preserved
untouched and surfaced via `.allmight/templates/conflicts.yaml`
for `/sync` to resolve.

### 2. SRP: Three Layers of Agent Documentation

| Layer | Audience | Abstraction | Contains |
|-------|----------|-------------|----------|
| **AGENTS.md** | Agent | High-level WHAT | Capabilities, commands, "see skill for details" |
| **Skills/Commands** | Agent | Low-level HOW | SMAK CLI commands, YAML schemas, troubleshooting |
| **README.md** | Human | Conversational | "Tell the agent to search for..." |

- **AGENTS.md** knows about `/search` but NOT about `smak search --config ...`
- **Skills** know about SMAK internals but never expose them to the human user
- **README.md** doesn't mention SMAK, sidecars, or YAML — only natural-language examples

### 3. config.yaml: Only SMAK Owns It

There is **no All-Might-level config.yaml**. Workspaces are
discovered by scanning
`personalities/<p>/database/*/config.yaml` — no registry needed
for workspaces. (Personalities are recorded in
`.allmight/personalities.yaml` so `allmight list` knows what's
installed.)

### 4. Shared vs Per-Personality vs Per-Workspace

| Component | Scope | Why |
|-----------|-------|-----|
| `MEMORY.md` | Project-wide root | L1 cache: project map, default-personality callout, user prefs (plugin-loaded) |
| `AGENTS.md` | Project-wide root | High-level WHAT the agent can do |
| `.opencode/{commands,skills,plugins}/` | Project-wide globals | Capability-written; one set per project |
| `personalities/<p>/{commands,skills}/` | Per-personality | Real empty slots for personality-specific entries; projected into `.opencode/` via downward symlinks by `compose` |
| `personalities/<p>/database/` | Per-personality | Knowledge-graph workspaces |
| `personalities/<p>/memory/` | Per-personality | L2 understanding + L3 journal + SMAK store |
| `personalities/<p>/database/<ws>/{config.yaml,store/}` | Per-workspace | Each SMAK workspace has its own index config + data |
| `.allmight/personalities.yaml` | Project-wide | Lists installed personalities (Part-D shape: `name` + `capabilities` + `versions`) |
| Sidecar files | Per-source-file | Live beside source code (external) |

### 5. CLI Surface (Part D)

```
allmight init [--yes] [path]                       Scaffold-only: writes globals + suggestion catalog. NO personality created at install time — /onboard handles that.
allmight add <name> [--capabilities a,b,c]         Add a personality with the requested capability subset. Called by /onboard for each chosen suggestion.
allmight list                                      Print a table of installed personalities.
allmight clone <source>                            Read-only clone with symlinked database/.
allmight migrate                                   One-shot upgrade for pre-Part-C projects.
allmight memory init / memory export               Memory-specific lifecycle.
allmight memory snapshot / log / diff / restore / gc   Memory version-control mirror (recovery from accidental edits / deletes).
allmight share publish / pull                      Push or pull personality bundles via a git remote.
```

**`/one-for-all` and `/all-for-one` are skills, not CLI commands.**
Export (one-for-all) is agent-driven because it needs PII review
and per-file consent. Merge (all-for-one) is agent-driven because
it needs per-file conflict dialog and ROLE.md prose reconciliation
that no CLI flag can capture. The standalone `allmight import` CLI
was removed in Track C; bundles arriving over a git remote install
via `allmight share pull` (which calls the internal
`cli._import_bundle` helper).

The agent calls `smak` CLI directly (taught by skills), NOT
`allmight` wrappers.

**`cli.py` knows nothing template-specific.** Per-template flags
(`--sos`, `--writable`) are contributed by their template's
`cli_options` and registered on the `init` Click command at startup.
Each template extracts what it needs from `Personality.options`
inside its `install` callable — `cli.py` never reads them. To add a
flag: append a `CliOption(...)` to the right template's
`__init__.py` and it shows up in `allmight init --help`
automatically.

---

## Interface Isolation & Clean-Code Rules

Each rule below is enforceable by reading a diff. Violating a rule
is a regression even if tests pass.

- **`cli.py` is closed against templates.** Touching
  `src/allmight/cli.py` to special-case a template is a regression.
  New flags belong in `template.cli_options`; new install
  behaviour belongs in `template.install`. The only universal
  concerns that live there are `--force`, scaffold writing
  (`write_init_scaffold`), registry persistence
  (`write_registry`), and the lifecycle commands (`init`, `add`,
  `list`, `import`, etc.).
- **`core/` is closed against templates.** Files under
  `src/allmight/core/` must not import from
  `src/allmight/capabilities/*`. The dependency arrow points one
  way: templates depend on core, never the other direction.
- **A capability template owns its directory, nothing else.**
  Writes outside `personalities/<name>/` are limited to four root
  targets: `AGENTS.md`, `MEMORY.md`, the project-wide
  `.opencode/<kind>/` (one set per project), and the staging
  directory `.allmight/templates/...`. Composition symlinks under
  `.opencode/<kind>/<basename>` for personality-specific entries
  are placed by `core.personalities.compose`, not by the template
  itself. Any new write target must be an explicit, documented
  exception in this section.
- **Conflict resolution lives in `core/personalities.compose`.**
  Templates do not detect or stage their own conflicts; they
  declare what they want to write inside their share.
  Centralising this keeps `/sync`'s mental model uniform — one
  manifest at `.allmight/templates/conflicts.yaml`, one set of
  resolution rules.
- **Markers are the contract for "this file is mine".** Every
  generated file *must* carry an `ALLMIGHT_MARKER_*` token (see
  `core/markers.py`). Files without a marker are treated as
  user-authored on re-init and preserved. **Skipping the marker
  is a silent data-loss bug** — the file gets clobbered or, worse,
  silently divorced from re-init flow.
- **When in doubt: add a flag, not a capability.** A new capability
  is justified only when it has its own data dir, its own
  skills/commands, and a meaningful uninstall semantics.
  Otherwise, extend an existing template's `cli_options` or its
  `install` logic. The bar for new capabilities is high because
  each one introduces new symlinks, new entries in
  `personalities.yaml`, and a new directory under each
  personality.

---

## Discipline When Generating Third-Party Integrations

The initializer writes files that execute in foreign runtimes
(OpenCode plugins, MCP servers, CI configs). The Python test suite
verifies **what strings we wrote**, not **whether the file works
at runtime** — so string-presence assertions can pass while the
generated code is silently broken. Rules below came from real
regressions; break them and the same bugs come back.

- **Read a working example's source before writing.** Doc summaries
  hide signatures. For an OpenCode plugin, read a published one on
  GitHub (`oh-my-opencode`, `opencode-supermemory`) and the
  `@opencode-ai/plugin` type definitions — not a blog post.
- **Distinguish event subscription from hook registration.** OpenCode
  has two separate mechanisms: the global `event:` handler observes
  the bus; top-level keys like `"chat.message"` and
  `"experimental.session.compacting"` are **hooks with input/output
  contracts**. Never place a hook name inside the event handler's
  if-chain.
- **Tests must include negative assertions.** `assert "chat.message"
  in content` is useless on its own. Assert the exact signature
  (`'"chat.message": async (input: any, output: any)'`), the
  correct injection path (`output.parts.unshift`), and the absence
  of the broken shape (`"msg.content =" not in content`).
- **Type-check generated TypeScript at least once** (see *After
  Code Changes* above). A one-shot `tsc --noEmit --skipLibCheck`
  catches wrong-shape calls the Python suite cannot see.
- **If official docs are unreachable (403/404/503), say so
  explicitly** and fetch a real implementation from GitHub. Do not
  silently degrade to secondary sources and pretend the shape was
  verified.
- **Verify the API on one file before propagating to many.** If
  three files share an unverified assumption, they break together
  — and the tests pass in all three.
