# All-Might Workflow

## Overview

```
Human                                Agent
──────                               ──────

Phase 0: Bootstrap
  allmight init .                →

Phase 1: Explore
  /ingest                       →    Build search index
                                     /search "query"
                                     Read source code

Phase 2: Enrich
                                     /enrich --file --symbol --intent
                                     /enrich --relation --bidirectional

Phase 3: Remember
                                     /remember "observation"
                                     /recall "query"

Phase 4: Reflect
  /reflect                           Review and tidy memory
```

## Human vs Agent Responsibilities

### Human does

| When | Action | Why |
|------|--------|-----|
| **First time** | `allmight init .` | Create workspace + memory |
| **First time** | `/ingest` (in agent) | Build search index |
| **Set preferences** | Tell agent directly | Agent records to MEMORY.md |

### Agent does (automatically)

| When | Action | Why |
|------|--------|-----|
| **Every turn** | Load `MEMORY.md` (via hook) | L1 always in context |
| **Reading code** | `/enrich` if intent is missing | Grow knowledge graph |
| **Finding relations** | `/enrich --relation` | Link symbols |
| **Learning something** | Update L2 understanding | Per-workspace knowledge |
| **Worth logging** | Append to L3 journal | Searchable via `/recall` |
| **Session end** | `/reflect` | Keep memory tidy |

## Session Lifecycle

```
┌─────────── Session Start ──────────┐
│                                     │
│  1. MEMORY.md injected (L1 hook)    │ ← automatic
│  2. one-for-all SKILL.md loaded     │ ← automatic
│                                     │
├─────────── Active Work ────────────┤
│                                     │
│  /search             → explore      │
│  /enrich             → annotate     │
│  /remember           → record       │
│  /recall             → search past  │
│                                     │
├──────── Memory Nudge (hook) ───────┤
│                                     │
│  After each response, agent is      │
│  reminded to update memory if it    │
│  learned something.                 │
│                                     │
├─────────── Session End ────────────┤
│                                     │
│  /reflect — tidy L1, update L2,     │
│  log to L3 journal                  │
│                                     │
└─────────────────────────────────────┘
```

## Milestone Checkpoints

| Milestone | How to verify | You're on track when |
|-----------|---------------|---------------------|
| **Init complete** | `knowledge_graph/` exists | `allmight init` printed "initialized" |
| **Index built** | `/search` returns results | `/search "main"` shows hits |
| **First enrichment** | Sidecar file created | A symbol has intent |
| **Memory active** | `MEMORY.md` has content | L1 loaded every turn |
| **Knowledge growing** | L2 files exist | `memory/understanding/*.md` populated |
