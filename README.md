# All-Might

All-Might is a role-centric agent harness. You define the **roles**
that matter to your project — personalities like `stdcell_owner`,
`pll_owner`, `code_reviewer` — and pick which **capabilities** each
one needs. The framework provides two capabilities today:

* **`database`** — turns the project's source into a searchable
  knowledge graph (`/search`, sidecar annotations).
* **`memory`** — keeps cross-session memory (`/remember`, `/recall`,
  per-personality `understanding/` + `journal/`).

A personality opts into either or both. `code_reviewer` with only
`memory` and no `database` is a first-class shape — All-Might is not
just for codebase indexing.

All personalities share **one** flat slash-command surface
(`/onboard`, `/search`, `/remember`, `/recall`, `/recover`,
`/one-for-all`, `/all-for-one`, `/sync`). The agent decides which
personality to act for from conversation context plus the
`> **Default personality**: <name>` hint at the top of `MEMORY.md`.

## Setup

```bash
pip install allmight
cd /path/to/my-chip-project
allmight init .
```

`allmight init` is **scaffold-only**. It writes:

* `.opencode/` — the global slash-command surface (commands, skills,
  plugins, per-personality subagent pointers)
* `.claude/` — a Claude Code mirror (directory symlinks + Python
  hooks + `settings.json`) pointing at the same content
* `AGENTS.md` (framework primer for the agent), `MEMORY.md`, root
  `CLAUDE.md` shim
* `.allmight/personalities.yaml` (empty registry) +
  `.allmight/suggestions/personalities/*.yaml` (suggestion catalog
  that `/onboard` reads from)

**It does not create any personality.** That step is agent-driven:

Open the project in **Claude Code** or **OpenCode** and run
`/onboard`. The agent walks the suggestion catalog, asks what you
want to use this project for, and shells out to
`allmight add <name> --capabilities <list>` once per chosen
personality. `ROLE.md`, the capability table, and the registry row
are written deterministically by `allmight add` — the agent does not
free-form them.

## Adding more personalities

```bash
allmight add stdcell_owner --capabilities database,memory
allmight add pll_owner     --capabilities database,memory
allmight add code_reviewer --capabilities memory     # no database
```

`--capabilities` is a comma-separated list. Omit it to install every
available capability. `code_reviewer` above is created with only the
`memory` capability — no `database/` data dir, no `/search` against
its corpus.

```bash
allmight list
# Personality    Capabilities      Version
# stdcell_owner  database, memory  1.0.0
# pll_owner      database, memory  1.0.0
# code_reviewer  memory            1.0.0
```

## Project layout

```
my-chip-project/
├── AGENTS.md                            ← framework primer + composed ROLE.md
├── MEMORY.md                            ← project map + default-personality hint
├── CLAUDE.md                            ← @-import shim → AGENTS.md + MEMORY.md
├── .opencode/                           ← canonical agent surface
│   ├── commands/                        ← /search, /remember, /recall, …
│   ├── plugins/                         ← role-load, memory-load, memory-history, …
│   ├── skills/                          ← /onboard, /one-for-all, /all-for-one, /sync, /recover
│   └── agents/<name>.md                 ← OpenCode subagent pointer per personality
├── .claude/                             ← generated mirror
│   ├── commands → ../.opencode/commands
│   ├── skills   → ../.opencode/skills
│   ├── hooks/                           ← *.py mirrors of .opencode/plugins/*.ts
│   └── settings.json                    ← hook registrations
├── personalities/
│   ├── stdcell_owner/
│   │   ├── ROLE.md
│   │   ├── commands/                    ← initially empty; for personality-specific commands
│   │   ├── skills/                      ← same
│   │   ├── database/                    ← knowledge-graph workspaces (if capability opted in)
│   │   └── memory/                      ← per-personality journal + understanding
│   ├── pll_owner/
│   └── code_reviewer/                   ← no database/ — only memory was opted in
└── .allmight/
    ├── personalities.yaml               ← Part-D registry (what `allmight list` reads)
    ├── suggestions/personalities/       ← /onboard proposal catalog
    ├── templates/                       ← re-init staging (/sync resolves)
    ├── memory-history/.git/             ← recovery snapshots (separate git)
    ├── plugins/heartbeats/{oc,cc}/      ← plugin observability markers
    ├── onboard.yaml                     ← /onboard state
    ├── upstream.yaml                    ← share publish/pull bookkeeping
    └── mode                             ← agent-surface mode marker (`read-only`)
```

The agent surface (`.opencode/commands/`, `.opencode/skills/`,
`.opencode/plugins/`) lives **once** at project level. Each
personality has its own `commands/` and `skills/` slot where the
agent can add personality-specific entries; those are projected back
into `.opencode/` so OpenCode discovers them from a single scan.

