# All-Might Workflow

## Overview

```
Human                                Agent
──────                               ──────

Phase 0: Bootstrap
  allmight init [--with-memory]  →
  /ingest                       →

Phase 1: Explore
                                     /search "query"
                                     /explain "uid"
                                     Read source code

Phase 2: Enrich
                                     /enrich --file --symbol --intent
                                     /enrich --relation --bidirectional

Phase 3: Remember (if memory enabled)
                                     /memory-observe "observation"
  /memory-update user_model "..."    /memory-recall "query"

Phase 4: Consolidate
  /memory-consolidate                episodic → semantic merge

Phase 5: Maintain
  /power-level                       /regenerate
  /memory-status                     /graph-report

Phase 6: Cleanup
  allmight memory gc                  Decay auto-removes low-value memories
```

## Human vs Agent Responsibilities

### Human does

| When | Action | Why |
|------|--------|-----|
| **First time** | `allmight init .` | Create workspace |
| **First time** | `/ingest` (in agent) | Build search index |
| **Optional** | `allmight memory init` | Enable agent memory |
| **When agent is wrong** | `/memory-update user_model "..."` | Correct agent's understanding |
| **Set preferences** | `/memory-update user_model "prefer concise"` | Persists across sessions |
| **Set environment** | `/memory-update environment "Node 18+"` | Persists across sessions |
| **Weekly** | `/memory-consolidate` | Convert episodes to facts |
| **Check health** | `/power-level`, `/memory-status` | Track progress |
| **Cleanup** | `allmight memory gc` | Remove decayed memories |
| **On conflicts** | Review agent's conflict reports | Arbitrate contradicting facts |

### Agent does (automatically)

| When | Action | Why |
|------|--------|-----|
| **Session start** | Load `MEMORY.md` | Working memory in context |
| **Reading code** | `/enrich` if intent is missing | Grow knowledge graph |
| **Finding relations** | `/enrich --relation` | Link symbols |
| **Noticing patterns** | `/memory-observe "..."` | Buffer to episode |
| **Human corrects** | `/memory-observe "User corrected: X→Y"` | Record correction |
| **Needing history** | `/memory-recall "query"` | Search past sessions |
| **Session end** | Create Episode (via hook or manual) | Summarize session |
| **On consolidation** | Extract observations → semantic facts | Detect patterns, conflicts |
| **Maintenance** | `/regenerate` | Update skills with latest data |

## Session Lifecycle

```
┌─────────── Session Start ──────────┐
│                                     │
│  1. MEMORY.md loaded (working mem)  │ ← automatic
│  2. one-for-all SKILL.md loaded     │ ← automatic
│  3. enrichment-protocol loaded      │ ← automatic
│                                     │
├─────────── Active Work ────────────┤
│                                     │
│  /search, /explain   → explore      │
│  /enrich             → annotate     │
│  /memory-observe     → record       │
│  /memory-recall      → remember     │
│  /memory-update      → correct      │ ← human-driven
│                                     │
├─────────── Session End ────────────┤
│                                     │
│  1. Episode created (observations,  │
│     decisions, files touched)       │
│  2. Written to memory/episodes/     │
│  3. /ingest if configured           │ ← optional hook
│                                     │
└─────────────────────────────────────┘
```

## Milestone Checkpoints

| Milestone | How to verify | You're on track when |
|-----------|---------------|---------------------|
| **Init complete** | `config.yaml` exists | `allmight init` printed "initialized" |
| **Index built** | `/search` returns results | `/search "main"` shows hits |
| **First enrichment** | `/power-level` > 0% | At least one symbol has intent |
| **Graph forming** | `/graph-report` | Clusters and relations visible |
| **Memory active** | `/memory-status` | Working memory has content |
| **First consolidation** | `/memory-consolidate` | Facts created from episodes |
| **Mature workspace** | `/power-level` > 20% | Key entry points annotated |

## Memory Update Timing

| When | Who | Does what | Updates |
|------|-----|-----------|---------|
| Session start | System | Load MEMORY.md | Working (read) |
| During work, pattern found | Agent | `/memory-observe` | Episodic (buffer) |
| During work, human corrects | Human | `/memory-update` | Working (write) |
| During work, need history | Agent | `/memory-recall` | Episodic + Semantic (read) |
| Session end | Hook/Agent | Create Episode | Episodic (write) |
| Weekly | Human triggers | `/memory-consolidate` | Semantic (write) |
| Conflict detected | Agent reports | Human arbitrates | Semantic (supersede) |
| Maintenance | Human | `allmight memory gc` | Semantic (cleanup) |
