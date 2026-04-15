# All-Might

Turn your codebase into a knowledge graph that AI agents can search,
learn from, and remember across sessions.

## Setup

```bash
pip install allmight
cd /path/to/your/project
allmight init .                # knowledge graph only
allmight init . --with-memory  # + agent memory (recommended)
```

Then open the folder in **Claude Code** or **OpenCode** and start talking.

## Talking to the Agent

### Explore

> "Search for how authentication works"
>
> "What does the AuthHandler class do?"
>
> "Find all error handling patterns in this project"

The agent uses `/search` to find code by meaning, then explains what it found.

### Enrich

> "Annotate the AuthHandler with its purpose"
>
> "Link the login function to its test file"
>
> "Enrich the top 5 most important entry points"

The agent uses `/enrich` to record what code does and how it connects.
This builds the knowledge graph over time.

### Track Progress

> "How much of the codebase is annotated?"
>
> "Show me the knowledge graph health"

The agent uses `/status` to report enrichment coverage.

### Remember (if memory enabled)

> "Remember that the user prefers TypeScript over JavaScript"
>
> "What did we discuss about the auth module last time?"
>
> "Consolidate what you've learned from recent sessions"

The agent uses `/remember`, `/recall`, and `/consolidate` to persist
knowledge across sessions.

## What You Need to Do

| When | Tell the agent |
|------|----------------|
| **First time** | "Run /ingest to build the search index" |
| **Exploring** | Ask questions about the code |
| **Learning something** | "Enrich this symbol with what you just learned" |
| **Checking progress** | "Show me the status" |
| **Weekly (memory)** | "Consolidate recent sessions" |
| **After big changes** | "Re-run /ingest" |

Everything else is automatic. The agent reads its skills on startup and
knows how to operate the knowledge graph.

## Commands

| Command | What to tell the agent |
|---------|----------------------|
| `/search` | "Search for ..." |
| `/enrich` | "Annotate this symbol" |
| `/ingest` | "Build/rebuild the search index" |
| `/status` | "Show knowledge graph health" |
| `/remember` | "Remember that ..." |
| `/recall` | "What do you remember about ...?" |
| `/consolidate` | "Consolidate recent sessions" |

## Compatibility

| Tool | Status |
|------|--------|
| **Claude Code** | First-class support |
| **OpenCode** | Supported (via `AGENTS.md` symlink) |

## License

MIT
