# All-Might

<!-- ALL-MIGHT -->
## All-Might: Active Knowledge Graph

This project has an **All-Might knowledge graph** — the agent can search
code by meaning, annotate what it learns, and remember across sessions.

### Capabilities

| Command | What it does |
|---------|-------------|
| `/search <query>` | Search code by meaning (not just keywords) |
| `/enrich` | Annotate a symbol — record what it does and what it relates to |
| `/ingest` | Build or rebuild the search index from source files |
| `/status` | Show how much of the codebase has been annotated |

### Concepts

- **Annotation** = a note on a code symbol (function, class) describing its
  purpose and connections. Stored in sidecar files beside the source code.
- **Corpus** = a searchable index built from source files. Created by `/ingest`.
- **Power Level** = percentage of symbols that have annotations. Higher = better.

### How to learn the details

The `one-for-all` skill (auto-loaded in `.claude/skills/`) contains the
complete operational guide: search engine commands, annotation workflow,
sidecar file format, and troubleshooting.

### Getting Started

1. `/ingest` — build the search index (first time)
2. `/search "query"` — explore the codebase
3. `/enrich` — annotate symbols as you learn them
4. `/status` — track progress

<!-- ALL-MIGHT-MEMORY -->
## Agent Memory

The agent can **remember things across sessions**: your preferences,
past decisions, corrections, and learned patterns.

### What the agent can do

| Command | What it does |
|---------|-------------|
| `/remember` | Save an observation from this session |
| `/recall` | Search what the agent remembers from past sessions |
| `/consolidate` | Turn raw session notes into lasting knowledge |

### How it works

- **Session notes** — each session's observations are recorded as an episode
- **Lasting facts** — `/consolidate` extracts recurring patterns into permanent knowledge
- **Natural decay** — frequently recalled memories persist; forgotten ones fade

The `one-for-all` skill has the complete operational guide.
