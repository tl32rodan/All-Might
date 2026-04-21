# All-Might Development

## After Code Changes

After modifying initializer, skill templates, commands, or memory init:

1. Run tests: `PYTHONPATH=src python -m pytest tests/`
2. If the change touches code that generates TypeScript (e.g. OpenCode
   plugins under `memory/initializer.py::_opencode_plugin_map`), also
   type-check the generated output:
   `cd /tmp/demo && allmight init . && tsc --noEmit .opencode/plugins/*.ts`
   Python tests only verify strings written — they cannot catch
   wrong-shape API calls in the generated `.ts`.

## Project Structure

```
All-Might/                          ← This repo (the framework)
├── src/allmight/                    ← Framework source code
│   ├── detroit_smak/               ← Scanner + Initializer (generates workspace)
│   ├── memory/                     ← Agent memory system (L1/L2/L3)
│   ├── bridge/                     ← SMAK CLI subprocess wrapper (internal)
│   ├── config/                     ← config.yaml manager
│   ├── core/                       ← Domain models + protocols
│   ├── enrichment/                 ← Enrichment policy (advisory)
│   ├── one_for_all/                ← Skill template generator
│   ├── hub/                        ← Multi-workspace hub templates
│   └── cli.py                      ← CLI entry point (init only)
├── tests/                          ← Test suite
└── docs/
```

## Key Files to Know

| File | What it generates |
|------|-------------------|
| `detroit_smak/initializer.py` | AGENTS.md, knowledge_graph/, .opencode/skills, .opencode/commands |
| `one_for_all/templates/skill-base.md.j2` | The one-for-all SKILL.md |
| `memory/initializer.py` | MEMORY.md (L1), understanding/ (L2), journal/ (L3), /remember /recall |
| `detroit_smak/scanner.py` | Detects languages, frameworks, proposes indices |

## Architecture Layers

| Layer | What | For whom |
|-------|------|----------|
| README.md | How to talk to the agent | Human |
| AGENTS.md (in workspace) | What capabilities exist | Agent (high-level) |
| Skills/Commands | How to execute operations (smak CLI) | Agent (low-level) |
| CLI | `allmight init` only | Human (bootstrap) |

---

## Design Philosophy

### 1. What All-Might Generates (Target Workspace Structure)

An All-Might project manages **one knowledge graph** across **multiple
SMAK workspaces** (corpora). Example with 3 EDA flows:

```
my-chip-project/                          ← One All-Might project
├── AGENTS.md                             ← Agent: WHAT can I do (high-level)
│
├── .opencode/
│   ├── skills/
│   │   └── one-for-all/SKILL.md          ← Agent: HOW to operate (low-level)
│   ├── commands/
│   │   ├── search.md                     ← /search operational guide
│   │   ├── enrich.md                     ← /enrich operational guide
│   │   ├── ingest.md                     ← /ingest operational guide
│   │   ├── remember.md                   ← /remember (memory)
│   │   └── recall.md                     ← /recall (memory)
│   ├── plugins/                          ← TypeScript plugins (L1 loader, nudge)
│   └── opencode.json                     ← OpenCode config ($schema + plugins)
│
├── MEMORY.md                             ← L1: project map + user prefs (plugin-loaded)
│
│
├── memory/                               ← Shared: agent memory across ALL workspaces
│   ├── config.yaml                       ← Memory settings
│   ├── understanding/                    ← L2: per-corpus knowledge
│   │   ├── stdcell.md
│   │   └── pll.md
│   ├── journal/                          ← L3: append-only text files
│   │   ├── stdcell/
│   │   └── general/
│   └── store/                            ← L3: SMAK vector index of journal/
│
└── knowledge_graph/                      ← SMAK workspaces (each independent)
    ├── stdcell/
    │   ├── config.yaml                   ← SMAK config (indices: rtl, verif, constraints)
    │   └── store/                        ← SMAK search data
    ├── io_phy/
    │   ├── config.yaml                   ← SMAK config (indices: rtl, verif)
    │   └── store/
    └── pll/
        ├── config.yaml                   ← SMAK config (indices: source_code, tests)
        └── store/
```

**SMAK indexes source files in-place** — no files are ever copied into
the All-Might project. Only the vector index (`store/`) and SMAK config
(`config.yaml`) live inside `knowledge_graph/` workspaces.

**Sidecar files** (`.sidecar.yaml`) live beside the source code they describe
(at `$DDI_ROOT_PATH/...`), NOT inside the All-Might project.

