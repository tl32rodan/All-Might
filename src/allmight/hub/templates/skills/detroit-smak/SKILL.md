---
name: detroit-smak
description: >-
  Precision workspace strike. Spawn a sub-agent inside a workspace to
  perform semantic search, enrichment lookup, or graph queries. Supports
  single-target and multi-target (parallel) modes. Use when you need to
  query indexed knowledge in one or more workspaces.
disable-model-invocation: true
argument-hint: "<workspace> <query>"
---

# Detroit SMAK — Precision Strike

Dispatch a sub-agent into a specific workspace to perform semantic search,
enrichment lookup, or graph queries.  The sub-agent inherits the hub's global
context and automatically loads the workspace's domain-specific `.claude/`.

## How It Works

```
Hub Agent (you)
  |
  |-- 1. Select target workspace(s)
  |-- 2. Formulate query
  |-- 3. Spawn sub-agent with cwd = workspaces/<name>/
  |       |
  |       +-- Sub-agent loads workspaces/<name>/.claude/ (automatic)
  |       +-- Sub-agent has search bridge for this workspace
  |       +-- Sub-agent executes query
  |       +-- Sub-agent returns structured results
  |
  +-- 4. Receive and synthesize results
```

## Sub-Agent Mechanics

The sub-agent launches with **workspace directory as cwd**.  Claude Code's native
`.claude/` loading picks up the workspace's domain context automatically.

What the sub-agent sees:
- `config.yaml` — the corpus configuration for this domain
- `smak/` — Search data for semantic search
- `.claude/CLAUDE.md` — domain-specific knowledge (symbol memory, patterns)
- `.claude/skills/` — domain-specific skills (if any)
- `enrichment/` — power tracker for this workspace

What the sub-agent does NOT need to know:
- Online vs. VC (global concern — handled at hub level)
- SOS workflows (global concern — handled by `sidecar-handling` skill)
- Other workspaces (the sub-agent focuses on its assigned domain)

## Single-Target Usage

When you need to query **one** workspace:

1. Identify the target workspace from the registry (see CLAUDE.md workspace table)
2. Spawn a sub-agent with:
   - `cwd`: `workspaces/<name>/`
   - Task: the semantic search query, enrichment lookup, or graph question
3. Wait for results
4. Present findings to user with workspace context

### Example Prompts to Sub-Agent

**Semantic search:**
> Search for "timing constraint handler" using the corpora in this workspace.
> Return the top 5 results with file paths, symbol names, and relevance scores.

**Enrichment lookup:**
> Look up the enrichment status of `src/timing/constraint.py::TimingHandler`.
> Return its sidecar content (intent, relations) and suggest missing relations.

**Graph query:**
> Using the panorama graph, find all symbols that depend on `src/core/clock.py::ClockDomain`.
> Show the dependency chain up to 3 levels deep.

## Multi-Target Usage

When you need to search **across multiple workspaces** (e.g., finding shared library
usage across flows):

1. Identify all target workspaces
2. Spawn sub-agents **in parallel** — one per workspace, same query
3. Collect results from all sub-agents
4. Correlate and synthesize at hub level:
   - Which workspaces returned matches?
   - Are the matches referring to the same underlying code?
   - What cross-workspace patterns emerge?

### Example Multi-Target Scenario

> User: "Where is `shared_lib::TimingUtils` used across all flows?"
>
> Hub action:
> 1. Spawn sub-agents for stdcell, io_phy, pll, ... (all workspaces)
> 2. Each sub-agent runs: search for "TimingUtils" in their corpus
> 3. Collect results: stdcell has 5 hits, io_phy has 3 hits, pll has 0 hits
> 4. Present: "TimingUtils is used in 2 of 10 flows — stdcell (5 references)
>    and io_phy (3 references). PLL and other flows do not reference it."

## Result Format

When returning results to the user, always include:

- **Workspace name** — which domain the result comes from
- **File path** — relative to the workspace's source root
- **Symbol UID** — in `<file_path>::<symbol_name>` format
- **Relevance context** — why this result matters for the query
- **Enrichment status** — whether the symbol has sidecar annotations

## When to Use This Skill

| Situation | Action |
|-----------|--------|
| User asks about code in a specific flow | Single-target detroit-smak |
| User asks about code across flows | Multi-target detroit-smak |
| User wants to understand a specific symbol | Single-target with `/explain` query |
| User wants to find where something is used | Multi-target search |
| User asks a vague question about "the code" | Ask which workspace, then single-target |

## Important

- **Always** use this skill to query workspaces.  Do NOT read workspace files directly
  from the hub — the sub-agent needs its own `.claude/` context to give good answers.
- **Always** specify the workspace by name, not by path.
- For multi-target queries, issue sub-agents **in parallel** for efficiency.
- If a sub-agent returns no results, report that — don't silently skip it.
