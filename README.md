# All-Might

Turn your codebase into a knowledge graph that AI agents can search,
learn from, and remember across sessions.

## How It Works

All-Might builds three layers of understanding on top of your code:

**Search** — The agent can search your code by meaning, not just keywords.
Ask "how does authentication work?" and it finds the relevant modules,
even if they never use the word "authentication".

**Annotation** — As the agent reads and understands code, it writes down
what each function/class does and how things connect. These notes persist
across sessions, so the next agent (or the same one later) starts with
that understanding already built.

**Memory** (optional) — The agent remembers things across sessions:
your preferences, past decisions, corrections you've made. Over time,
frequently-used memories stick; forgotten ones fade naturally.

## Setup

```bash
pip install allmight
cd /path/to/your/project
allmight init .                # search + annotation
allmight init . --with-memory  # + agent memory (recommended)
```

Then open the folder in **Claude Code** or **OpenCode**.

## Talking to the Agent

### Search the code

> "Search for how authentication works"
>
> "What does the AuthHandler class do?"
>
> "Find all error handling patterns"

### Build understanding

> "Annotate the AuthHandler — write down what it does and why"
>
> "Link the login function to its test file"
>
> "What's the annotation coverage so far?"

Each annotation makes future searches and questions more useful.

### Remember things (if memory enabled)

> "Remember that I prefer TypeScript over JavaScript"
>
> "What did we discuss about the auth module last time?"
>
> "Consolidate what you've learned from recent sessions"

## What You Need to Do

| When | Tell the agent |
|------|----------------|
| **First time** | "Run /ingest to build the search index" |
| **Exploring** | Ask questions about the code |
| **Agent learns something** | "Annotate this with what you just learned" |
| **Check progress** | "Show me the status" |
| **After big changes** | "Re-run /ingest" |
| **Weekly (memory)** | "Consolidate recent sessions" |

Everything else is automatic.

## Commands

These are slash commands you can type (or just ask the agent in
natural language — it knows what to do).

| Command | Plain English |
|---------|--------------|
| `/search` | "Search for ..." |
| `/enrich` | "Annotate this symbol" |
| `/ingest` | "Build the search index" |
| `/status` | "How healthy is the knowledge graph?" |
| `/remember` | "Remember that ..." |
| `/recall` | "What do you know about ...?" |
| `/consolidate` | "Turn recent session notes into lasting knowledge" |

## Glossary

| Term | What it means |
|------|--------------|
| **Knowledge graph** | The accumulated understanding: code annotations + their connections |
| **Annotation** (enrichment) | A note describing what a function/class does and what it relates to |
| **Corpus** | A searchable index of your source code, built by `/ingest` |
| **Power Level** | Percentage of code symbols that have been annotated |
| **Memory** | Agent's persistent knowledge across sessions (preferences, decisions, facts) |
| **Consolidation** | Turning raw session notes into lasting facts |

## Compatibility

| Tool | Status |
|------|--------|
| **Claude Code** | First-class support |
| **OpenCode** | Supported (via `AGENTS.md` symlink) |

## License

MIT
