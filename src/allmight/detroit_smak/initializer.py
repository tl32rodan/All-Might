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
        """Create config.yaml, enrichment/, and panorama/ at the project root."""
        # Build index dicts
        indices = []
        for idx in manifest.indices:
            entry: dict = {
                "name": idx.name,
                "uri": idx.uri or f"./smak/{idx.name}",
                "description": idx.description,
                "paths": idx.paths,
            }
            if idx.path_env:
                entry["path_env"] = idx.path_env
            indices.append(entry)

        # Merged config.yaml
        config = {
            "project": {
                "name": manifest.name,
                "root": str(manifest.root_path),
                "languages": manifest.languages,
                "frameworks": manifest.frameworks,
            },
            "enrichment": {
                "strategy": "advisory",
            },
            "indices": indices,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_yaml(root / "config.yaml", config)

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
        """Generate All-Might skills (WHAT + WHEN/WHY + bootstrap layers)."""
        skills_dir = root / ".claude" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        # detroit-smak/SKILL.md — bootstrap (user-triggered)
        self._write_skill(
            skills_dir / "detroit-smak" / "SKILL.md",
            name="detroit-smak",
            description=(
                "Project knowledge graph initialization. Re-scan project structure, "
                "regenerate configuration and All-Might workspace. "
                "Use when the project structure has significantly changed."
            ),
            disable_model_invocation=True,
            body=self._detroit_smak_skill_body(manifest),
        )

        # one-for-all/SKILL.md — project knowledge map (auto-loaded)
        self._write_skill(
            skills_dir / "one-for-all" / "SKILL.md",
            name="one-for-all",
            description=(
                "Project knowledge graph guide. Provides project structure, "
                "corpus reference, key symbols, and current Power Level. "
                "Auto-loaded when agent needs to understand the project."
            ),
            body=self._one_for_all_skill_body(manifest),
        )

        # enrichment/SKILL.md — enrichment protocol (auto-loaded)
        self._write_skill(
            skills_dir / "enrichment" / "SKILL.md",
            name="enrichment-protocol",
            description=(
                "Knowledge enrichment protocol. Guides agents on when and how "
                "to contribute to the knowledge graph while working. "
                "Auto-loaded when agent reads or modifies code."
            ),
            body=self._enrichment_skill_body(),
        )

    def _generate_commands(self, root: Path, manifest: ProjectManifest) -> None:
        """Generate .claude/commands/ for slash-command operations."""
        commands_dir = root / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)

        # /power-level
        (commands_dir / "power-level.md").write_text(
            "Analyze the project's knowledge graph coverage (Power Level).\n\n"
            "1. Read `enrichment/tracker.yaml` for the last known Power Level.\n"
            "2. Scan all sidecar YAML files (`.*.sidecar.yaml`) across all corpora.\n"
            "3. For each sidecar, count total symbols vs symbols with non-empty `intent`.\n"
            "4. Count total relations across all sidecars.\n"
            "5. Report the overall coverage percentage and per-index breakdown.\n"
            "6. Update `enrichment/tracker.yaml` with the new metrics.\n\n"
            "Display results in a clear table format with coverage bars.\n"
        )

        # /regenerate
        (commands_dir / "regenerate.md").write_text(
            "Regenerate the One For All skill with the latest project state.\n\n"
            "1. Read `config.yaml` for project configuration and corpus definitions.\n"
            "2. Scan all sidecar YAML files to find enriched symbols.\n"
            "3. Calculate current Power Level.\n"
            "4. Regenerate `.claude/skills/one-for-all/SKILL.md` with:\n"
            "   - Updated project overview\n"
            "   - Current index reference with descriptions\n"
            "   - Key enriched symbols summary (top symbols by relation count)\n"
            "   - Current Power Level metrics\n"
            "   - Updated architecture notes from high-coverage areas\n"
            "5. Update `enrichment/tracker.yaml` with new metrics.\n\n"
            "Report what changed in the regenerated skill.\n"
        )

        # /panorama
        (commands_dir / "panorama.md").write_text(
            "Export the knowledge graph as a panoramic visualization.\n\n"
            "1. Scan all sidecar YAML files across all corpora.\n"
            "2. Build a graph of symbols (nodes) and relations (edges).\n"
            "3. Generate a Mermaid diagram showing the key relationships.\n"
            "4. Write output to `panorama/overview.mermaid`.\n"
            "5. Also write `panorama/graph.json` with the full graph data.\n"
            "6. Report summary statistics: node count, edge count, clusters, orphans.\n\n"
            "Focus on the most connected symbols — omit isolated nodes with no relations.\n"
        )

        # /search
        (commands_dir / "search.md").write_text(
            "Search the knowledge graph via All-Might.\n\n"
            "Usage: `/search <query>` or `/search <query> --index <index>`\n\n"
            "Run `allmight search \"<query>\" --index source_code` to perform semantic search.\n"
            "Use `allmight explain <uid>` for graph context on any result.\n"
        )

        # /enrich
        (commands_dir / "enrich.md").write_text(
            "Enrich a symbol with intent and/or relations via All-Might.\n\n"
            "Usage: `/enrich --file <path> --symbol <name> --intent \"description\"`\n\n"
            "Run `allmight enrich --file <path> --symbol <name> --intent \"...\"` to annotate.\n"
            "Add `--relation <uid>` (repeatable) to link to other symbols.\n"
            "Add `--bidirectional` to create the reverse link too.\n"
        )

        # /ingest
        (commands_dir / "ingest.md").write_text(
            "Rebuild the corpus search data.\n\n"
            "Usage: `/ingest` or `/ingest --index <index>`\n\n"
            "Run `allmight ingest` to re-ingest all indices, or\n"
            "`allmight ingest --index source_code` for a specific index.\n"
        )

        # /explain
        (commands_dir / "explain.md").write_text(
            "Show full graph context for a symbol.\n\n"
            "Usage: `/explain <uid>`\n\n"
            "Run `allmight explain \"<path>::<symbol>\"` to see:\n"
            "- Intent, outgoing/incoming relations, degree\n"
            "- Whether it's a god node (highly connected)\n"
            "- Which community/cluster it belongs to\n"
        )

        # /graph-report
        (commands_dir / "graph-report.md").write_text(
            "Generate a graph intelligence report.\n\n"
            "Run `allmight report` to produce `panorama/GRAPH_REPORT.md`.\n"
            "The report includes:\n"
            "- Overview metrics (nodes, edges, density)\n"
            "- God nodes (most connected symbols)\n"
            "- Communities (connected components)\n"
            "- Orphan nodes (symbols with no relations)\n"
            "- Cross-index relations\n"
        )

        # /add-index
        (commands_dir / "add-index.md").write_text(
            "Add a new corpus to the workspace configuration.\n\n"
            "Usage: `/add-index --name <name> --description \"desc\" --paths <path>`\n\n"
            "Run `allmight config add-index --name <name> --description \"...\" --paths <path>`.\n"
            "This updates `config.yaml`.\n"
            "After adding, run `/ingest --index <name>` to build the search data.\n"
        )

        # /remove-index
        (commands_dir / "remove-index.md").write_text(
            "Remove a corpus from the workspace configuration.\n\n"
            "Usage: `/remove-index --name <name>`\n\n"
            "Run `allmight config remove-index --name <name>`.\n"
            "This updates `config.yaml`.\n"
        )

        # /list-indices
        (commands_dir / "list-indices.md").write_text(
            "List all corpora in the workspace configuration.\n\n"
            "Run `allmight config list-indices` to see all configured indices.\n"
            "Add `--json` for machine-readable output.\n"
        )

    def _update_claude_md(self, root: Path, manifest: ProjectManifest) -> None:
        """Append All-Might baseline instructions to CLAUDE.md at project root."""
        claude_md = root / "CLAUDE.md"

        marker = "<!-- ALL-MIGHT -->"
        allmight_section = f"""{marker}
## All-Might: Active Knowledge Graph

This project uses **All-Might** as the single interface for knowledge graph operations.
All operations go through All-Might commands.

### How It Works

All-Might indexes source files for semantic search, enables natural-language queries over code,
and stores per-symbol metadata in **sidecar YAML files** (`.{{filename}}.sidecar.yaml`).

Mental model: `init → ingest → search → enrich → knowledge graph`

### Workspace Architecture

This folder is a **standalone All-Might workspace hub** — it is decoupled from source code.

```
<this folder>/                        ← Claude Code project root
├── config.yaml                       ← Project metadata + index definitions
├── CLAUDE.md                         ← This file (agent constitution)
├── enrichment/tracker.yaml           ← Power tracker
├── panorama/                         ← Graph exports
├── smak/                             ← Search data (built by /ingest)
└── .claude/                          ← Skills, commands
```

**Source code is NOT in this folder.** It lives at external paths managed by the project's
version control system. Indices in `config.yaml` reference these external paths
(e.g., via `$DDI_ROOT_PATH` in SOS/EDA environments).

| What | Location |
|------|----------|
| Search data | `./smak/<index_name>/` (local, built by `/ingest`) |
| Index config | `./config.yaml` (local) |
| Source code | External paths defined in `config.yaml` |
| Sidecar files | Beside source files at the external path (not in this folder) |

**Key implication for agents**: When you need to read or modify source files, you must
navigate to the paths listed in `config.yaml` — they are outside this folder.

- **Skills**: `.claude/skills/` — `one-for-all` (project map), `enrichment` (protocol)
- **Config**: `config.yaml` — project metadata, semantic index definitions, enrichment settings
- **Enrichment**: `enrichment/` — Power Level tracker
- **Panorama**: `panorama/` — graph exports

### Commands

| Command | Purpose |
|---------|---------|
| `/search <query>` | Semantic search with graph context |
| `/enrich` | Annotate a symbol with intent/relations |
| `/explain <uid>` | Full graph context for a symbol |
| `/ingest` | Rebuild corpus |
| `/power-level` | Knowledge graph coverage metrics |
| `/regenerate` | Regenerate One For All skill |
| `/panorama` | Export knowledge graph visualization |
| `/graph-report` | Generate graph intelligence report |
| `/add-index` | Add a new corpus |
| `/remove-index` | Remove an existing index |
| `/list-indices` | List all configured indices |

### Guardrails — Critical Rules

- **NEVER** directly edit `.sidecar.yaml` files. Always use `/enrich` to modify sidecar content.
  Sidecar files have a strict schema that hand-editing will break.
- **NEVER** directly edit `config.yaml`. Use `/add-index`, `/remove-index`,
  or `allmight config update-index` to modify index configuration.
- **NEVER** invent symbol UIDs. UIDs follow the format `<file_path>::<symbol_name>`
  (e.g., `src/module.py::ClassName.method_name`). Use `/search` or `/explain` to discover valid UIDs.
- **ALWAYS** use All-Might commands for knowledge graph operations.

### Online vs. Version Control

**Corpora index online (Layer 1) only.** All `/search` and `/explain` results come from online.
Version control (VC) releases are frozen snapshots — they do not have separate search indices.

To check whether a feature exists in a specific VC release:
1. `/search` on online to find the relevant files/symbols
2. Use `sos log` / `sos history` on the file to find the revision log entry
3. Check if the **same revision log string** exists in the target VC
4. Same log → same code → feature is present in that VC

See the `sos-smak` skill for the full SOS workflow and version control details.

### Getting Started — Step by Step

**Phase 1: Build the search index** (one-time setup)
1. Run `/ingest` to build the corpus from source code
2. Verify with `/list-indices` — you should see your corpora listed
3. If `/ingest` isn't available yet, ensure the search engine is installed

**Phase 2: Explore** (start using immediately)
1. `/search "what does the auth module do"` — semantic search across the codebase
2. `/explain "src/auth.py::AuthHandler"` — deep graph context for any symbol
3. The `one-for-all` skill auto-loads with project overview and corpus reference

**Phase 3: Enrich** (as you learn the codebase)
1. When you understand a symbol's purpose, run `/enrich` to annotate it
2. Follow the `enrichment-protocol` skill for guidance on when and how
3. Run `/power-level` to track enrichment progress (aim for key entry points first)

**Phase 4: Maintain** (periodically)
1. `/regenerate` — update the one-for-all skill with latest enrichment data
2. `/panorama` — export the knowledge graph as a visualization
3. `/graph-report` — identify god nodes, orphans, and communities

**Milestone checkpoints:**
- After `/ingest`: `/search` returns relevant results ✓
- After first `/enrich`: `/power-level` shows > 0% coverage ✓
- After 10+ enrichments: `/graph-report` shows meaningful clusters ✓
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
        index_table = "| Index | Description | Paths |\n|-------|-------------|-------|\n"
        for idx in manifest.indices:
            paths_str = ", ".join(idx.paths)
            index_table += f"| `{idx.name}` | {idx.description} | `{paths_str}` |\n"

        dir_map = ""
        if manifest.directory_map:
            dir_map = "### Directory Structure\n\n"
            for dirname, role in manifest.directory_map.items():
                dir_map += f"- `{dirname}/` — {role}\n"

        return f"""# One For All — {manifest.name}

