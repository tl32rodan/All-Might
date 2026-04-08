"""Detroit SMAK Initializer — one punch creates the entire workspace.

Takes a ProjectManifest from the Scanner and generates:
- all-might/ workspace directory
- workspace_config.yaml (SMAK configuration)
- .claude/skills/ (layered skill composition)
- .claude/commands/ (slash commands)
- Updates .claude/CLAUDE.md
"""

from __future__ import annotations

import shutil
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

        # 1. Create all-might/ workspace directory
        self._create_workspace(root, manifest)

        # 2. Generate workspace_config.yaml for SMAK
        self._create_workspace_config(root, manifest)

        # 3. Install SMAK skills (layered composition — HOW layer)
        self._install_smak_skills(root, manifest, smak_path)

        # 4. Generate All-Might skills (WHAT + WHEN/WHY layers)
        self._generate_allmight_skills(root, manifest)

        # 5. Generate commands
        self._generate_commands(root, manifest)

        # 6. Update CLAUDE.md
        self._update_claude_md(root, manifest)

    def _create_workspace(self, root: Path, manifest: ProjectManifest) -> None:
        """Create the all-might/ workspace directory structure."""
        workspace = root / "all-might"
        workspace.mkdir(exist_ok=True)

        # config.yaml
        config = {
            "project": {
                "name": manifest.name,
                "root": str(manifest.root_path),
                "languages": manifest.languages,
                "frameworks": manifest.frameworks,
            },
            "smak": {
                "config_path": "workspace_config.yaml",
            },
            "enrichment": {
                "strategy": "advisory",
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_yaml(workspace / "config.yaml", config)

        # enrichment/tracker.yaml — initial Power Level (all 0%)
        enrichment_dir = workspace / "enrichment"
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
        (workspace / "panorama").mkdir(exist_ok=True)

    def _create_workspace_config(self, root: Path, manifest: ProjectManifest) -> None:
        """Generate workspace_config.yaml for SMAK."""
        indices = []
        for idx in manifest.indices:
            entry: dict = {
                "name": idx.name,
                "description": idx.description,
                "paths": idx.paths,
            }
            if idx.path_env:
                entry["path_env"] = idx.path_env
            indices.append(entry)

        config = {"indices": indices}
        _write_yaml(root / "workspace_config.yaml", config)

    def _install_smak_skills(
        self,
        root: Path,
        manifest: ProjectManifest,
        smak_path: Path | None,
    ) -> None:
        """Install SMAK skills into .claude/skills/ (HOW + WHERE layers).

        Copies smak-skill/ and optionally sos-smak-skill/ from the SMAK
        installation into the project's .claude/skills/ directory.
        """
        skills_dir = root / ".claude" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        if smak_path is None:
            # Try common locations
            candidates = [
                root / "deps" / "smak",
                root.parent / "smak",
                root.parent / "SMAK",
            ]
            for candidate in candidates:
                if (candidate / "smak-skill" / "SKILL.md").exists():
                    smak_path = candidate
                    break

        if smak_path and (smak_path / "smak-skill" / "SKILL.md").exists():
            # Copy smak-skill/ → .claude/skills/smak/
            smak_skill_dst = skills_dir / "smak"
            if not smak_skill_dst.exists():
                smak_skill_dst.mkdir(exist_ok=True)
                shutil.copy2(
                    smak_path / "smak-skill" / "SKILL.md",
                    smak_skill_dst / "SKILL.md",
                )

            # Conditionally copy sos-smak-skill/ → .claude/skills/sos-smak/
            if manifest.has_path_env:
                sos_src = smak_path / "sos-smak-skill" / "SKILL.md"
                if sos_src.exists():
                    sos_dst = skills_dir / "sos-smak"
                    if not sos_dst.exists():
                        sos_dst.mkdir(exist_ok=True)
                        shutil.copy2(sos_src, sos_dst / "SKILL.md")

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
                "regenerate SMAK config and All-Might workspace. "
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
                "SMAK index reference, key symbols, and current Power Level. "
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
            "1. Read `all-might/enrichment/tracker.yaml` for the last known Power Level.\n"
            "2. Scan all sidecar YAML files (`.*.sidecar.yaml`) across all SMAK indices.\n"
            "3. For each sidecar, count total symbols vs symbols with non-empty `intent`.\n"
            "4. Count total relations across all sidecars.\n"
            "5. Report the overall coverage percentage and per-index breakdown.\n"
            "6. Update `all-might/enrichment/tracker.yaml` with the new metrics.\n\n"
            "Display results in a clear table format with coverage bars.\n"
        )

        # /regenerate
        (commands_dir / "regenerate.md").write_text(
            "Regenerate the One For All skill with the latest project state.\n\n"
            "1. Read `all-might/config.yaml` for project configuration.\n"
            "2. Read `workspace_config.yaml` for SMAK index definitions.\n"
            "3. Scan all sidecar YAML files to find enriched symbols.\n"
            "4. Calculate current Power Level.\n"
            "5. Regenerate `.claude/skills/one-for-all/SKILL.md` with:\n"
            "   - Updated project overview\n"
            "   - Current index reference with descriptions\n"
            "   - Key enriched symbols summary (top symbols by relation count)\n"
            "   - Current Power Level metrics\n"
            "   - Updated architecture notes from high-coverage areas\n"
            "6. Update `all-might/enrichment/tracker.yaml` with new metrics.\n\n"
            "Report what changed in the regenerated skill.\n"
        )

        # /panorama
        (commands_dir / "panorama.md").write_text(
            "Export the knowledge graph as a panoramic visualization.\n\n"
            "1. Scan all sidecar YAML files across all SMAK indices.\n"
            "2. Build a graph of symbols (nodes) and relations (edges).\n"
            "3. Generate a Mermaid diagram showing the key relationships.\n"
            "4. Write output to `all-might/panorama/overview.mermaid`.\n"
            "5. Also write `all-might/panorama/graph.json` with the full graph data.\n"
            "6. Report summary statistics: node count, edge count, clusters, orphans.\n\n"
            "Focus on the most connected symbols — omit isolated nodes with no relations.\n"
        )

    def _update_claude_md(self, root: Path, manifest: ProjectManifest) -> None:
        """Append All-Might baseline instructions to .claude/CLAUDE.md."""
        claude_dir = root / ".claude"
        claude_dir.mkdir(exist_ok=True)
        claude_md = claude_dir / "CLAUDE.md"

        marker = "<!-- ALL-MIGHT -->"
        allmight_section = f"""{marker}
## All-Might: Active Knowledge Graph

This project uses **All-Might** for active knowledge graph management on top of SMAK.

- **Skills**: Check `.claude/skills/` for available skills (one-for-all, enrichment, smak)
- **Commands**: `/power-level`, `/regenerate`, `/panorama`
- **Workspace**: `all-might/` contains config, enrichment tracker, and panorama exports
- **SMAK config**: `workspace_config.yaml` defines the semantic indices

### Quick Start
1. The `one-for-all` skill auto-loads with project context
2. Use SMAK tools (search, enrich_symbol, etc.) as guided by the `smak` skill
3. Follow the `enrichment-protocol` skill to contribute knowledge as you work
4. Run `/power-level` to check coverage, `/regenerate` to update skills
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
        return f"""# Detroit SMAK — Project Bootstrap

Re-initialize the All-Might workspace for **{manifest.name}**.

## What this does

1. Re-scan the project directory for structural changes
2. Update `workspace_config.yaml` with new/changed directories
3. Regenerate `all-might/config.yaml`
4. Regenerate all All-Might skills (one-for-all, enrichment)
5. Optionally trigger SMAK `ingest` for new indices

## When to use

- Project structure has significantly changed (new directories, languages)
- New team members need a fresh workspace setup
- After major refactoring

## Steps

1. Run `allmight init {manifest.root_path}` OR manually:
   - Scan the project directory structure
   - Compare with existing `all-might/config.yaml`
   - Update `workspace_config.yaml` indices
   - Regenerate `.claude/skills/one-for-all/SKILL.md`
   - Regenerate `.claude/skills/enrichment/SKILL.md`
2. If new indices were added, run SMAK `ingest` for each new index
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

> This skill works alongside the `smak` skill. For SMAK MCP tool reference
> (search, enrich_symbol, lookup, etc.), see that skill.

## Project Overview

- **Name**: {manifest.name}
- **Languages**: {', '.join(manifest.languages) or 'Not yet detected'}
- **Frameworks**: {', '.join(manifest.frameworks) or 'Not yet detected'}

{dir_map}

## SMAK Index Reference

{index_table}

Use `describe_workspace(config="./workspace_config.yaml")` to verify indices are active.

## Key Symbols

> No symbols have been enriched yet. As you work with this project and use
> `enrich_symbol` to annotate code, this section will be populated when you
> run `/regenerate`.

## Power Level

- **Coverage**: 0% (fresh workspace)
- **Enriched symbols**: 0
- **Total relations**: 0

Run `/power-level` to get current metrics, or `/regenerate` to update this skill.

## Getting Started

1. Run `describe_workspace(config="./workspace_config.yaml")` to see available indices
2. Use `search(config="./workspace_config.yaml", query="...", index="...")` to explore
3. When you understand a symbol's purpose, enrich it (see the `enrichment-protocol` skill)
4. Run `/power-level` periodically to track progress
"""

    def _enrichment_skill_body(self) -> str:
        """Generate the body for enrichment/SKILL.md."""
        return """# Enrichment Protocol — Enrich As You Work

> This is an **advisory** protocol. Follow it naturally as you work —
> don't treat it as a mandatory checklist.

## When to Enrich

### On reading and understanding code
When you read a symbol (function, class, module) and understand its purpose:
- If the sidecar has no `intent` for this symbol → set it via `enrich_symbol`
- Write intent as a **human-readable description** of what the code does and why

### On discovering relationships
When you notice that two entities are related:
- Code ↔ Issue: a function relates to a bug report or feature request
- Code ↔ Test: a function has specific test cases
- Code ↔ Doc: a module is documented somewhere
- Code ↔ Code: two modules collaborate or one depends on the other

Link them via `enrich_symbol(..., relations=[target_uid])`.
Always `lookup` the target UID first to verify it exists.

### On modifying code
After changing code:
- Check if the sidecar intent is still accurate
- Update intent if the purpose changed
- Add relations to any new dependencies you introduced

## How to Enrich

```python
# 1. Set intent for a symbol you understood
enrich_symbol(
    config="./workspace_config.yaml",
    file_path="src/module.py",       # exact_relative_path from search
    symbol="ClassName.method_name",   # short name, not full UID
    intent="Validates user input and returns sanitized data",
    index="source_code"
)

# 2. Link a code symbol to a related issue
enrich_symbol(
    config="./workspace_config.yaml",
    file_path="src/module.py",
    symbol="ClassName.method_name",
    relations=["./issues/bug-123.md::*"],
    index="source_code"
)
```

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
