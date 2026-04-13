"""Hub-level CLAUDE.md content — the "One For All" constitution.

This is the top-level CLAUDE.md that defines the hub agent's complete worldview.
It lives at ``<hub_root>/.claude/CLAUDE.md`` and is automatically loaded by
Claude Code for every agent session in the hub.

Individual workspace ``.claude/`` directories hold domain-specific context only.
"""

# ---------------------------------------------------------------------------
# The hub CLAUDE.md is assembled from sections.  Each section is a constant
# so the initializer can compose them (and tests can assert on them).
# ---------------------------------------------------------------------------

SECTION_IDENTITY = """\
## All-Might Hub — One For All

You are operating inside an **All-Might hub** — a multi-workspace agent harness
that manages {workspace_count} SMAK workspaces.

Each workspace is a SMAK instance that indexes one domain's source code from
**online** (`$DDI_ROOT_PATH`).  Your job is to build and maintain a knowledge
graph across all managed workspaces through semantic search, enrichment, and
self-improvement.

### Managed Workspaces

{workspace_table}

Use the `detroit-smak` skill to query any workspace.  Use `self-improving` to
audit the hub's health.  Use `enrich` to inject know-how into a workspace.
"""


SECTION_SMAK_PHILOSOPHY = """\
## What is SMAK

**SMAK** (Semantic Mesh Augmented Kernel) is a semantic search engine and vector
store for code.  It indexes source files into FAISS vector indices, enables
natural-language search, and stores per-symbol metadata in **sidecar YAML files**
(`.{filename}.sidecar.yaml`).

**All-Might** sits on top of SMAK as the **active intelligence layer**:

| Layer | Role |
|-------|------|
| **SMAK** | Indexing, vector search, sidecar file I/O |
| **All-Might** | Agent-facing skills, enrichment protocol, graph intelligence, multi-workspace orchestration |

Mental model: `init -> ingest -> search -> enrich -> knowledge graph`
"""


SECTION_ONLINE_VC = """\
## Online vs. Version Control (Global)

This section applies to **ALL workspaces simultaneously**.  Individual workspace
sub-agents do not need to know about online/VC — they just see "source code".

### Three-Layer Model

| Layer | What | Mutable? | Indexed by SMAK? |
|-------|------|----------|-----------------|
| **Online** (`$DDI_ROOT_PATH`) | Latest source — the live working tree | Yes | **Yes** |
| **VC release** (e.g. `rel1.0`) | Frozen snapshot at a tag | No | No (same FAISS) |
| **SOS workspace** (`/users/you/ws_xxx/`) | Personal checkout for editing sidecars | Yes | No |

### Key Rules

- `$DDI_ROOT_PATH` always points to **online** (latest, mutable).
- All SMAK `/search` and `/explain` results come from **online**.
- VC releases are frozen snapshots — they do NOT have separate FAISS indices.
- To verify whether a feature exists in a specific VC release:
  1. `/search` on online to find the relevant files/symbols
  2. Use `sos log` / `sos history` on the file to find the revision log entry
  3. Check if the **same revision log string** exists in the target VC
  4. Same log -> same code -> feature is present in that VC
- See the `sidecar-handling` skill for the full SOS workflow.
"""


