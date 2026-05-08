# All-Might

Turn your codebase into a knowledge graph that AI agents can search,
learn from, and remember across sessions — organised around the
**roles** *you* care about, not toolkits the framework hands you.

## How It Works

You define **personalities** — roles like `stdcell_owner`,
`pll_owner`, `code_reviewer` — and pick which **capabilities** each
one needs:

* The **`database` capability** indexes source code so the agent can
  search by meaning ("how does authentication work?") and annotate
  what each symbol does. Each personality gets its own searchable
  workspace.
* The **`memory` capability** keeps cross-session memory: your
  preferences, past decisions, scope-specific journal entries.

A single project can hold one personality (the default after
`allmight init`) or many (`allmight add` adds more). All personalities
share **one** flat slash-command surface — `/search`, `/remember`,
`/recall`, `/enrich`, `/ingest`, `/onboard`, `/one-for-all`,
`/all-for-one`, `/sync` — and the agent decides which personality to
act for from conversation context plus a `> **Default personality**:
<name>` hint at the top of `MEMORY.md`.

## Setup

```bash
pip install allmight
cd /path/to/my-chip-project
allmight init .                # creates one personality named after the dir
```

`allmight init` asks a single question (with `--yes` to skip):

```
Personality name? [my-chip-project]
```

The default is the project-root directory name. The personality is
created with all available capabilities (`database` + `memory`).

