# All-Might Development

## After Code Changes

After modifying initializer, skill templates, commands, or memory init:

1. Regenerate the example workspace to verify the output:
   ```bash
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

2. Check the generated files in `examples/single-workspace/` match expectations

3. Run tests: `PYTHONPATH=src python -m pytest tests/`

4. Commit the regenerated example alongside your code changes

## Project Structure

```
All-Might/                          ← This repo (the framework)
├── src/allmight/                    ← Framework source code
│   ├── detroit_smak/               ← Scanner + Initializer (generates workspace)
│   ├── memory/                     ← Agent memory system
│   ├── bridge/                     ← SMAK CLI subprocess wrapper (internal)
│   ├── config/                     ← config.yaml manager
│   ├── core/                       ← Domain models + protocols
│   ├── enrichment/                 ← Power Level tracker + planner
│   ├── panorama/                   ← Knowledge graph analyzer + exporter
│   ├── one_for_all/                ← Skill template generator
│   ├── hub/                        ← Multi-workspace hub templates
│   └── cli.py                      ← CLI entry point (init only)
├── tests/                          ← Test suite
├── examples/
│   └── single-workspace/           ← ← REGENERATE THIS after changes
└── docs/
```

## Key Files to Know

| File | What it generates |
|------|-------------------|
| `detroit_smak/initializer.py` | CLAUDE.md, config.yaml, skills, commands |
| `one_for_all/templates/skill-base.md.j2` | The one-for-all SKILL.md |
| `memory/initializer.py` | Memory section in one-for-all, /remember /recall /consolidate |
| `detroit_smak/scanner.py` | Detects languages, frameworks, proposes indices |

## Architecture Layers

| Layer | What | For whom |
|-------|------|----------|
| README.md | How to talk to the agent | Human |
| CLAUDE.md (in workspace) | What capabilities exist | Agent (high-level) |
| Skills/Commands | How to execute operations (smak CLI) | Agent (low-level) |
| CLI | `allmight init` only | Human (bootstrap) |