SECTION_WORKSPACE_ARCHITECTURE = """\
## Hub Architecture

```
<this folder>/                             <- All-Might hub (Claude Code project root)
|-- .claude/
|   |-- CLAUDE.md                          <- This file (global constitution)
|   |-- skills/
|   |   |-- enrich/SKILL.md               <- Know-how injection into a workspace
|   |   |-- self-improving/SKILL.md       <- Hub-level self-improvement loop
|   |   |-- detroit-smak/SKILL.md         <- Precision strike via sub-agent
|   |   +-- sidecar-handling/SKILL.md     <- SOS-based sidecar update SOP
|   +-- commands/                          <- Agent-invocable commands
|
|-- all-might/config.yaml                  <- Workspace registry
|
+-- workspaces/
    |-- <name>/                            <- One workspace per domain/flow
    |   |-- workspace_config.yaml          <- SMAK index config for this domain
    |   |-- smak/                          <- FAISS databases (local)
    |   |-- .claude/                       <- Domain-specific context (loaded by sub-agent)
    |   |   |-- CLAUDE.md                  <- Domain knowledge, symbol memory
    |   |   +-- skills/                    <- Domain-specific skills (if any)
    |   +-- enrichment/                    <- Power tracker for this workspace
    +-- ...
```

### Two-Layer Context Model

| Layer | Loaded by | Contains |
|-------|-----------|----------|
| **Hub .claude/** | Claude Code automatically (project root) | SMAK philosophy, guardrails, online/VC awareness, skill reference |
| **Workspace .claude/** | Sub-agent (workspace cwd) | Domain-specific symbols, enrichment patterns, flow-specific know-how |

When the `detroit-smak` skill dispatches a sub-agent to a workspace, the sub-agent
runs with `cwd = workspaces/<name>/`.  Claude Code's native `.claude/` loading
picks up the workspace's domain context automatically.  The sub-agent does NOT
need to know about online/VC/SOS — it just works with "source code at these paths".
"""


SECTION_GUARDRAILS = """\
## Guardrails

- **NEVER** directly edit `.sidecar.yaml` files.  Use the `sidecar-handling` skill
  (which goes through SOS) or `/enrich` to modify sidecar content.
- **NEVER** directly edit `workspace_config.yaml`.  Use `allmight init` or
  `allmight config` CLI commands to manage index configuration.
- **NEVER** invent symbol UIDs.  UIDs follow the format `<file_path>::<symbol_name>`.
  Use `/search` or `/explain` to discover valid UIDs.
- **NEVER** operate on a workspace without first loading its `.claude/` context.
  Always use the `detroit-smak` skill for workspace queries — it handles context loading.
- **ALWAYS** use All-Might skills and commands for knowledge graph operations.
  SMAK MCP tools exist but are internal plumbing — agents must not call them directly.
"""


SECTION_SKILL_REFERENCE = """\
## Skill Quick Reference

| Skill | Purpose | Scope |
|-------|---------|-------|
| `detroit-smak` | Precision strike: spawn sub-agent in a workspace, semantic search, return results | Single or multi-workspace |
| `enrich` | Inject domain knowledge into a workspace's `.claude/` layer | Per-workspace |
| `self-improving` | Scan all workspaces, propose hub-level improvements, propagate knowledge | Cross-workspace |
| `sidecar-handling` | Full SOP for updating sidecar files through SOS | Global (any workspace) |
"""


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

MARKER = "<!-- ALL-MIGHT-HUB -->"


def build_hub_claude_md(
    *,
    hub_name: str,
    workspace_count: int,
    workspace_table: str,
) -> str:
    """Assemble the full hub CLAUDE.md content.

    Parameters
    ----------
    hub_name:
        Human-readable name for this hub (e.g. "CAD Flow Knowledge Hub").
    workspace_count:
        Number of managed workspaces.
    workspace_table:
        Markdown table of workspaces, e.g.::

            | Workspace | Path | Description |
            |-----------|------|-------------|
            | stdcell | workspaces/stdcell | DDR5 PHY stdcell |
            | io_phy | workspaces/io_phy | IO PHY interface |
    """
    identity = SECTION_IDENTITY.format(
        workspace_count=workspace_count,
        workspace_table=workspace_table,
    )

    sections = [
        f"# {hub_name}\n",
        MARKER,
        identity,
        SECTION_SMAK_PHILOSOPHY,
        SECTION_ONLINE_VC,
        SECTION_WORKSPACE_ARCHITECTURE,
        SECTION_GUARDRAILS,
        SECTION_SKILL_REFERENCE,
    ]
    return "\n".join(sections)
