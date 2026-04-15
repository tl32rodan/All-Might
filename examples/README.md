# examples/

This directory shows what `allmight init --with-memory` produces.

Run `make example` from repo root to regenerate after code changes
(or manually: see instructions below).

## single-workspace/

A typical project after `allmight init . --with-memory`:

```
single-workspace/
├── src/main.py                              ← Your source code (unchanged)
├── tests/test_main.py                       ← Your tests (unchanged)
├── docs/README.md                           ← Your docs (unchanged)
├── pyproject.toml                           ← Your project config (unchanged)
│
│   --- All-Might generates everything below ---
│
├── CLAUDE.md                                ← Agent constitution (high-level WHAT)
├── AGENTS.md → CLAUDE.md                    ← OpenCode compatibility symlink
├── config.yaml                              ← Project metadata + corpus definitions
│
├── .claude/
│   ├── skills/
│   │   └── one-for-all/SKILL.md             ← THE skill (auto-loaded, teaches agent everything)
│   └── commands/
│       ├── search.md                        ← /search guide
│       ├── enrich.md                        ← /enrich guide
│       ├── ingest.md                        ← /ingest guide
│       ├── status.md                        ← /status guide
│       ├── remember.md                      ← /remember guide (memory)
│       ├── recall.md                        ← /recall guide (memory)
│       └── consolidate.md                   ← /consolidate guide (memory)
│
├── enrichment/
│   └── tracker.yaml                         ← Power Level history (annotation coverage)
│
├── panorama/                                ← (empty until agent generates graph exports)
│
└── memory/                                  ← Agent memory (from --with-memory)
    ├── config.yaml                          ← Memory settings + store definitions
    ├── smak_config.yaml                     ← Internal search engine config (auto-generated)
    ├── working/
    │   └── MEMORY.md                        ← Always-in-context facts
    ├── episodes/                            ← Session history (one file per session)
    ├── semantic/                            ← Lasting facts (extracted from episodes)
    └── store/                               ← Memory search index data (internal)
```

## What each part does

| Directory | Purpose | Who uses it |
|-----------|---------|-------------|
| `.claude/skills/` | Teaches the agent HOW to operate | Agent (auto-loaded) |
| `.claude/commands/` | Operational guides triggered by `/command` | Agent (user triggers) |
| `enrichment/` | Tracks annotation coverage over time | Agent (reads/writes tracker.yaml) |
| `panorama/` | Graph exports (generated on demand) | Agent (writes when asked) |
| `memory/` | Persistent agent memory across sessions | Agent (reads/writes) |

## hub-3-flows/

A multi-workspace setup with 3 independent SMAK workspaces:

```
hub-3-flows/
└── workspaces/
    ├── stdcell/                   ← EDA workspace (Verilog/SystemVerilog)
    │   ├── rtl/top.v              ← Source: RTL design files
    │   ├── verif/tb_top.sv        ← Source: verification testbenches
    │   ├── constraints/timing.sdc ← Source: timing constraints
    │   ├── config.yaml            ← 3 corpora: rtl, verif, constraints
    │   ├── CLAUDE.md
    │   ├── .claude/skills/...     ← one-for-all (teaches smak for THIS workspace)
    │   ├── .claude/commands/...   ← /search, /enrich, /ingest, /status + memory
    │   ├── enrichment/
    │   ├── panorama/
    │   └── memory/
    │
    ├── io_phy/                    ← EDA workspace (Verilog/SystemVerilog)
    │   ├── rtl/io_pad.v
    │   ├── verif/tb_io.sv
    │   ├── config.yaml            ← 2 corpora: rtl, verif
    │   ├── ...                    ← same structure as stdcell
    │
    └── pll/                       ← Software workspace (Python)
        ├── src/pll.py
        ├── tests/test_pll.py
        ├── config.yaml            ← 2 corpora: source_code, tests
        ├── ...                    ← same structure
```

### Key observations

1. **Each workspace is self-contained** — has its own config.yaml, skills,
   commands, enrichment tracker, and memory.

2. **config.yaml differs per workspace** — stdcell has `rtl`, `verif`,
   `constraints` corpora; pll has `source_code`, `tests`. The scanner
   auto-detects based on directory structure.

3. **No hub-level config.yaml yet** — currently each workspace is initialized
   independently with `allmight init`. A future hub config would just list
   workspace paths without duplicating their SMAK settings.

4. **Skills/commands are identical** — the one-for-all skill and commands are
   the same templates, but the one-for-all SKILL.md content differs because
   it reflects each workspace's detected languages and corpora.

---

## Regenerating

```bash
cd /path/to/All-Might
rm -rf examples/single-workspace/.claude examples/single-workspace/CLAUDE.md \
       examples/single-workspace/AGENTS.md examples/single-workspace/config.yaml \
       examples/single-workspace/enrichment examples/single-workspace/panorama \
       examples/single-workspace/memory
PYTHONPATH=src python -c "
from allmight.detroit_smak.scanner import ProjectScanner
from allmight.detroit_smak.initializer import ProjectInitializer
from allmight.memory.initializer import MemoryInitializer
from pathlib import Path
root = Path('examples/single-workspace').resolve()
manifest = ProjectScanner().scan(root)
ProjectInitializer().initialize(manifest)
MemoryInitializer().initialize(root)
"
```
