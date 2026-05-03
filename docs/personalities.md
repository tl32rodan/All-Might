# Personalities

A *personality* is a reusable capability bundle that ``allmight init``
attaches to a project. Personalities can be shared across projects
or teams; see [team-share.md](team-share.md) for the bundle (Mode 1,
git transport) and instance (Mode 2, NFS) sharing patterns.

Built-in personalities today:

| Template       | Short name | What it provides |
|----------------|------------|------------------|
| corpus_keeper  | corpus     | Knowledge-graph workspaces, `/search` `/enrich` `/ingest` `/sync`, AGENTS.md section |
| memory_keeper  | memory     | L1/L2/L3 agent memory, `/remember` `/recall` `/reflect`, OpenCode plugins |

## Two-tier model

There are two distinct concepts in `core/personalities.py`:

* **`PersonalityTemplate`** — the *kind*. A static record holding the
  template's name, owned paths, contributed CLI flags, and the
  ``install`` / ``status`` callables. One per built-in subpackage,
  exposed as a module-level ``TEMPLATE`` constant.
* **`Personality`** — an *instance* of a template attached to a project.
  Identified by ``name`` (defaults to ``f"{manifest.name}-{template.short_name}"``)
  and rooted at ``personalities/<name>/``.

Today every project has exactly one instance per built-in template.
The data model already supports several instances per template, but
the CLI defaults are single-instance for now.

## Layout

Each instance owns one directory:

```
personalities/<name>/
├── skills/      ← contributed to .opencode/skills/ via symlink
├── commands/    ← contributed to .opencode/commands/ via symlink
├── plugins/     ← contributed to .opencode/plugins/ via symlink
└── <data dir>   ← knowledge_graph/ or memory/, depending on template
```

Two files always stay at the project root because they are
single-entrypoint by design: ``AGENTS.md`` (high-level capabilities)
and ``MEMORY.md`` (L1 cache loaded every turn). Each template appends
its own marker-fenced section to those files.

`.opencode/` itself is **composed** by the registry: after every
template's ``install`` returns, the registry walks each instance's
``skills/`` ``commands/`` ``plugins/`` and creates relative symlinks
under root ``.opencode/<kind>/<basename>``. The agent never sees the
symlink — its tools open ``.opencode/commands/search.md`` and the
filesystem follows the link into the corpus instance.

## CLI flags are contributed, not hardcoded

The ``init`` Click command registers per-template flags dynamically
from each template's ``cli_options``. ``--sos`` and ``--writable``
ship with corpus_keeper; cli.py itself contains no literal references
to those names. To add a new flag:

1. Append a ``CliOption(name=..., flag="--foo", help="...")`` to the
   template's ``cli_options`` list.
2. Read ``instance.options.get("foo")`` inside the template's
   ``install`` callable.

The CLI never interprets the value — it forwards the raw dict of
parsed options to every ``Personality.options``.

## Registry on disk

After ``allmight init``, ``.allmight/personalities.yaml`` records the
installed instances:

```yaml
personalities:
- template: corpus_keeper
  instance: my-project-corpus
  version: 1.0.0
- template: memory_keeper
  instance: my-project-memory
  version: 1.0.0
```

``allmight status`` (planned) will read this file and call each
template's ``status`` callable to render an installed/missing/dirty
report.

## Out of scope

User-defined templates (third-party authoring via entry points) are
**not supported** in this PR. The framework is internal-only; the
``TODO(future)`` marker in ``core/personalities.py::discover`` flags
where entry-point discovery would slot in.

Multi-instance per template is supported by the data model but not
exposed in the CLI yet — the init flow always picks the
``f"{manifest.name}-{short_name}"`` default.

Wrapping vendor CLIs like ``soscmd`` as OpenCode plugins is a
plausible direction for corpus_keeper but auth/env/output design is
not yet clear. The current refactor only ensures such a plugin would
live entirely inside ``personalities/corpus_keeper/`` rather than
leaking into ``cli.py``.
