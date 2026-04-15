---
name: one-for-all
description: All-Might knowledge guide. Project structure, corpus reference, enrichment protocol, key symbols, and Power Level. Auto-loaded when agent needs to understand the project.
---

# One For All — All-Might

> **All-Might** is the active knowledge graph layer that indexes this codebase,
> providing commands, enrichment, and graph intelligence.
>
> All knowledge graph operations go through **All-Might commands** (`/search`, `/enrich`, `/explain`, etc.).
> Do NOT hand-edit sidecar or config YAML files.

## Project Overview

- **Name**: All-Might
- **Languages**: Verilog, SystemVerilog
- **Frameworks**: Not yet detected

### Directory Structure

- `constraints/` — Design constraints
- `rtl/` — RTL design files
- `verif/` — Verification/testbench


## Corpus Reference

| Index | Description | Paths |
|-------|-------------|-------|
| `rtl` | RTL design files — RTL design files (Verilog, SystemVerilog) | `./rtl` |
| `verif` | Verification/testbench — Verification testbenches and coverage models | `./verif` |
| `constraints` | SDC timing constraints, floorplan DEF, and power intent UPF | `./constraints` |


Use `/list-indices` to verify indices are active.

> **Note:** This workspace is a standalone hub — source code is at external paths
> listed in the "Paths" column above. Search data is stored locally in `./smak/`.
> Sidecar files live beside the source files at those external paths, not here.
> **Indices are built from online (Layer 1) only.** To verify features in version control
> releases, use SOS revision log matching (see `sos-smak` skill).

## Key Symbols

> No symbols have been enriched yet. As you work with this project and use
> `/enrich` to annotate code, this section will be populated when you
> run `/regenerate`.

## Power Level

- **Coverage**: 0% (fresh workspace)
- **Enriched symbols**: 0
- **Total relations**: 0

Run `/power-level` to get current metrics, or `/regenerate` to update this skill.

## All-Might Commands

| Command | Purpose |
|---------|---------|
| `/search <query>` | Semantic search with graph context |
| `/explain <uid>` | Full graph context for a symbol |
| `/enrich` | Annotate a symbol with intent/relations |
| `/ingest` | Rebuild corpus |
| `/power-level` | Check knowledge coverage metrics |
| `/regenerate` | Update this skill with latest state |
| `/panorama` | Export knowledge graph visualization |
| `/graph-report` | Graph intelligence report |
| `/add-index` | Add a new corpus |
| `/remove-index` | Remove an index |
| `/list-indices` | List all configured indices |

## Getting Started

1. Use `/search "..."` to explore the codebase semantically
2. Use `/explain "path::symbol"` for deep context on any symbol
3. When you understand a symbol's purpose, use `/enrich` (see `enrichment-protocol` skill)
4. Run `/power-level` periodically to track progress

<!-- MEMORY -->

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
