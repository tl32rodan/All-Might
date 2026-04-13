---
name: enrich
description: >-
  Know-how injection. Persist domain knowledge into a workspace's .claude/
  layer — symbol patterns, terminology, relationships, gotchas. Use when
  you learn something about a flow that should be remembered across sessions.
  Distinct from sidecar enrichment (which annotates individual symbols via
  /enrich command and sidecar-handling skill).
disable-model-invocation: true
argument-hint: "<workspace> <knowledge>"
---

# Enrich — Know-How Injection

Inject domain knowledge into a workspace's `.claude/` layer so that future
sub-agent queries in that workspace benefit from accumulated know-how.

## What This Skill Does

Enrichment at the `.claude/` level is about **teaching the workspace**.  It
updates the workspace's CLAUDE.md and skills with structured knowledge that
persists across sessions:

- Symbol patterns ("all timing constraints in this flow use class X")
- Domain terminology ("CTS means Clock Tree Synthesis in this context")
- Relationship hints ("module A always calls module B's init before use")
- Gotchas ("never modify file X without also updating config Y")

This is distinct from **sidecar enrichment** (which annotates individual symbols
via `/enrich` and the `sidecar-handling` skill).

## When to Use

| Situation | Use `enrich` skill? |
|-----------|-------------------|
| You learned a domain pattern while working with a flow | **Yes** — persist it |
| User tells you something about how a flow works | **Yes** — persist it |
| You found a cross-cutting pattern across flows | Use `self-improving` instead |
| You want to annotate a specific symbol's intent/relations | Use `/enrich` command or `sidecar-handling` instead |
| You want to update the hub's global knowledge | Use `self-improving` instead |

## Workflow

### Step 1: Identify the Knowledge

What did you learn?  Categorize it:

| Category | Example | Where it goes in .claude/ |
|----------|---------|--------------------------|
| **Domain concept** | "CTS = Clock Tree Synthesis" | CLAUDE.md glossary section |
| **Code pattern** | "All constraint handlers inherit from BaseConstraint" | CLAUDE.md patterns section |
| **Relationship** | "TimingEngine always calls ClockDomain.validate() first" | CLAUDE.md relationships section |
| **Gotcha/warning** | "Never edit timing.cfg directly — use gen_timing.py" | CLAUDE.md warnings section |
| **Workflow** | "To add a new constraint: create class, register in factory, add test" | skills/ (new or existing skill) |

### Step 2: Read Current State

Before writing, read the workspace's current `.claude/`:

1. Read `workspaces/<name>/.claude/CLAUDE.md` — understand what's already there
2. Read `workspaces/<name>/.claude/skills/` — check if a relevant skill exists
3. Decide: update existing section, add new section, or create new skill?

### Step 3: Write the Knowledge

**For CLAUDE.md updates** — maintain this structure in workspace CLAUDE.md:

```markdown
# <Workspace Name>

## Domain Concepts
- Term: definition
- Term: definition

## Code Patterns
- Pattern: description + example file/symbol

## Key Relationships
- A -> B: description of the relationship

## Warnings
- WARNING: gotcha description

## Workflow Notes
- How to do X: step-by-step
```

**For skill creation** — write to `workspaces/<name>/.claude/skills/<skill-name>/SKILL.md`
only when the knowledge is a complete, reusable workflow (not just a fact).

### Step 4: Verify

After writing, confirm:
- [ ] The workspace CLAUDE.md is valid markdown
- [ ] No duplicate entries were created
- [ ] The knowledge is stated clearly enough for a sub-agent to act on it
- [ ] The knowledge does NOT include SOS/online/VC concepts (global concern)

## What NOT to Put in Workspace .claude/

The workspace `.claude/` is for **domain-specific knowledge only**.  Do NOT include:

- Online vs. VC awareness (lives in hub CLAUDE.md)
- SOS workflow instructions (lives in `sidecar-handling` skill)
- Cross-workspace patterns (lives in hub CLAUDE.md, managed by `self-improving`)
- Guardrails about sidecar editing (lives in hub CLAUDE.md)
- SMAK philosophy or general instructions (lives in hub CLAUDE.md)

## Example

User says: "In the stdcell flow, all placement constraints inherit from
`PlacementBase` and must implement `apply()` and `validate()` methods."

Action:
1. Read `workspaces/stdcell/.claude/CLAUDE.md`
2. Add to the "Code Patterns" section:
   ```markdown
   - Placement constraints: All inherit from `PlacementBase` (in `src/placement/base.py`).
     Must implement `apply()` and `validate()`.  See `HaloConstraint` for reference.
   ```
3. Confirm the update doesn't duplicate existing entries.

## Interaction with Other Skills

| Skill | Relationship |
|-------|-------------|
| `detroit-smak` | Enrich makes detroit-smak sub-agents smarter — they see the persisted knowledge |
| `self-improving` | Self-improving reads enriched workspaces to find patterns worth promoting |
| `sidecar-handling` | Sidecar enrichment annotates individual symbols; `.claude/` enrichment teaches patterns |
