# All-Might Development

## After Code Changes

After modifying initializer, skill templates, commands, or memory init:

1. Run tests: `PYTHONPATH=src python -m pytest tests/`
2. If the change touches code that generates TypeScript (e.g. OpenCode
   plugins under
   `personalities/memory_keeper/initializer.py::_opencode_plugin_map`),
   also type-check the generated output:
   `cd /tmp/demo && allmight init . && tsc --noEmit .opencode/plugins/*.ts`
   Python tests only verify strings written — they cannot catch
   wrong-shape API calls in the generated `.ts`.

## Planning Workflow

When the task requires designing before coding:

- **Write plan files incrementally to disk via the Edit tool.** Do
  not stream a long single-shot response. Stream-idle timeouts have
  lost whole plans before; write each section, save, then continue.
- **Confirm core premises before drafting.** Naming choices,
  deprecated concepts (`detroit_smak` is deprecated), and
  non-negotiable rules (no Composer pattern; one `Personality`
  instance per template by default) — surface assumptions and ask
  for confirmation in 30 seconds, instead of redrafting after
  rejection.
- **Close every design session with a written artifact.** Plan
  files and CLAUDE.md additions both count; chat memory does not.
  Context bled across sessions when this was skipped.

## Project Structure

```
All-Might/                          ← This repo (the framework)
├── src/allmight/                    ← Framework source code
│   ├── personalities/               ← Built-in personality templates
│   │   ├── corpus_keeper/          ← Scanner + KG initializer + /search /enrich /ingest /sync
│   │   └── memory_keeper/          ← Agent memory L1/L2/L3 + /remember /recall /reflect
│   ├── bridge/                     ← SMAK CLI subprocess wrapper (internal)
│   ├── config/                     ← config.yaml manager
│   ├── core/                       ← Domain models + personalities framework
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
| `core/personalities.py` | Personality framework: Template, Personality, registry, compose |
| `personalities/corpus_keeper/__init__.py` | TEMPLATE (cli_options for --sos, --writable) |
| `personalities/corpus_keeper/initializer.py` | AGENTS.md, knowledge_graph/, instance commands/skills |
| `personalities/memory_keeper/__init__.py` | TEMPLATE (no cli_options) |
| `personalities/memory_keeper/initializer.py` | MEMORY.md (L1), understanding/ (L2), journal/ (L3), /remember /recall |
| `personalities/corpus_keeper/scanner.py` | Detects languages, frameworks, proposes indices |
| `one_for_all/templates/skill-base.md.j2` | The one-for-all SKILL.md |

## Personality Platform Conventions

These rules are non-negotiable; proposals that violate them have been
rejected before and will be rejected again.

- **`corpus_keeper` is the canonical name** for the corpus-side
  personality. The legacy name `detroit_smak` is **deprecated** —
  do not re-introduce it in proposals, skill bodies, plugin code,
  or test names.
- **Two-tier model.** Every capability is a `PersonalityTemplate`
  (the *kind* — registered as a module-level `TEMPLATE` constant
  inside `src/allmight/personalities/<name>/__init__.py`) plus
  zero-or-more `Personality` instances (one per project, default
  name `f"{manifest.name}-{template.short_name}"`). The framework
  instantiates the instance; the template never instantiates itself.
- **No Composer pattern.** Templates do not mix runtime state
  across personalities, do not share helpers via mutable globals,
  and do not coordinate at install time. Each `template.install`
  runs in isolation and writes only into its own
  `personalities/<name>/`. If two templates need the same data,
  they each compute it from `InstallContext`; cross-template state
  flows through the file system, never through process memory.
- **Composition is build-time.** The registry walks each instance's
  `skills/`, `commands/`, `plugins/` after `install` and creates
  relative symlinks at `.opencode/<kind>/<basename>`. Once written,
  OpenCode resolves them on file open — no in-process registry
  mediates command dispatch at runtime.

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

An All-Might project is composed of **personality instances**. Each
instance owns a directory under `personalities/<name>/` containing
both its agent surface (skills/commands/plugins) and its data dir
(`knowledge_graph/` for corpus, `memory/` for memory). The top-level
`.opencode/` is **composed** from each instance via symlinks.

Example with 3 EDA flows:

```
my-chip-project/                          ← One All-Might project
├── AGENTS.md                             ← root entry point (corpus-flavoured)
├── MEMORY.md                             ← L1: project map + user prefs (plugin-loaded)
│
├── .opencode/                            ← COMPOSED by registry (symlinks)
│   ├── opencode.json                     ← $schema only (init scaffold)
│   ├── package.json                      ← @opencode-ai/plugin (init scaffold)
│   ├── skills/sync → ../personalities/<corpus>/skills/sync
│   ├── commands/
│   │   ├── search.md  → ../personalities/<corpus>/commands/search.md
│   │   ├── enrich.md  → …
│   │   ├── ingest.md  → …
│   │   ├── sync.md    → …
│   │   ├── remember.md→ ../personalities/<memory>/commands/remember.md
│   │   ├── recall.md  → …
│   │   └── reflect.md → …
│   └── plugins/{memory-load.ts, …}       ← symlinks into <memory> instance
│
├── personalities/                        ← Each subdir is one instance
│   ├── my-chip-project-corpus/           ← default name = f"{manifest.name}-corpus"
│   │   ├── skills/sync/SKILL.md
│   │   ├── commands/{search,enrich,ingest,sync}.md
│   │   └── knowledge_graph/              ← SMAK workspaces (each independent)
│   │       ├── stdcell/{config.yaml, store/}
│   │       ├── io_phy/{config.yaml, store/}
│   │       └── pll/{config.yaml, store/}
│   └── my-chip-project-memory/           ← default name = f"{manifest.name}-memory"
│       ├── commands/{remember,recall,reflect}.md
│       ├── plugins/{memory-load,remember-trigger,todo-curator,trajectory-writer,usage-logger}.ts
│       └── memory/
│           ├── config.yaml
│           ├── smak_config.yaml
│           ├── understanding/{stdcell.md, pll.md}    ← L2
│           ├── journal/{stdcell/, general/}          ← L3
│           └── store/                                 ← L3 SMAK vector index
│
└── .allmight/
    ├── personalities.yaml                ← Records installed instances
    ├── mode                              ← read-only | writable
    └── templates/                        ← Re-init staging (when applicable)