### 2. SRP: Three Layers of Agent Documentation

| Layer | Audience | Abstraction | Contains |
|-------|----------|-------------|----------|
| **AGENTS.md** | Agent | High-level WHAT | Capabilities, commands, "see skill for details" |
| **Skills/Commands** | Agent | Low-level HOW | SMAK CLI commands, YAML schemas, troubleshooting |
| **README.md** | Human | Conversational | "Tell the agent to search for..." |

- **AGENTS.md** knows about `/search`, `/enrich` but NOT about `smak search --config ...`
- **Skills** know about SMAK internals but never expose them to the human user
- **README.md** doesn't mention SMAK, sidecars, or YAML — only natural-language examples

### 3. config.yaml: Only SMAK Owns It

There is **no All-Might-level config.yaml**.  Workspaces are discovered
by scanning `knowledge_graph/*/config.yaml` — no registry needed.

**SMAK config.yaml** (per workspace at `knowledge_graph/<name>/config.yaml`):
```yaml
indices:
  - name: rtl
    uri: ./store/rtl
    description: "RTL design files (Verilog, SystemVerilog)"
    paths:
      - $DDI_ROOT_PATH/stdcell/rtl
    path_env: DDI_ROOT_PATH
  - name: verif
    uri: ./store/verif
    description: "Verification testbenches"
    paths:
      - $DDI_ROOT_PATH/stdcell/verif
```

**Rule**: config.yaml is SMAK's concern.  All-Might discovers workspaces
by their directory structure, not by a registry file.

### 4. Shared vs Per-Workspace

| Component | Scope | Why |
|-----------|-------|-----|
| `MEMORY.md` | Project-wide | L1 cache: project map, user prefs (hook-loaded) |
| `memory/understanding/` | Project-wide | L2: per-corpus knowledge (agent reads/writes) |
| `memory/journal/` | Project-wide | L3: searchable log (SMAK indexed) |
| `.opencode/skills/` | Project-wide | One skill teaches agent about all workspaces |
| `.opencode/commands/` | Project-wide | One set of commands for the whole project |
| `knowledge_graph/<name>/config.yaml` | Per-workspace | Each SMAK DB has its own index config |
| `knowledge_graph/<name>/store/` | Per-workspace | Each SMAK DB has its own search data |
| Sidecar files | Per-source-file | Live beside source code (external) |

### 5. CLI: Bootstrap Only

The `allmight` CLI does ONE thing: `allmight init`.
Everything else is agent-driven through skills and commands.

```
allmight init .                  → creates the project structure (includes memory)
allmight memory init             → re-initialize memory on existing project
```

The agent calls `smak` CLI directly (taught by skills), NOT `allmight` wrappers.

---

## Discipline When Generating Third-Party Integrations

The initializer writes files that execute in foreign runtimes (OpenCode
plugins, MCP servers, CI configs). The Python test suite verifies **what
strings we wrote**, not **whether the file works at runtime** — so
string-presence assertions can pass while the generated code is silently
broken. Rules below came from real regressions; break them and the same
bugs come back.

- **Read a working example's source before writing.** Doc summaries hide
  signatures. For an OpenCode plugin, read a published one on GitHub
  (`oh-my-opencode`, `opencode-supermemory`) and the
  `@opencode-ai/plugin` type definitions — not a blog post.
- **Distinguish event subscription from hook registration.** OpenCode
  has two separate mechanisms: the global `event:` handler observes the
  bus; top-level keys like `"chat.message"` and
  `"experimental.session.compacting"` are **hooks with input/output
  contracts**. Never place a hook name inside the event handler's
  if-chain.
- **Tests must include negative assertions.** `assert "chat.message"
  in content` is useless on its own. Assert the exact signature
  (`'"chat.message": async (input: any, output: any)'`), the correct
  injection path (`output.parts.unshift`), and the absence of the
  broken shape (`"msg.content =" not in content`).
- **Type-check generated TypeScript at least once** (see *After Code
  Changes* above). A one-shot `tsc --noEmit` catches wrong-shape calls
  the Python suite cannot see.
- **If official docs are unreachable (403/404/503), say so explicitly**
  and fetch a real implementation from GitHub. Do not silently degrade
  to secondary sources and pretend the shape was verified.
- **Verify the API on one file before propagating to many.** If three
  files share an unverified assumption, they break together — and the
  tests pass in all three.
