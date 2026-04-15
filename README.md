# All-Might

Active Knowledge Graph Framework for AI coding agents.

All-Might turns your codebase into a searchable, enrichable knowledge graph
that agents can query, learn from, and build upon across sessions.

## What It Does

```
init  →  /ingest  →  /search  →  /enrich  →  knowledge graph
                                     ↑              ↓
                               agent learns    agent remembers
```

- **Semantic search** — natural-language queries across your codebase
- **Symbol enrichment** — agents annotate code with intent and relationships
- **Knowledge graph** — visualize how code connects (communities, god nodes, paths)
- **Agent memory** — three-layer persistent memory across sessions (optional)

## Quick Start

### 1. Install

```bash
pip install allmight
```

### 2. Initialize a workspace

```bash
cd /path/to/your/project
allmight init .
```

This creates `config.yaml`, corpora definitions, and agent skills in `.claude/`.

To also enable agent memory (recommended for long-running projects):

```bash
allmight init . --with-memory
```

### 3. Open in Claude Code or OpenCode

```bash
# Claude Code
claude

# OpenCode
opencode
```

All-Might skills auto-load. The agent immediately has access to the knowledge
graph commands.

### 4. Build the search index

Inside the coding agent, run:

```
/ingest
```

This builds the search corpus from your source code. You only need to re-run
it when source files change significantly.

### 5. Start exploring

```
/search "authentication handler"
/enrich --file src/auth.py --symbol "AuthHandler" --intent "Validates JWT tokens"
/status
```

## Daily Workflow

### For the human

| When | Do | Why |
|------|-----|-----|
| **First time** | `allmight init .` | Bootstrap the workspace |
| **First time** | `/ingest` | Build search index |
| **When you learn** | `/enrich` | Grow the knowledge graph |
| **Periodically** | `/status` | Check progress |
| **Periodically** | `/consolidate` | Convert session notes to facts (if memory enabled) |
| **When structure changes** | `/ingest` | Rebuild the search index |

### For the agent (automatic)

The agent reads `CLAUDE.md` and the `one-for-all` skill on startup.
It knows how to search, enrich, remember, and recall.

## Commands

### Core (always available)

| Command | Purpose |
|---------|---------|
| `/search <query>` | Semantic search across the codebase |
| `/enrich` | Annotate a symbol with intent and/or relations |
| `/ingest` | Rebuild the search corpus from source files |
| `/status` | Show enrichment coverage and system health |

### Memory (requires `--with-memory`)

| Command | Purpose |
|---------|---------|
| `/remember` | Record an observation during this session |
| `/recall` | Search past memories across all layers |
| `/consolidate` | Convert session episodes into lasting facts |

## Architecture

```
your-project/
├── config.yaml              # Corpus definitions
├── CLAUDE.md                 # Agent instructions (auto-generated)
├── AGENTS.md                 # → CLAUDE.md symlink (OpenCode compat)
├── enrichment/
│   └── tracker.yaml          # Power Level metrics + history
├── panorama/                 # Graph exports (JSON, Mermaid)
├── smak/                     # Search index data (internal)
├── memory/                   # Agent memory (if --with-memory)
│   ├── config.yaml           # Memory settings + store definitions
│   ├── working/MEMORY.md     # Always-in-context facts
│   ├── episodes/             # Session history (append-only)
│   ├── semantic/             # Consolidated facts with decay
│   └── store/                # Memory search data (internal)
└── .claude/
    ├── skills/               # Auto-loaded agent skills
    └── commands/             # Slash commands
```

## Key Concepts

**Corpus** — A searchable index of source code. Created by `/ingest`, queried
by `/search`. You can have multiple corpora for different parts of your
project (source, tests, docs).

**Sidecar** — A `.{filename}.sidecar.yaml` file that stores enrichment
metadata (intent, relations) alongside the source file it describes.
Never edit sidecars by hand — use `/enrich`.

**Power Level** — A coverage metric showing what percentage of symbols
have been enriched. Higher is better, but focus on entry points and
complex logic first.

**Symbol UID** — The unique identifier for a code symbol:
`<file_path>::<symbol_name>` (e.g., `src/auth.py::AuthHandler.validate`).

## Agent Memory (Optional)

Enable with `allmight init --with-memory` or `allmight memory init`.

Three-layer architecture inspired by cognitive science:

| Layer | What | When |
|-------|------|------|
| **Working Memory** | `MEMORY.md` — always in context | User preferences, environment facts, active goals |
| **Episodic Memory** | Session records | Auto-recorded at session end |
| **Semantic Memory** | Consolidated facts | Created by `/memory-consolidate` from episodes |

Memory features Ebbinghaus decay curves — frequently accessed memories
persist longer, unused ones fade naturally.

## Compatibility

| Tool | Support |
|------|---------|
| Claude Code | First-class (reads `.claude/` natively) |
| OpenCode | Supported via `AGENTS.md` symlink + `.claude/` fallback |

## License

MIT
