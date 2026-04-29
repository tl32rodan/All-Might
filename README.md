# All-Might

Turn your codebase into a knowledge graph that AI agents can search,
learn from, and remember across sessions.

## How It Works

All-Might builds two layers of understanding on top of your code,
each provided by an independent **personality** (more on those below):

**Search & Annotation** — provided by the **corpus keeper**. The agent
searches your code by meaning, not just keywords. Ask "how does
authentication work?" and it finds the relevant modules even if they
never use the word "authentication". As the agent reads and
understands code, it can annotate what each function/class does and
how things connect. Those notes persist across sessions.

**Memory** — provided by the **memory keeper**. The agent remembers
things across sessions: your preferences, past decisions, corrections
you've made. Over time, frequently-used memories stick; forgotten ones
fade naturally.

## Why personalities?

All-Might is built around **personalities** — independent capability
bundles that you install into a project. Today there are two:

- A **corpus keeper** for search and annotation.
- A **memory keeper** for cross-session memory.

Each personality lives in its own folder under `personalities/<name>/`.
That isolation is the point: when you update All-Might, your
customizations to one personality don't get tangled with the other,
and you can read each personality's commands and notes in one place.
Future personalities (review automation, doc generation, …) plug in
the same way without touching the framework's core.

## Setup

```bash
pip install allmight
cd /path/to/your/project
allmight init .                # search + annotation + agent memory
```

Then open the folder in **Claude Code** or **OpenCode**.

## Project layout after `allmight init`

```
my-project/
├── AGENTS.md                ← what the agent can do
├── MEMORY.md                ← what the agent remembers
├── .opencode/               ← Claude Code / OpenCode picks this up
│   ├── commands/            ← /search, /remember, …
│   ├── plugins/             ← memory hooks
│   └── skills/              ← /sync
└── personalities/
    ├── my-project-corpus/   ← corpus keeper data + commands
    └── my-project-memory/   ← memory keeper data + commands
```

Everything under `.opencode/` is composed automatically — each
personality contributes its own commands and plugins, and All-Might
links them in. Your customizations to either side stay isolated under
their own `personalities/<name>/` folder, so updates won't tread on
your work.

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
| **After big changes** | "Re-run /ingest" |

Everything else is automatic.

## Commands

These are slash commands you can type (or just ask the agent in
natural language — it knows what to do).

| Command | Plain English |
|---------|--------------|
| `/search` | "Search for ..." |
| `/enrich` | "Annotate this symbol" |
| `/ingest` | "Build the search index" |
| `/remember` | "Remember that ..." |
| `/recall` | "What do you know about ...?" |
| `/reflect` | "Review and tidy up what you've learned" |

## Glossary

| Term | What it means |
|------|--------------|
| **Personality** | A capability bundle All-Might installs (today: a corpus keeper for search/annotation, a memory keeper for cross-session memory). Each has its own folder under `personalities/<name>/`. |
| **Knowledge graph** | The accumulated understanding: code annotations + their connections |
| **Annotation** (enrichment) | A note describing what a function/class does and what it relates to |
| **Corpus** | A searchable index of your source code, built by `/ingest` |
| **Memory** | Agent's persistent knowledge across sessions (preferences, decisions, facts) |

## Updating

Re-running `allmight init` is safe. New templates are staged into
`.allmight/templates/` instead of overwriting your customized files.
Tell the agent "run /sync" and it merges your version with the new
template intelligently.

```bash
pip install --upgrade allmight
allmight init .
```

**Already had `.opencode/` before installing All-Might?** That's fine.
`allmight init` never overwrites a `.opencode/` file you authored — it
preserves your version, lists the skipped paths in
`.allmight/templates/conflicts.yaml`, and `/sync` walks you through
each one. The same goes for an existing `opencode.json`: your
`$schema` and pinned plugin versions are left as-is.

Use `--force` only when you want to overwrite everything, including
your own customizations:

```bash
allmight init . --force
```

**Note:** `MEMORY.md` is never overwritten — it contains accumulated
agent knowledge (project map, user preferences, key facts). A version
update only touches skills, commands, and hooks.

## Combining Projects

Merge knowledge from another All-Might project into yours:

```bash
allmight merge /path/to/other-project
```

New workspaces are copied directly. If both projects have a workspace
with the same name, it's saved as `<name>.incoming/` for the agent to
resolve via `/sync`.

Options:
- `--workspace pll` — only merge specific workspaces
- `--no-memory` — skip merging memory files
- `--dry-run` — preview what would happen

## Compatibility

| Tool | Status |
|------|--------|
| **Claude Code** | First-class support |
| **OpenCode** | First-class support |

## License

MIT
