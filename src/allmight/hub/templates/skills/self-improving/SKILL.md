---
name: self-improving
description: >-
  Hub-level audit and evolution. Scan all workspaces' .claude/ layers,
  identify cross-workspace patterns worth promoting, detect gaps and stale
  knowledge, and propose improvements to the hub CLAUDE.md and global skills.
  Also provides aggregate power tracking across workspaces.
disable-model-invocation: true
---

# Self-Improving — Hub-Level Audit & Evolution

Scan all managed workspaces, assess their `.claude/` health, identify patterns
worth promoting to the hub level, and propose improvements.

## Purpose

The hub gets smarter over time.  This skill drives the feedback loop:

```
workspaces enriched  -->  self-improving reads them
                              |
                              v
                     identifies cross-workspace patterns
                              |
                              v
                     proposes hub CLAUDE.md / skill updates
                              |
                              v
                     (with user approval) propagates to other workspaces
```

## When to Use

- User asks "what should we improve?" or "how healthy is the knowledge graph?"
- After a batch of enrichment work across multiple workspaces
- Periodically (e.g., weekly review of hub health)
- When you notice a pattern repeating across workspaces

## Audit Workflow

### Phase 1: Gather State

For each workspace in the registry:

1. **Read `.claude/CLAUDE.md`** — what domain knowledge is documented?
2. **Read `.claude/skills/`** — any domain-specific skills?
3. **Check enrichment health** — run `allmight power-level <workspace>` or read
   `workspaces/<name>/enrichment/tracker.yaml` to see:
   - Coverage percentage (what fraction of symbols have sidecar annotations)
   - History (is coverage trending up or stagnating?)
   - Last enrichment date

### Phase 2: Analyze

Look for these patterns:

#### A. Promotable Patterns
Knowledge that appears in 2+ workspaces and should be in the hub CLAUDE.md:

> Example: "stdcell, io_phy, and pll all document that constraints inherit from
> `BaseConstraint`.  This is a global pattern — promote to hub CLAUDE.md."

#### B. Gaps
Workspaces with weak or missing knowledge:

> Example: "stdcell has 12 documented patterns, io_phy has 8, but pll has 0.
> PLL needs enrichment attention."

#### C. Stale Knowledge
Knowledge that may be outdated (source code changed but `.claude/` wasn't updated):

> Example: "stdcell documents `OldTimingEngine` but search shows it was replaced
> by `NewTimingEngine`.  Update needed."

#### D. Inconsistencies
Workspaces that describe the same concept differently:

> Example: "stdcell calls it 'placement constraint', io_phy calls it 'place rule'.
> Standardize terminology in hub CLAUDE.md glossary."

### Phase 3: Report

Present findings as a structured report:

```markdown
## Self-Improvement Report — <date>

### Hub Health Summary
| Workspace | .claude/ entries | Power level | Last enriched | Status |
|-----------|-----------------|-------------|---------------|--------|
| stdcell   | 12 patterns     | 34%         | 2 days ago    | Good   |
| io_phy    | 8 patterns      | 22%         | 1 week ago    | OK     |
| pll       | 0 patterns      | 5%          | never         | Needs attention |

### Promotable Patterns (-> hub CLAUDE.md)
1. [pattern description] — seen in: stdcell, io_phy

### Gaps
1. pll — no domain knowledge documented yet

### Stale Knowledge
1. stdcell — `OldTimingEngine` reference may be outdated

### Recommended Actions
1. Promote [pattern] to hub CLAUDE.md
2. Prioritize pll enrichment
3. Verify stdcell `OldTimingEngine` references
```

### Phase 4: Act (with user approval)

**Hub updates** — propose specific edits to:
- `<hub>/.claude/CLAUDE.md` — new global patterns, glossary terms
- `<hub>/.claude/skills/` — updated skill content

**Knowledge propagation** — push patterns to workspaces that lack them:
- Read workspace `.claude/CLAUDE.md`
- Add the promoted pattern (if not already present)
- Confirm with user before writing

**IMPORTANT**: Always ask for user approval before modifying hub CLAUDE.md or
propagating knowledge to workspaces.  Present the diff and explain why.

## Hub-Level Power Tracking

Aggregate power level across all workspaces:

| Metric | How to compute |
|--------|---------------|
| **Hub coverage** | Average power level across all workspaces |
| **Weakest workspace** | Workspace with lowest power level |
| **Knowledge density** | Total `.claude/` entries across all workspaces |
| **Coverage trend** | Compare current vs. last audit |

## What This Skill Does NOT Do

- Does NOT perform sidecar enrichment (that's `/enrich` + `sidecar-handling`)
- Does NOT query workspace SMAK indices (that's `detroit-smak`)
- Does NOT make changes without user approval
- Does NOT touch online/VC/SOS concerns (global, already in hub CLAUDE.md)
