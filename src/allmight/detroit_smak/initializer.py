"""Detroit SMAK Initializer — one punch creates the entire workspace.

Takes a ProjectManifest from the Scanner and generates:
- config.yaml (merged project metadata + corpus definitions)
- enrichment/ and panorama/ directories
- .claude/skills/ (layered skill composition)
- .claude/commands/ (slash commands)
- Updates CLAUDE.md at project root
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..core.domain import ProjectManifest


class ProjectInitializer:
    """Creates the All-Might workspace and Claude Code integration files."""

    def initialize(
        self,
        manifest: ProjectManifest,
        smak_path: Path | None = None,
    ) -> None:
        """Execute Detroit SMAK — bootstrap the entire workspace.

        Args:
            manifest: Project characteristics from the Scanner.
            smak_path: Optional path to SMAK installation for skill copying.
        """
        root = manifest.root_path

        # 1. Create config.yaml, enrichment/, panorama/
        self._create_metadata(root, manifest)

        # 3. Install SMAK skills (layered composition — HOW layer)
        self._install_smak_skills(root, manifest, smak_path)

        # 4. Generate All-Might skills (WHAT + WHEN/WHY layers)
        self._generate_allmight_skills(root, manifest)

        # 5. Generate commands
        self._generate_commands(root, manifest)

        # 6. Update CLAUDE.md
        self._update_claude_md(root, manifest)

        # 7. Create OpenCode compatibility symlinks
        self._create_opencode_compat(root)

    def _create_metadata(self, root: Path, manifest: ProjectManifest) -> None:
        """Create enrichment/, panorama/, knowledge_graph/ at the project root.

        Note: config.yaml is NOT created here — it belongs to SMAK workspaces
        under knowledge_graph/*/config.yaml, not the All-Might project root.
        """
        # knowledge_graph/ — workspace container (SMAK workspaces live here)
        (root / "knowledge_graph").mkdir(exist_ok=True)

        # enrichment/tracker.yaml — initial Power Level (all 0%)
        enrichment_dir = root / "enrichment"
        enrichment_dir.mkdir(exist_ok=True)
        tracker = {
            "power_level": {
                "total_symbols": 0,
                "enriched_symbols": 0,
                "coverage_pct": 0.0,
                "by_index": {},
                "total_files": 0,
                "files_with_sidecars": 0,
                "total_relations": 0,
            },
            "history": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_yaml(enrichment_dir / "tracker.yaml", tracker)

        # panorama/ — output directory
        (root / "panorama").mkdir(exist_ok=True)

    def _install_smak_skills(
        self,
        root: Path,
        manifest: ProjectManifest,
        smak_path: Path | None,
    ) -> None:
        """Install environment skills into .claude/skills/.

        Agents use All-Might commands for all operations. We only install
        sos-smak/SKILL.md for SOS environments, since it provides path
        resolution rules.

        SOS skill content is bundled in All-Might — no runtime dependency
        on external skill files being present on disk.
        """
        if not manifest.has_path_env:
            return

        from .sos_skill_content import SOS_SKILL_BODY

        skills_dir = root / ".claude" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        self._write_skill(
            skills_dir / "sos-smak" / "SKILL.md",
            name="sos-smak-skill",
            description=(
                "CliosoftSOS environment guide. Teaches agents the "
                "internal EDA version control workflow — online vs. version "
                "control vs. SOS workspace — and how to correctly use All-Might "
                "(path_env, sidecar editing, ingestion) within this environment. "
                "Load this skill when working in projects that use CliosoftSOS "
                "and $DDI_ROOT_PATH."
            ),
            body=SOS_SKILL_BODY,
        )

    def _generate_allmight_skills(self, root: Path, manifest: ProjectManifest) -> None:
        """Generate All-Might skill — one unified skill that covers everything."""
        skills_dir = root / ".claude" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        # one-for-all/SKILL.md — the single unified skill (auto-loaded)
        self._write_skill(
            skills_dir / "one-for-all" / "SKILL.md",
            name="one-for-all",
            description=(
                "All-Might knowledge guide. Project structure, corpus reference, "
                "enrichment protocol, key symbols, and Power Level. "
                "Auto-loaded when agent needs to understand the project."
            ),
            body=self._one_for_all_skill_body(manifest),
        )

    def _generate_commands(self, root: Path, manifest: ProjectManifest) -> None:
        """Generate .claude/commands/ — thick operational guides."""
        commands_dir = root / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)

        (commands_dir / "search.md").write_text("""\
Search the codebase by semantic meaning.

## How to execute

```bash
smak search "<query>" --config config.yaml --index source_code --top-k 5 --json
```

To search across all corpora at once:
```bash
smak search-all "<query>" --config config.yaml --top-k 3 --json
```

To look up a specific symbol by UID:
```bash
smak lookup "<file_path>::<symbol_name>" --config config.yaml --index source_code --json
```

## What to expect

JSON output with a `results` array. Each result contains:
- `id` — the matched chunk/symbol identifier
- `text` or `content` — the matched source code
- `score` — relevance score (0–1)
- `metadata` — file path, symbol name, etc.

## After searching

- If a result has a sidecar (`.{filename}.sidecar.yaml` beside it), read the
  sidecar to see its enriched intent and relations.
- If a result has NO sidecar or missing intent, consider enriching it with `/enrich`.
- Present results to the user in terms of "knowledge graph" — do not mention SMAK.
""")

        (commands_dir / "enrich.md").write_text("""\
Annotate a code symbol with intent and/or relations.

## How to execute

Set intent (what the symbol does and why):
```bash
smak enrich --config config.yaml --index source_code \\
    --file <relative_path> --symbol "<SymbolName>" \\
    --intent "Human-readable description of purpose"
```

Add a relation to another symbol:
```bash
smak enrich --config config.yaml --index source_code \\
    --file <relative_path> --symbol "<SymbolName>" \\
    --relation "<other_file>::<OtherSymbol>" --bidirectional
```

## When to enrich

- **Reading code**: symbol has no intent → add one
- **Discovering relationships**: two entities are related → link them
- **After modifying code**: existing intent may be stale → update it

## Priority

1. Entry points — main functions, API handlers, CLI commands
2. Complex logic — algorithms, state machines, non-obvious flow
3. Cross-cutting concerns — error handling, auth, logging
4. Frequently modified files (high git activity)

Skip auto-generated code, simple getters, and obvious boilerplate.

## What to expect

- A `.{filename}.sidecar.yaml` file is created/updated beside the source file
- The sidecar contains structured YAML with `symbols[].intent` and `symbols[].relations`
- Do NOT edit sidecar files by hand — always use `smak enrich`

## UID format

`<file_path>::<symbol_name>` — e.g., `src/auth.py::AuthHandler.validate`
- File path is relative to project root
- Dot notation for nested symbols: `ClassName.method_name`
- Wildcard `*` for entire file: `path/to/file.py::*`
- Never invent UIDs — use `/search` to discover valid ones
""")

        (commands_dir / "ingest.md").write_text("""\
Rebuild the search corpus from source files.

## When to run

- **First time**: after `allmight init` to build the initial index
- **After significant changes**: new files added, major refactoring
- **After adding a corpus**: to populate the new index

You do NOT need to re-ingest after enrichment — sidecars are separate
from the search index.

## How to execute

Rebuild all corpora:
```bash
smak ingest --config config.yaml --json
```

Rebuild a specific corpus:
```bash
smak ingest --config config.yaml --index source_code --json
```

## What to expect

- The `./smak/<corpus_name>/` directory is populated with search index data
- `/search` will return results from the newly ingested files
- Ingestion may take a few minutes for large codebases

## Troubleshooting

- If `smak` is not found, ensure SMAK is installed and on PATH
- Check `smak health --config config.yaml --json` for diagnostics
- List available corpora: `smak describe --config config.yaml --json`
""")

        (commands_dir / "status.md").write_text("""\
Show the knowledge graph coverage and system health.

## How to execute

1. Scan all sidecar YAML files (`.*.sidecar.yaml`) across all paths
   defined in `config.yaml` indices.
2. For each sidecar, count symbols and check which have non-empty `intent`.
3. Calculate coverage: `enriched_symbols / total_symbols * 100`.
4. Read `enrichment/tracker.yaml` for historical data.
5. If `memory/config.yaml` exists (memory system enabled), also report:
   - Working memory: count words in `memory/working/MEMORY.md`
   - Episodic memory: count files in `memory/episodes/`
   - Semantic memory: count files in `memory/semantic/`

## What to report

```
Power Level: XX.X%
  source_code: XX.X% (N/M symbols enriched)
  tests:       XX.X% (N/M symbols enriched)
  Total relations: N

Memory (if enabled):
  Episodes: N total, M unconsolidated
  Facts: N total, avg confidence X.XX
```

## When to run

- After enrichment work to see progress
- Periodically to track coverage trends
- When the user asks "how healthy is the knowledge graph?"

## After checking status

- If coverage is low, prioritize `/enrich` on entry points
- If many episodes are unconsolidated, suggest `/consolidate`
- Update `enrichment/tracker.yaml` with the new snapshot
""")

    def _update_claude_md(self, root: Path, manifest: ProjectManifest) -> None:
        """Append All-Might baseline instructions to CLAUDE.md at project root."""
        claude_md = root / "CLAUDE.md"

        marker = "<!-- ALL-MIGHT -->"
        allmight_section = f"""{marker}
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
"""

        if claude_md.exists():
            content = claude_md.read_text()
            if marker in content:
                # Replace existing section
                before = content[: content.index(marker)]
                content = before.rstrip() + "\n\n" + allmight_section
            else:
                content = content.rstrip() + "\n\n" + allmight_section
            claude_md.write_text(content)
        else:
            claude_md.write_text(f"# {manifest.name}\n\n{allmight_section}")

    def _create_opencode_compat(self, root: Path) -> None:
        """Create OpenCode-compatible symlinks.

        OpenCode prefers ``AGENTS.md`` over ``CLAUDE.md`` as its rules
        file.  We create a single symlink so both tools read the same
        content.

        We do **NOT** create a ``.opencode/`` directory — that is
        OpenCode's own runtime directory (node_modules, plugins, etc.)
        and pre-creating it interferes with OpenCode's initialisation.
        OpenCode already reads ``.claude/skills/`` and ``.claude/CLAUDE.md``
        natively as a compatibility fallback, so no directory-level
        symlinks are needed.

        Symlink created::

            AGENTS.md → CLAUDE.md
        """
        import os

        agents_md = root / "AGENTS.md"
        claude_md = root / "CLAUDE.md"
        if claude_md.exists() and not agents_md.exists():
            os.symlink("CLAUDE.md", str(agents_md))

    def _write_skill(
        self,
        path: Path,
        name: str,
        description: str,
        body: str,
        disable_model_invocation: bool = False,
    ) -> None:
        """Write a SKILL.md file with YAML frontmatter."""
        path.parent.mkdir(parents=True, exist_ok=True)

        frontmatter_lines = [
            "---",
            f"name: {name}",
            f"description: {description}",
        ]
        if disable_model_invocation:
            frontmatter_lines.append("disable-model-invocation: true")
        frontmatter_lines.append("---")

        content = "\n".join(frontmatter_lines) + "\n\n" + body
        path.write_text(content)

    def _detroit_smak_skill_body(self, manifest: ProjectManifest) -> str:
        """Generate the body for detroit-smak/SKILL.md."""
        return f"""# Detroit — Project Bootstrap

Re-initialize the All-Might workspace for **{manifest.name}**.

## What this does

1. Re-scan the project directory for structural changes
2. Update `config.yaml` with new/changed directories and indices
3. Regenerate all All-Might skills (one-for-all, enrichment)
4. Optionally trigger `/ingest` for new indices

## When to use

- Project structure has significantly changed (new directories, languages)
- New team members need a fresh workspace setup
- After major refactoring

## Steps

1. Run `allmight init {manifest.root_path}` OR manually:
   - Scan the project directory structure
   - Compare with existing `config.yaml`
   - Update indices in `config.yaml`
   - Regenerate `.claude/skills/one-for-all/SKILL.md`
   - Regenerate `.claude/skills/enrichment/SKILL.md`
2. If new indices were added, run `/ingest` for each new index
"""

    def _one_for_all_skill_body(self, manifest: ProjectManifest) -> str:
        """Generate the initial body for one-for-all/SKILL.md."""
        dir_map = ""
        if manifest.directory_map:
            dir_map = "### Directory Structure\n\n"
            for dirname, role in manifest.directory_map.items():
                dir_map += f"- `{dirname}/` — {role}\n"

        return f"""# One For All — {manifest.name}

> **All-Might** is the active knowledge graph layer for this project.
> It manages SMAK workspaces under `knowledge_graph/`, shared enrichment,
> and agent memory. Use the commands below — Do NOT hand-edit sidecar or
> config YAML files directly.

## Project Overview

- **Name**: {manifest.name}
- **Languages**: {', '.join(manifest.languages) or 'Not yet detected'}
- **Frameworks**: {', '.join(manifest.frameworks) or 'Not yet detected'}

{dir_map}
## SMAK Workspaces

Workspaces live under `knowledge_graph/`. Discover them:
```bash
ls knowledge_graph/
```

Each workspace has its own `config.yaml` (indices) and `store/` (search data).

## SMAK CLI Reference

All commands use `--config <workspace>/config.yaml`. Add `--json` for
machine-readable output.

**Search** — find code by semantic meaning:
```bash
smak search "authentication handler" --config knowledge_graph/main/config.yaml --index source_code --top-k 5 --json
smak search-all "error handling" --config knowledge_graph/main/config.yaml --top-k 3 --json
smak lookup "src/auth.py::AuthHandler" --config knowledge_graph/main/config.yaml --index source_code --json
```

**Enrich** — annotate a symbol with intent and relations:
```bash
smak enrich --config knowledge_graph/main/config.yaml --index source_code \\
    --file src/auth.py --symbol "AuthHandler.validate" \\
    --intent "Validates JWT tokens and extracts user claims"

smak enrich --config knowledge_graph/main/config.yaml --index source_code \\
    --file src/auth.py --symbol "AuthHandler.validate" \\
    --relation "src/models.py::User" --bidirectional
```

**Ingest** — rebuild the vector index from source files:
```bash
smak ingest --config knowledge_graph/main/config.yaml                    # all corpora
smak ingest --config knowledge_graph/main/config.yaml --index source_code  # specific corpus
```

**Diagnostics**:
```bash
smak health --config knowledge_graph/main/config.yaml --json
smak describe --config knowledge_graph/main/config.yaml --json
smak stats --config knowledge_graph/main/config.yaml --json
```

## Sidecar Files

Sidecar files store enrichment metadata beside the source file they describe.
They are named `.{{source_filename}}.sidecar.yaml`.

```yaml
# Example: .auth.py.sidecar.yaml  (beside src/auth.py)
symbols:
  - name: "AuthHandler.validate"
    intent: "Validates JWT tokens and extracts user claims"
    relations:
      - "src/models.py::User"
      - "tests/test_auth.py::test_validate"
```

**Important rules:**
- NEVER edit .sidecar.yaml files by hand — always use `smak enrich`
- UIDs follow the format `<file_path>::<symbol_name>`
- Use dot notation for nested symbols: `ClassName.method_name`
- The wildcard `*` means the entire file: `path/to/file.py::*`
- Do NOT invent UIDs — use `smak search` to discover valid ones

## Commands

| Command | Purpose |
|---------|---------|
| `/search <query>` | Search the codebase semantically |
| `/enrich` | Annotate a symbol with intent and relations |
| `/ingest` | Rebuild the search corpus from source files |
| `/status` | Show enrichment coverage and system health |

## Getting Started

1. `/ingest` — build the search index (first time setup)
2. `/search "query"` — explore the codebase
3. `/enrich` — annotate symbols as you learn them
4. `/status` — track enrichment progress
"""

    def _enrichment_skill_body(self) -> str:
        """Generate the body for enrichment/SKILL.md."""
        return """# Enrichment Protocol — Enrich As You Work

> This is an **advisory** protocol. Follow it naturally as you work —
> don't treat it as a mandatory checklist.
>
> All enrichment goes through **All-Might commands**.

## When to Enrich

### On reading and understanding code
When you read a symbol (function, class, module) and understand its purpose:
- If the sidecar has no `intent` for this symbol → use `/enrich` to set it (do not edit the sidecar file directly)
- Write intent as a **human-readable description** of what the code does and why

### On discovering relationships
When you notice that two entities are related:
- Code ↔ Issue: a function relates to a bug report or feature request
- Code ↔ Test: a function has specific test cases
- Code ↔ Doc: a module is documented somewhere
- Code ↔ Code: two modules collaborate or one depends on the other

Link them via `/enrich --file <path> --symbol <name> --relation <target_uid>`.
Use `/search` or `/explain` to find and verify UIDs before linking.

### On modifying code
After changing code:
- Check if the sidecar intent is still accurate — use `/explain` to review, `/enrich` to update (do not edit the sidecar file directly)
- Update intent if the purpose changed
- Add relations to any new dependencies you introduced

## How to Enrich

Use the `/enrich` command (or `allmight enrich` CLI):

```bash
# 1. Set intent for a symbol you understood
allmight enrich --file src/module.py --symbol "ClassName.method_name" \\
    --intent "Validates user input and returns sanitized data"

# 2. Link a code symbol to a related issue
allmight enrich --file src/module.py --symbol "ClassName.method_name" \\
    --relation "./issues/bug-123.md::*"

# 3. Create bidirectional relation
allmight enrich --file src/module.py --symbol "ClassName.method_name" \\
    --relation "src/other.py::OtherClass" --bidirectional
```

## Sidecar File Schema (Reference Only)

> **Do NOT edit sidecar files by hand.** This schema is shown for understanding only.
> All modifications MUST go through `/enrich` or `allmight enrich`.

Sidecar files are named `.{source_filename}.sidecar.yaml` and sit beside their source file
at the **source code path** (not in the All-Might workspace folder).
In SOS environments, sidecars are created in the SOS workspace (Layer 3) and checked in
to the canonical path (Layer 1/2) via `sos check-in`.

```yaml
# Example: .module.py.sidecar.yaml
symbols:
  - name: "ClassName.method_name"      # Symbol identifier
    intent: "Human-readable purpose"    # What this code does and WHY
    relations:                          # Links to other symbols (by UID)
      - "src/other.py::OtherClass"
      - "./tests/test_module.py::test_method"
```

### UID Format

A symbol UID is: `<relative_file_path>::<symbol_name>`

- File path is relative to the project root (or uses `$ENV_VAR/...` in SOS environments)
- Symbol name uses dot notation for nested symbols: `ClassName.method_name`
- The wildcard `*` refers to the entire file: `path/to/file.py::*`

**Common mistakes** (all handled automatically by `/enrich`):
- Wrong nesting (putting `intent` outside `symbols` array)
- Missing `name` field
- Using absolute paths instead of relative paths in UIDs
- Inventing UIDs that don't correspond to actual symbols

## Useful Commands

| Command | When to use |
|---------|-------------|
| `/search <query>` | Find symbols to enrich |
| `/explain <uid>` | Check existing enrichment for a symbol |
| `/enrich` | Add intent and/or relations |
| `/power-level` | Check overall enrichment progress |
| `/graph-report` | See which areas need attention |

## Priority Guidelines

Focus enrichment on:
1. **Entry points** — main functions, API handlers, CLI commands
2. **Complex logic** — algorithms, state machines, non-obvious control flow
3. **Cross-cutting concerns** — error handling, auth, logging patterns
4. **Frequently modified** — hot files that change often (high git commit count)

Don't bother enriching:
- Auto-generated code
- Simple getters/setters
- Boilerplate that's obvious from naming

## Quality over Quantity

- A few well-written intents are worth more than many shallow ones
- Intent should answer "what does this do and **why**"
- Relations should capture **meaningful** connections, not trivial ones
"""


def _write_yaml(path: Path, data: dict) -> None:
    """Write a YAML file with consistent formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
