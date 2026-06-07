# Offline Reference / Knowledge MCP — Design Proposal (Framework B)

> **Status:** active build. Framework A (`/docs` skill) was trialed and
> **reverted** (commit `990d8d7`) — it was, as the reviewer put it,
> "just a search skill" on the *pull* surface and could not occupy the
> model's autonomous *push* reflex. We go straight to **Framework B**:
> wrap All-Might's corpora as **MCP tools** so the model reaches for
> them the way OpenCode reaches for `websearch` / `context7`.

## Context — the gap

Air-gapped workstations have no `web_search` / `context7` (both are
cloud: OpenCode's `websearch` hits Exa, context7 is a hosted MCP). The
model's harness still *reflexively reaches for a tool* to look things
up; offline that dead-ends. Internal code also lacks API docs.

**Goal:** an offline, SMAK-backed substitute that (a) the model invokes
**autonomously** (tool, not slash command), and (b) exploits SMAK's
**semantic mesh** so a hit in code surfaces related docs and vice
versa — the agent itself builds those code↔doc links.

## Why this is *not* the rejected "capabilities as MCP" (Q6 / 2026-05-27)

Those rejections stand for **memory** and **code search** — both have
stable CLI paths; MCP would be redundant indirection. This proposal
targets the **one slot with no path at all**: the model's autonomous
web/docs reflex. Only a **tool** intercepts it; a skill/command cannot
(verified against OpenCode: `websearch` is a tool in the schema every
turn, invoked by the model — *push*, not *pull*).

## Key SMAK facts that make this work (verified)

- **Docs are first-class nodes.** `SMAK/src/smak/parsers/__init__.py`
  routes any non-code file to `SimpleLineParser` → `KnowledgeUnit(uid =
  "<path>::*", source_type="documentation")`. Manuals/`.md`/`.txt` are
  addressable, like code symbols (`file.py::Class.method`).
- **The agent builds links itself** via `enrich_symbol(..., relations=[...],
  bidirectional=True)` (`SMAK/src/smak/mcp_server.py:153`).
- **Search returns the 1-hop mesh** (`services/query.py:133-159`), and
  the relation resolver `_get_payload_globally` (`query.py:86-100`)
  **crosses every index in the config** — so code↔doc cross-retrieval
  works **iff code and docs live in the same workspace config.** A
  *separate* `docs/` workspace would break the mesh. → **Index docs as
  added paths / an extra index inside the existing database workspace,
  never as a separate workspace.**
- **`core_ops` is the in-process API**: `do_search`, `do_search_all`,
  `do_enrich_symbol`, + `load_config`/`init_config`/`load_embedding_config`.

## Decisions (this session)

1. **Cancel `/docs` (Framework A).** Done.
2. **Two intent-split MCP tools** (not one router):
   - `project_knowledge_search(query, top_k=8)` — the `websearch`/`context7`
     analog. Searches **all** `personalities/*/database/*` workspaces
     (code + docs + mesh). Knowledge is project-wide, not identity-scoped.
   - `memory_recall(query, personality=None, top_k=5)` — recall the
     agent's own past observations. **Default-personality-scoped** (read
     from MEMORY.md `> **Default personality**:`), `personality` arg
     overrides. Preserves per-personality memory isolation.
3. **Open enrichment (relax read-only).** A surface that teaches/enables
   the agent to build code↔doc relations via `smak enrich-symbol
   --relation --bidirectional`. The database `read-only` stance relaxes
   **for relations only** (not corpus content).
4. **Thin All-Might wrapper, in-process delegation.** `allmight/mcp/
   knowledge_server.py` (FastMCP) discovers configs from the project
   tree and delegates to `smak.core_ops`. SMAK's raw server is not
   wired directly (it needs a `config` arg per call + has generic
   names). Imports of `smak`/`mcp` are **lazy** so discovery logic is
   unit-testable without the heavy deps.

## MCP wiring shapes (verified from upstream docs)

OpenCode `.opencode/opencode.json`:
```json
{ "mcp": { "allmight-knowledge": {
  "type": "local",
  "command": ["python", "-m", "allmight.mcp.knowledge_server"],
  "enabled": true,
  "environment": { "ALLMIGHT_PROJECT_ROOT": "." }
}}}
```
Claude Code `.mcp.json`:
```json
{ "mcpServers": { "allmight-knowledge": {
  "type": "stdio",
  "command": "python",
  "args": ["-m", "allmight.mcp.knowledge_server"],
  "env": { "ALLMIGHT_PROJECT_ROOT": "." }
}}}
```
Both are **new write targets** → documented exception added to
CLAUDE.md "Interface Isolation" (`opencode.json#/mcp`, `.mcp.json`).
Both carry an All-Might marker / `setdefault` semantics so user edits
survive re-init.

## The harness hook (dual-platform)

`session_start_inject` plugin `offline-reference.ts` + mirror
`offline_reference.py`: tells the model "this environment is offline;
`web_search`/`context7` are unavailable — use `project_knowledge_search`
for library/tool/code lookups and `memory_recall` for past decisions;
if a search returns nothing, say so, **don't hallucinate**." Text from a
single generator `_offline_reference_notice()` (shared-constant rule).
Registered in `PLUGIN_MANIFEST` + heartbeat + `KNOWN_*` lists.

## Build sequence (incremental, each commit green + tested)

1. **Wrapper server** `allmight/mcp/knowledge_server.py` + tests
   (discovery, default-personality resolution, delegation with smak
   mocked). ← *slice 1, this is isolated and lowest-risk*
2. **MCP wiring** — database `install_globals` writes `opencode.json#/mcp`
   + `.mcp.json` (marker'd, re-init-safe) + CLAUDE.md exemption.
3. **Harness hook** `offline-reference` (ts + py + manifest + heartbeat).
4. **Enrichment surface** + read-only relaxation (relations only).
5. **Docs-in-workspace** guidance (scanner/onboard: index doc dirs into
   the same workspace as code).

## Failure modes (carried from v2)

- Empty/missing index → tool returns `{empty: true, reason}`; the hook
  tells the model to say so, never hallucinate.
- `memory_recall` with no resolvable personality → returns a clear error
  asking which personality, never guesses.
- Re-init must not clobber user-edited `opencode.json#/mcp`.

## Fundamentally unachievable (honest)

Current public-internet info, upstream docs newer than last sync, live
external APIs. Mitigated by provenance, not solved. The offline tool is
a **reference** substitute (context7-class), not a current-events one.

## Verification (four layers, from v2)

1. Static: pytest green; manifest coherence; shared-constant single
   source; re-init safety; `tsc --noEmit` on generated `.ts`.
2. Wired-isolated: `allmight init` writes both MCP configs; `python -m
   allmight.mcp.knowledge_server` answers `tools/list` with the two
   intent-named tools; heartbeat fires; mesh hit returns a related doc.
3. Behavioral: free-model A/B/C (does the model auto-call the tool? does
   the hook change the rate?); silent-failure check on an empty index.
4. Cost: tokens/turn with the two tool schemas vs `--pure`.
