"""Detroit SMAK Initializer — one punch creates the entire workspace.

Takes a ProjectManifest from the Scanner and generates:
- config.yaml (merged project metadata + corpus definitions)
- enrichment/ and panorama/ directories
- .claude/skills/ (layered skill composition)
- .claude/commands/ (slash commands)
- Updates CLAUDE.md at project root
"""

from __future__ import annotations

from pathlib import Path

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
        """Create knowledge_graph/ at the project root.

        Note: config.yaml is NOT created here — it belongs to SMAK workspaces
        under knowledge_graph/*/config.yaml, not the All-Might project root.
        """
        # knowledge_graph/ — workspace container (SMAK workspaces live here)
        (root / "knowledge_graph").mkdir(exist_ok=True)

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

SMAK searches the vector index — source files are never copied.
Results point back to files at their original paths.

## How to execute

```bash
smak search "<query>" --config knowledge_graph/<workspace>/config.yaml --index source_code --top-k 5 --json
```

To search across all corpora at once:
```bash
smak search-all "<query>" --config knowledge_graph/<workspace>/config.yaml --top-k 3 --json
```

To look up a specific symbol by UID:
```bash
smak lookup "<file_path>::<symbol_name>" --config knowledge_graph/<workspace>/config.yaml --index source_code --json
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

        (commands_dir / "enrich.md").write_text(
            self._enrich_command_body(manifest.has_path_env)
        )

        (commands_dir / "ingest.md").write_text("""\
Build the SMAK vector index from source files.

SMAK indexes source files **in-place** at their original paths.
No files are copied — only the vector index (in `store/`) is created
inside the workspace.

## When to run

- **First time**: after `allmight init` to build the initial index
- **After significant changes**: new files added, major refactoring
- **After adding a workspace**: to populate the new index

You do NOT need to re-ingest after enrichment — sidecars are separate
from the search index.

## How to execute

Rebuild all corpora in a workspace:
```bash
smak ingest --config knowledge_graph/<workspace>/config.yaml --json
```

Rebuild a specific corpus:
```bash
smak ingest --config knowledge_graph/<workspace>/config.yaml --index source_code --json
```

## What to expect

- The `store/` directory inside the workspace is populated with vector index data
- `/search` will return results from the indexed files
- Source files remain at their original paths — nothing is copied

## Troubleshooting

- If `smak` is not found, ensure SMAK is installed and on PATH
- Check `smak health --config knowledge_graph/<workspace>/config.yaml --json` for diagnostics
- List available corpora: `smak describe --config knowledge_graph/<workspace>/config.yaml --json`
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

### Concepts

- **Corpus** = a vector index built from source files by `/ingest`. Source
  files are indexed **in-place** — nothing is copied into this project.
  Only the vector index (in `knowledge_graph/<workspace>/store/`) is local.
- **Annotation** = a note on a code symbol (function, class) describing its
  purpose and connections. Stored in `.sidecar.yaml` files beside the source code.

### How to learn the details

The `one-for-all` skill (auto-loaded in `.claude/skills/`) contains the
complete operational guide: search engine commands, annotation workflow,
sidecar file format, and troubleshooting.

### Getting Started

1. `/ingest` — build the search index (first time)
2. `/search "query"` — explore the codebase
3. `/enrich` — annotate symbols as you learn them
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

    @staticmethod
    def _enrich_command_body(has_path_env: bool) -> str:
        """Return the enrich.md command content, SOS-aware when applicable."""
        base = """\
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
"""
        if not has_path_env:
            return base

        sos_section = """
## SOS Environment (CliosoftSOS)

In SOS environments, sidecar files are version-controlled objects.
Use `--dry-run` with the `cliosoft-sos` MCP tools to enrich safely:

### Recommended workflow: dry-run + cliosoft-sos MCP tools

1. **Preview** the enriched sidecar (no write):
   ```bash
   smak enrich --config config.yaml --index source_code \\
       --file <relative_path> --symbol "<SymbolName>" \\
       --intent "description" --dry-run --json
   ```
   This returns `sidecar_yaml` (the full sidecar content) and
   `sidecar_path` (where it belongs) without writing anything.

2. **Check out** the sidecar via `cliosoft-sos` MCP tool:
   - If the sidecar already exists: use `sos_checkout` on the sidecar path
   - If this is the first enrichment for the file: skip this step

3. **Write** the `sidecar_yaml` content to the sidecar path.

4. **Register** new sidecars (first enrichment only):
   - Use `sos_create` on the new sidecar file

5. **Check in** via `cliosoft-sos` MCP tool:
   - Use `sos_checkin` with a descriptive log message

### Alternative: direct enrich with SOS checkout

1. Use `sos_checkout` on the existing sidecar file
2. Run `smak enrich` normally (writes to the now-writable file)
3. Use `sos_checkin` to commit

### Important

- **Never** run `soscmd` directly — always use `cliosoft-sos` MCP tools
- Path mismatch warnings in workspaces are normal (see `sos-smak` skill)
- After check-in, re-ingest to update the search index
"""
        return base + sos_section

    def _create_opencode_compat(self, root: Path) -> None:
        """Create OpenCode-compatible symlinks.

        OpenCode prefers ``AGENTS.md`` over ``CLAUDE.md`` and looks in
        ``.opencode/`` alongside ``.claude/``.  We create symlinks so
        that a single set of files serves both tools.

        Symlinks created::

            AGENTS.md            → CLAUDE.md
            .opencode/skills/    → .claude/skills/
            .opencode/commands/  → .claude/commands/

        OpenCode also reads ``.claude/`` natively as a compatibility
        fallback, so the symlinks are an optimisation, not a hard
        requirement.
        """
        import os

        # --- AGENTS.md → CLAUDE.md ---
        agents_md = root / "AGENTS.md"
        claude_md = root / "CLAUDE.md"
        if claude_md.exists() and not agents_md.exists():
            os.symlink("CLAUDE.md", str(agents_md))

        # --- .opencode/ directory with symlinks into .claude/ ---
        opencode_dir = root / ".opencode"
        claude_dir = root / ".claude"

        if not claude_dir.is_dir():
            return  # Nothing to link to

        opencode_dir.mkdir(exist_ok=True)

        for subdir in ("skills", "commands"):
            source = claude_dir / subdir
            target = opencode_dir / subdir
            if source.is_dir() and not target.exists():
                # Relative symlink: .opencode/skills → ../.claude/skills
                os.symlink(
                    os.path.relpath(str(source), str(opencode_dir)),
                    str(target),
                )

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
>
> **Important**: SMAK indexes source files **in-place** at their original
> paths. Do NOT copy source code or documentation into this project.
> Only the vector index (`store/`) and SMAK config (`config.yaml`) live
> inside `knowledge_graph/` workspaces.

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

Each workspace has its own `config.yaml` (index definitions pointing to
source paths) and `store/` (vector index data). Source files stay at
their original paths — they are never copied.

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

## Getting Started

1. `/ingest` — build the search index (first time setup)
2. `/search "query"` — explore the codebase
3. `/enrich` — annotate symbols as you learn them
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
| `/enrich` | Add intent and/or relations |

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