## The `.allmight/` directory

| Path | Written by | What it's for |
|------|------------|---------------|
| `personalities.yaml` | `allmight add` / `allmight init` | Registry: name + capabilities + versions + lineage per personality. `allmight list` reads this. |
| `suggestions/personalities/*.yaml` | `allmight init` (seeded) | Catalog `/onboard` reads to propose personalities. |
| `templates/` | re-run of `allmight init` | Staging for new framework templates. `/sync` resolves. |
| `memory-history/.git/` | post-turn hook | Local git mirror of memory data (separate from project's main `.git`). Source for `/recover` and `allmight memory restore`. |
| `plugins/heartbeats/{oc,cc}/` | every plugin / hook | Touch-file on each fire; `allmight plugin status` reads. |
| `onboard.yaml` | `/onboard` | Captured purpose / chosen personalities; preserved across re-init. |
| `upstream.yaml` | `allmight share publish` / `pull` | Per-personality remote URL + last bundle id. |
| `mode` | `allmight init` | Agent-surface mode marker. |

## Talking to the agent

```text
> Search the stdcell rtl for setup-time violations.
> Remember that the PLL lock-time spec is 50 µs.
> What did we decide last week about the io_phy retiming?
```

The agent reads `MEMORY.md`'s project map (one row per personality),
picks the right personality from your phrasing, and runs the matching
command against that personality's data dir.

### Pinning a default personality

Add this line to the top of `MEMORY.md` to set the active personality
when conversation context is ambiguous:

```markdown
> **Default personality**: stdcell_owner
```

`/onboard` writes this for you when more than one personality exists.
Edit by hand only when you want to override.

### `@<name>` — subagents

Every personality is also exposed as an OpenCode subagent at
`.opencode/agents/<name>.md`. You can `@stdcell_owner search for
setup-time violations` from any conversation to invoke just that
personality for one task — no Tab-switch. The agent pointer is a
thin file; `ROLE.md` remains the source of truth for behaviour.

## Commands

| Command   | Plain English |
|-----------|---------------|
| `/onboard`  | Capture each personality's role and (if 2+ personalities) pick the default. Run once after `allmight init`. |
| `/search`   | "Search for ..." |
| `/remember` | "Remember that ..." — **Record** (write a new memory) or **Reflect** (review/condense existing memory), picked by trigger context |
| `/recall`   | "What do you know about ...?" |
| `/recover`  | "Get back what I just deleted" — agent walks you through picking the right snapshot from `.allmight/memory-history/` and restores it |
| `/one-for-all` | "Export `<name>` so I can share it" — agent applies per-capability rules and reviews for PII (1 personality → 1 bundle) |
| `/all-for-one` | "Merge these into one personality" — fold multiple bundles or in-project personalities into one target (N → 1) with per-file dialog |
| `/sync`     | Merge staged template updates after re-init / resolve compose conflicts |

The `database` capability is **search-only** from the agent surface
— no slash command mutates a corpus. `memory` is written via
`/remember`. Index builds and sidecar edits happen out-of-band via
the `smak` CLI.

## Sharing personalities between projects

Two skills handle cross-project transfer. **`/one-for-all`** exports
one personality outward (1 → 1); **`/all-for-one`** absorbs sources
into one personality (N → 1). There is no standalone `allmight
import` CLI — single bundles arrive over a git remote via
`allmight share pull`, and the merge case is agent-driven through
`/all-for-one`.

### Export: `/one-for-all`

The agent walks the personality's data, applies per-capability rules,
reviews every file for likely PII, and asks for consent on sensitive
content before writing a directory bundle:

```
stdcell_owner-export/
├── manifest.yaml                   ← allmight version + capabilities + lineage
├── ROLE.md
├── database/
│   └── config.yaml                 ← (no store/ — vector index is rebuilt)
└── memory/
    ├── understanding/              ← only files that passed PII review
    └── journal/                    ← only if the user opted in
```

`store/` is never bundled — the receiver rebuilds the SMAK index
out-of-band (via `smak ingest`) after import.

### Merge / absorb: `/all-for-one`

Run this skill in the agent when you want to:

- Combine multiple bundles into one personality
- Fold a bundle into an existing personality
- Consolidate two in-project personalities (`stdcell_owner` +
  `pll_owner` → `eda_owner`) — sources don't have to be bundles

The agent walks per-capability merge rules: workspace-name clashes,
`memory/understanding/` overwrites, `memory/journal/` append + dedupe,
`ROLE.md` prose reconciliation. Each conflict is resolved with a
short dialog. By default the source personalities are kept after the
merge (the agent asks before removing them). Lineage from every
source is recorded in the target's `derived_from` list.

After any merge or share pull, rebuild SMAK indices for the affected
workspaces out-of-band via the `smak ingest` CLI.

### Bundle manifest

Each bundle carries a `manifest.yaml` with the shape below
(full schema lives in the `/one-for-all` skill):

```yaml
allmight_version: "<package version>"
schema_version: 3
personality_name: stdcell_owner
bundle_id: <fresh uuid4>                # regenerated at every export
bundle_version: 0.1.0                   # semver of THIS bundle's content
derived_from:                           # lineage — accumulates across merges
  - kind: bundle
    bundle_id: <prior_bundle_id>
    bundle_version: <prior_version>
  - kind: personality                   # in-project source folded by /all-for-one
    name: <source_personality_name>
capabilities:
  database: {capability_version: 1.0.0}
  memory:   {capability_version: 1.0.0}
exported_at: "<iso-8601>"
database_subscriptions:                 # optional; NFS-hosted SMAK indices
  - index: stdcell
    nfs_path: /nfs/team/smak/stdcell
    required: true                      # warn (not block) if missing on receiver
```

`derived_from` grows every time `/all-for-one` folds a new source in;
`database_subscriptions` warns the receiver if a referenced NFS path
isn't mounted (without blocking install).

## Team Share

Two patterns for sharing All-Might across a team:

* **Bundle share** — push a personality bundle to a git remote with
  `allmight share publish`; teammates `allmight share pull` to
  import. Each receiver owns their copy. Best for starter-kit
  personalities that get customised per project.

  ```bash
  # Step 1 — on the source project, produce a reviewed bundle:
  #   run /one-for-all in the agent → writes ./stdcell_owner-export/
  # Step 2 — push the bundle to a git remote:
  allmight share publish ./stdcell_owner-export/ \
                         --to file:///nfs/team/stdcell_owner.git

  # On a receiving project:
  allmight share pull file:///nfs/team/stdcell_owner.git
  allmight share pull file:///nfs/team/stdcell_owner.git --as stdcell_v2
  ```

  Any URL the local `git` can reach works (file://, ssh, https). For
  a brand-new local bare repo, `share publish` runs `git init --bare`
  on first push automatically.

* **Instance share** — multiple users `cd` into a shared NFS-hosted
  All-Might project and run their agents against the same memory +
  database. Best for service roles like a team review agent. The
  `memory/lessons_learned/_inbox/` directory is the user-side write
  buffer for that mode; a curator periodically audits and promotes
  entries to `_reviewed/`.

For database (SMAK) sharing, the canonical pattern is one
NFS-hosted SMAK index per team, written by a single dedicated
account, read by everyone. A personality bundle records its SMAK
index dependencies in `manifest.yaml::database_subscriptions`; on
import, missing NFS paths surface as warnings without blocking the
install.

See [docs/team-share.md](docs/team-share.md) for the layout,
permissions, manifest schema, and the lessons-learned curation
workflow.

## Re-init is safe

```bash
pip install --upgrade allmight
allmight init .                    # safe; stages new templates if changed
```

New templates land in `.allmight/templates/` rather than overwriting
your working files. `/sync` walks you through merging your
customisations with the staged updates.

If you authored a file at `.opencode/<kind>/<name>` before running
init, All-Might preserves it and stages a manifest at
`.allmight/templates/conflicts.yaml`; `/sync` resolves each conflict
interactively.

`--force` overwrites everything. `MEMORY.md` is never overwritten —
once it exists it's agent-authored from `/onboard` onward.

## Migrating older projects

If you have an All-Might project from before the Part-C / Part-D
layout (legacy `<project>-corpus` / `<project>-memory` instance
dirs, separate `/reflect` command, single-file `AGENTS.md`), the
one-shot migrator rewrites the tree in place:

```bash
allmight migrate --dry-run     # print the plan, no changes
allmight migrate               # apply
```

Idempotent on already-migrated projects.

## Plugin observability

Every plugin and hook touches a marker file when it fires:

```bash
allmight plugin status
# OpenCode plugins:
#   memory-load      fired 12s ago
#   memory-history   fired 12s ago
#   role-load        never fired
# Claude Code hooks:
#   memory_load      fired 12s ago
#   ...
```

`never fired` is the signal to investigate. Design rationale and the
plugin-reduction plan live in
[docs/plugin-observability.md](docs/plugin-observability.md).

## Recovering from accidental memory edits

Every memory write is auto-snapshotted into a local git mirror at
`.allmight/memory-history/` (separate from your project's main
`.git`). Snapshots fire automatically after every agent turn (and
on session end / pre-compaction).

The friendly path: just tell the agent.

```text
> Oops, I deleted understanding/stdcell.md by accident — get it back?
```

The `/recover` skill walks you through picking the right snapshot
and restores the file. SMAK vector indices (`store/`) are excluded
from the mirror — they're rebuilt out-of-band via the `smak ingest`
CLI.

For scripting / power users, the same operations are exposed as CLI
subcommands:

```bash
allmight memory log                          # see snapshots
allmight memory log --personality stdcell_owner -n 5
allmight memory diff <sha>                   # what changed
allmight memory restore MEMORY.md --rev HEAD~1
allmight memory snapshot -m "before risky edit"
```

## Exporting memory for offline analysis

```bash
allmight memory export --format jsonl --out trajectory.jsonl
```

Walks `personalities/*/memory/journal/` for entries carrying the
`allmight_journal: v1` frontmatter sentinel and writes them as
JSONL. Legacy / freeform entries are counted and skipped — they need
to be reflected through `/remember` to get the structured shape.

## Glossary

| Term | What it means |
|------|--------------|
| **Personality** | A user-defined role (e.g. `stdcell_owner`). One `ROLE.md`, plus a data dir for each capability it has. |
| **Capability** | A reusable feature module the framework provides — currently `database` (knowledge graph) and `memory` (cross-session memory). |
| **Workspace** | One independently-indexed corpus inside a personality's `database/`. A personality can have several. |
| **Default personality** | The hint written to the top of `MEMORY.md` (`> **Default personality**: <name>`) that resolves the active personality when the conversation isn't clearly about a specific one. |
| **Annotation** | A note on a code symbol describing what it does and what it links to. Stored in sidecar files beside the source. |

## Compatibility

| Tool | Status |
|------|--------|
| **OpenCode** | First-class support — primary target |
| **Claude Code** | First-class support for the plugins whose required platform capabilities Claude Code's hook system can provide; see matrix below |

### Plugin × platform matrix

OpenCode is the design target. Claude Code is mirrored where the
hook system structurally supports the same behaviour — some
OpenCode events (`session.idle`, mid-turn message injection,
cross-turn plugin state) have no Claude Code analogue, so those
plugins are OpenCode-only **by platform design**, not as TODOs.

<!-- ALLMIGHT_COMPAT_MATRIX_START -->
<!-- Generated from src/allmight/core/plugin_telemetry.py::PLUGIN_MANIFEST. -->
<!-- To regenerate: `allmight plugin matrix`. -->

| Plugin | OpenCode | Claude Code | Notes |
|--------|----------|-------------|-------|
| `memory-history` | ✓ | ✓ | Snapshot memory data after every turn; mark L3 ingest pending if journal changed |
| `memory-load` | ✓ | ✓ | Inject MEMORY.md + scope-first principle at session start; drain L3 ingest if pending |
| `offline-reference` | ✓ | ✓ | Tell the agent it is air-gapped: use project_knowledge_search / memory_recall instead of web_search / context7 |
| `reflection` | ✓ | ✓ | Per-turn reflection nudge that fires before the user prompt |
| `remember-trigger` | ✓ | — | OpenCode-only — requires `session_idle_counter, mid_turn_message_inject` |
| `role-load` | ✓ | ✓ | Inject the active personality's ROLE.md at session start |
| `todo-curator` | ✓ | — | OpenCode-only — requires `cross_turn_plugin_state, mid_turn_message_inject` |
| `trajectory-writer` | ✓ | — | OpenCode-only — requires `cross_turn_plugin_state` |
| `usage-logger` | ✓ | — | OpenCode-only — requires `tool_execute_after_inject, mid_turn_message_inject` |
<!-- ALLMIGHT_COMPAT_MATRIX_END -->

`allmight init` writes the canonical `.opencode/` surface and a
generated `.claude/` mirror in the same pass: `.claude/commands` and
`.claude/skills` are directory symlinks back into `.opencode/`,
`.claude/hooks/*.py` are Python rewrites of the matching
`.opencode/plugins/*.ts`, and the root `CLAUDE.md` is an `@`-import
shim that points Claude Code at `AGENTS.md` and `MEMORY.md`. A single
edit to `ROLE.md` / `AGENTS.md` / `MEMORY.md` is picked up by both
editors.

### oh-my-opencode (OMO) caveat

OMO 4.x ships a built-in hook called `claude-code-hooks` that re-runs
every Claude Code hook from inside OpenCode on equivalent lifecycle
events. For an All-Might project that means a double-fire (we
already emit native OpenCode plugins for everything we mirror), and
under the Claude "non-zero exit injects stderr as next prompt"
semantics a single broken hook can cascade. If you use OMO, disable
the bridge at the project level:

```json
// .opencode/oh-my-opencode.json
{ "disabled_hooks": ["claude-code-hooks"] }
```

## License

MIT