Then open the project in **Claude Code** or **OpenCode** and run
`/onboard` once — the agent asks one open-ended question per
personality ("tell me about the `<name>` role"), writes the answers
into `personalities/<name>/ROLE.md`, populates `MEMORY.md`'s project
map, and (if there's more than one personality) records the default.

## Adding more personalities

```bash
allmight add stdcell_owner --capabilities database,memory
allmight add pll_owner     --capabilities database,memory
allmight add code_reviewer --capabilities memory     # no database
```

`--capabilities` is a comma-separated list. Omit it to install every
available capability. `code_reviewer` above is created with only the
`memory` capability — no `database/` data dir, no `/search`-against-it.

```bash
allmight list
# Personality     Capabilities      Version
# my-chip-project database, memory  1.0.0
# stdcell_owner   database, memory  1.0.0
# pll_owner       database, memory  1.0.0
# code_reviewer   memory            1.0.0
```

## Project layout

```
my-chip-project/
├── AGENTS.md                            ← composed from each ROLE.md
├── MEMORY.md                            ← project map + default-personality hint
├── .opencode/                           ← Claude Code / OpenCode picks this up
│   ├── commands/                        ← /search, /remember, /one-for-all, …
│   ├── plugins/                         ← memory hooks, role loader, memory-history
│   └── skills/                          ← /onboard, /one-for-all, /all-for-one, /sync
└── personalities/
    ├── my-chip-project/
    │   ├── ROLE.md
    │   ├── commands/                    ← initially empty; for personality-specific commands
    │   ├── skills/                      ← same
    │   ├── database/                    ← knowledge-graph workspaces
    │   └── memory/                      ← per-personality journal + understanding
    ├── stdcell_owner/
    └── pll_owner/
```

The agent surface (`commands/`, `skills/`, `plugins/`) lives **once**
in `.opencode/` — capability templates write the globals there
directly. Each personality has its own real `commands/` and `skills/`
slot for personality-specific entries; ``compose`` projects those into
``.opencode/<kind>/`` via downward symlinks so OpenCode discovers them
from one global scan.

## Talking to the agent

```text
> Search the stdcell rtl for setup-time violations.
> Remember that the PLL lock-time spec is 50 µs.
> What did we decide last week about the io_phy retiming?
```

The agent reads `MEMORY.md`'s project map (one row per personality),
picks the right personality from your phrasing, and runs the matching
command against that personality's data dir.

## Commands

| Command   | Plain English |
|-----------|--------------|
| `/onboard`  | Capture each personality's role and (if 2+ personalities) pick the default. Run once after `allmight init`. |
| `/search`   | "Search for ..." |
| `/enrich`   | "Annotate this symbol" |
| `/ingest`   | "Build the search index" |
| `/remember` | "Remember that ..." (records *or* reviews — agent picks based on trigger) |
| `/recall`   | "What do you know about ...?" |
| `/one-for-all` | "Export `<name>` so I can share it" — agent applies per-capability rules and reviews for PII (1 personality → 1 bundle) |
| `/all-for-one` | "Merge these into one personality" — fold multiple bundles or in-project personalities into one target (N → 1) with per-file dialog |
| `/sync`     | Merge staged template updates after re-init / resolve compose conflicts |

## Sharing personalities between projects

Two skills, themed after All-Might's quirks. Use **`/one-for-all`**
to export one personality outward (1 → 1) and **`/all-for-one`** to
absorb sources into one (N → 1):

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

`store/` is never bundled — the receiver runs `/ingest` to rebuild it.

### Import (single bundle, no merge): `allmight import`

```bash
allmight import ./stdcell_owner-export/
allmight import ./stdcell_owner-export/ --as stdcell_v2  # rename
```

Mechanical install — runs each capability's install hook, copies
the bundled files, records lineage. **Refuses if a personality of
the same name already exists** and points you at `/all-for-one` to
merge instead. Reserved for CI / scripting / fresh-project bootstrap.

### Merge (multiple sources, or fold-into-existing): `/all-for-one`

Run this skill in the agent when you want to:

- Combine multiple bundles into one personality
- Fold a bundle into an existing personality (`allmight import`
  refused on collision)
- Consolidate two in-project personalities (`stdcell_owner` +
  `pll_owner` → `eda_owner`) — sources don't have to be bundles

The agent walks per-capability merge rules: workspace-name clashes,
`memory/understanding/` overwrites, `memory/journal/` append + dedupe,
`ROLE.md` prose reconciliation. Each conflict is resolved with a
short dialog. By default the source personalities are kept after the
merge (the agent asks before removing them). Lineage from every
source is recorded in the target's `derived_from` list.

After any import or merge, run `/ingest` in the merged workspaces to
rebuild SMAK indices.

## Team Share

Two patterns for sharing All-Might across a team:

* **Bundle share** — push a personality bundle to a git remote with
  `allmight share publish`; teammates `allmight share pull` to import.
  Each receiver owns their copy. Best for starter-kit personalities
  that get customised per project.

  ```bash
  # On the source project (after running /one-for-all to produce the bundle):
  allmight share publish ./stdcell_owner-export/ --to file:///nfs/team/stdcell_owner.git

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
it's agent-authored from `/onboard` onward.

## Recovering from accidental memory edits

Every memory write is auto-snapshotted into a local git mirror at
`.allmight/memory-history/` (separate from your project's main
`.git`). Accidental deletes or overwrites are recoverable:

```bash
allmight memory log                          # see snapshots
allmight memory log --personality stdcell_owner -n 5
allmight memory diff <sha>                   # what changed
allmight memory restore MEMORY.md --rev HEAD~1
allmight memory restore personalities/stdcell_owner/memory/understanding/stdcell.md
```

Snapshots fire automatically after every agent turn (and on session
end / pre-compaction). You can also run `allmight memory snapshot`
by hand. SMAK vector indices (`store/`) are excluded from the
mirror — they're rebuilt by `/ingest`.

## Glossary

| Term | What it means |
|------|--------------|
| **Personality** | A user-defined role (e.g. `stdcell_owner`). One ROLE.md, plus a data dir for each capability it has. |
| **Capability** | A reusable feature module the framework provides — currently `database` (knowledge graph) and `memory` (cross-session memory). |
| **Workspace** | One independently-indexed corpus inside a personality's `database/`. A personality can have several. |
| **Default personality** | The hint written to the top of `MEMORY.md` (`> **Default personality**: <name>`) that resolves the active personality when the conversation isn't clearly about a specific one. |
| **Annotation** | A note on a code symbol describing what it does and what it links to. Stored in sidecar files beside the source. |

## Compatibility

| Tool | Status |
|------|--------|
| **Claude Code** | First-class support |
| **OpenCode** | First-class support |

## License

MIT