> **All-Might** is the active knowledge graph layer that indexes this codebase,
> providing commands, enrichment, and graph intelligence.
>
> All knowledge graph operations go through **All-Might commands** (`/search`, `/enrich`, `/explain`, etc.).
> Do NOT hand-edit sidecar or config YAML files.

## Project Overview

- **Name**: {manifest.name}
- **Languages**: {', '.join(manifest.languages) or 'Not yet detected'}
- **Frameworks**: {', '.join(manifest.frameworks) or 'Not yet detected'}

{dir_map}

## Corpus Reference

{index_table}

Use `/list-indices` to verify indices are active.

> **Note:** This workspace is a standalone hub — source code is at external paths
> listed in the "Paths" column above. Search data is stored locally in `./smak/`.
> Sidecar files live beside the source files at those external paths, not here.
> **Indices are built from online (Layer 1) only.** To verify features in version control
> releases, use SOS revision log matching (see `sos-smak` skill).

## Key Symbols

> No symbols have been enriched yet. As you work with this project and use
> `/enrich` to annotate code, this section will be populated when you
> run `/regenerate`.

## Power Level

- **Coverage**: 0% (fresh workspace)
- **Enriched symbols**: 0
- **Total relations**: 0

Run `/power-level` to get current metrics, or `/regenerate` to update this skill.

## All-Might Commands

| Command | Purpose |
|---------|---------|
| `/search <query>` | Semantic search with graph context |
| `/explain <uid>` | Full graph context for a symbol |
| `/enrich` | Annotate a symbol with intent/relations |
| `/ingest` | Rebuild corpus |
| `/power-level` | Check knowledge coverage metrics |
| `/regenerate` | Update this skill with latest state |
| `/panorama` | Export knowledge graph visualization |
| `/graph-report` | Graph intelligence report |
| `/add-index` | Add a new corpus |
| `/remove-index` | Remove an index |
| `/list-indices` | List all configured indices |

## Getting Started

1. Use `/search "..."` to explore the codebase semantically
2. Use `/explain "path::symbol"` for deep context on any symbol
3. When you understand a symbol's purpose, use `/enrich` (see `enrichment-protocol` skill)
4. Run `/power-level` periodically to track progress
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
