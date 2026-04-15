---
name: one-for-all
description: All-Might knowledge guide. Project structure, corpus reference, enrichment protocol, key symbols, and Power Level. Auto-loaded when agent needs to understand the project.
---

# One For All — All-Might

> **All-Might** is the active knowledge graph layer for this project.
> It manages SMAK workspaces under `knowledge_graph/`, shared enrichment,
> and agent memory. Use the commands below — Do NOT hand-edit sidecar or
> config YAML files directly.

## Project Overview

- **Name**: All-Might
- **Languages**: Python
- **Frameworks**: Python

### Directory Structure

- `src/` — Source code

## SMAK Workspaces

Workspaces live under `knowledge_graph/`. Discover them:
```bash
ls knowledge_graph/
```

Each workspace has its own `config.yaml` (indices) and `store/` (search data).

## SMAK CLI Reference

All commands use `--config <workspace>/config.yaml`. Add `--json` for
machine-readable output.

**Search** — find code by semantic meaning:
```bash
smak search "authentication handler" --config knowledge_graph/main/config.yaml --index source_code --top-k 5 --json
smak search-all "error handling" --config knowledge_graph/main/config.yaml --top-k 3 --json
smak lookup "src/auth.py::AuthHandler" --config knowledge_graph/main/config.yaml --index source_code --json
```

**Enrich** — annotate a symbol with intent and relations:
```bash
smak enrich --config knowledge_graph/main/config.yaml --index source_code \
    --file src/auth.py --symbol "AuthHandler.validate" \
    --intent "Validates JWT tokens and extracts user claims"

smak enrich --config knowledge_graph/main/config.yaml --index source_code \
    --file src/auth.py --symbol "AuthHandler.validate" \
    --relation "src/models.py::User" --bidirectional
```

**Ingest** — rebuild the vector index from source files:
```bash
smak ingest --config knowledge_graph/main/config.yaml                    # all corpora
smak ingest --config knowledge_graph/main/config.yaml --index source_code  # specific corpus
```

**Diagnostics**:
```bash
smak health --config knowledge_graph/main/config.yaml --json
smak describe --config knowledge_graph/main/config.yaml --json
smak stats --config knowledge_graph/main/config.yaml --json
```

## Sidecar Files

Sidecar files store enrichment metadata beside the source file they describe.
They are named `.{source_filename}.sidecar.yaml`.

```yaml
# Example: .auth.py.sidecar.yaml  (beside src/auth.py)
symbols:
  - name: "AuthHandler.validate"
    intent: "Validates JWT tokens and extracts user claims"
    relations:
      - "src/models.py::User"
      - "tests/test_auth.py::test_validate"
```

**Important rules:**
- NEVER edit .sidecar.yaml files by hand — always use `smak enrich`
- UIDs follow the format `<file_path>::<symbol_name>`
- Use dot notation for nested symbols: `ClassName.method_name`
- The wildcard `*` means the entire file: `path/to/file.py::*`
- Do NOT invent UIDs — use `smak search` to discover valid ones

## Commands

| Command | Purpose |
|---------|---------|
| `/search <query>` | Search the codebase semantically |
| `/enrich` | Annotate a symbol with intent and relations |
| `/ingest` | Rebuild the search corpus from source files |
| `/status` | Show enrichment coverage and system health |

## Getting Started

1. `/ingest` — build the search index (first time setup)
2. `/search "query"` — explore the codebase
3. `/enrich` — annotate symbols as you learn them
4. `/status` — track enrichment progress

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