```

**SMAK indexes source files in-place** — no files are ever copied into
the All-Might project. Only the vector index (`store/`) and SMAK config
(`config.yaml`) live inside each instance's `knowledge_graph/`
workspaces.

**Sidecar files** (`.sidecar.yaml`) live beside the source code they describe
(at `$DDI_ROOT_PATH/...`), NOT inside the All-Might project.

`allmight init` is **idempotent and safe in pre-populated
directories.** Files that carry an All-Might marker
(`ALLMIGHT_MARKER_MD`, `_TS`, `_YAML`) are auto-replaced; files you
authored at e.g. `.opencode/commands/search.md` are preserved
untouched and surfaced via `.allmight/templates/conflicts.yaml` for
`/sync` to resolve. `$schema` in `opencode.json` and pinned versions
in `package.json` are never overwritten — both writers use
`setdefault` semantics.

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
by scanning `personalities/<corpus>/knowledge_graph/*/config.yaml` —
no registry needed for workspaces. (Personality *instances* are
recorded in `.allmight/personalities.yaml` so `allmight status`
knows what's installed; that file is the registry of *kinds*, not
of SMAK workspaces.)

**SMAK config.yaml** (per workspace at
`personalities/<corpus>/knowledge_graph/<name>/config.yaml`):
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

### 4. Shared vs Per-Workspace vs Per-Instance

| Component | Scope | Why |
|-----------|-------|-----|
| `MEMORY.md` | Project-wide root | L1 cache: project map, user prefs (plugin-loaded) |
| `AGENTS.md` | Project-wide root | High-level WHAT the agent can do |
| `personalities/<m>/memory/understanding/` | Per memory instance | L2: per-corpus knowledge |
| `personalities/<m>/memory/journal/` | Per memory instance | L3: searchable log (SMAK indexed) |
| `.opencode/skills/` | Composed (symlinks) | Each instance contributes its skills |
| `.opencode/commands/` | Composed (symlinks) | Each instance contributes its commands |
| `.opencode/plugins/` | Composed (symlinks) | Each instance contributes its plugins |
| `personalities/<c>/knowledge_graph/<name>/config.yaml` | Per-workspace | Each SMAK DB has its own index config |
| `personalities/<c>/knowledge_graph/<name>/store/` | Per-workspace | Each SMAK DB has its own search data |
| `.allmight/personalities.yaml` | Project-wide | Lists installed personality instances |
| Sidecar files | Per-source-file | Live beside source code (external) |

### 5. CLI: Bootstrap Only

The `allmight` CLI does ONE thing: `allmight init`.
Everything else is agent-driven through skills and commands.

```
allmight init .                  → discovers personalities, installs each, composes .opencode/
allmight memory init             → re-initialize memory on existing project
```

The agent calls `smak` CLI directly (taught by skills), NOT `allmight` wrappers.

**`cli.py` knows nothing template-specific.** Per-template flags
(`--sos`, `--writable`) are contributed by their template's
`cli_options` and registered on the `init` Click command at startup.
Each template extracts what it needs from `Personality.options` inside
its `install` callable — `cli.py` never reads them. To add a flag:
append a `CliOption(...)` to the right template's `__init__.py` and it
shows up in `allmight init --help` automatically.

---

## Interface Isolation & Clean-Code Rules

Each rule below is enforceable by reading a diff. Violating a rule is
a regression even if tests pass.

- **`cli.py` is closed.** Touching `src/allmight/cli.py` to
  special-case a template is a regression. New flags belong in
  `template.cli_options`; new install behaviour belongs in
  `template.install`; new runtime state belongs inside the
  template, not in `cli.py`. The only universal concerns that live
  there are `--force`, scaffold writing
  (`write_init_scaffold`), and registry persistence
  (`write_registry`).
- **`core/` is closed against templates.** Files under
  `src/allmight/core/` must not import from
  `src/allmight/personalities/*`. The dependency arrow points one
  way: templates depend on core, never the other direction. If a
  utility is general enough to be shared, lift it into core; do not
  reach back into a template.
- **A template owns its directory, nothing else.** Writes outside
  `personalities/<name>/` are limited to four root targets:
  `AGENTS.md`, `MEMORY.md`, `.allmight/personalities.yaml`, and the
  staging directory `.allmight/templates/...`. Composition symlinks
  under `.opencode/` are placed by `core.personalities.compose`,
  not by the template itself. Any new write target must be an
  explicit, documented exception in this section.
- **Conflict resolution lives in `core/personalities.compose`.**
  Templates do not detect or stage their own conflicts; they just
  declare what they want to write inside their instance dir.
  Centralising this keeps `/sync`'s mental model uniform — one
  manifest at `.allmight/templates/conflicts.yaml`, one set of
  resolution rules.
- **Markers are the contract for "this file is mine".** Every
  generated file *must* carry an `ALLMIGHT_MARKER_*` token (see
  `core/markers.py`). Files without a marker are treated as
  user-authored on re-init and preserved. **Skipping the marker is
  a silent data-loss bug** — the file gets clobbered or, worse,
  silently divorced from re-init flow.
- **When in doubt: add a flag, not a template.** A new template is
  justified only when the capability has its own data dir, its own
  skills/commands, and a meaningful uninstall semantics.
  Otherwise, extend an existing template's `cli_options` or its
  `install` logic. The bar for new templates is high because each
  one introduces new symlinks, new entries in
  `personalities.yaml`, and a new directory under
  `personalities/`.

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
