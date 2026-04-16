"""Detroit SMAK Initializer — one punch creates the entire workspace.

Takes a ProjectManifest from the Scanner and generates:
- knowledge_graph/ directory
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
        force: bool = False,
    ) -> None:
        """Execute Detroit SMAK — bootstrap the entire workspace.

        Args:
            manifest: Project characteristics from the Scanner.
            force: If True, overwrite everything even on re-init.
        """
        root = manifest.root_path
        allmight_dir = root / ".allmight"
        is_reinit = allmight_dir.is_dir() and not force

        # 1. Create knowledge_graph/ (always safe — mkdir exist_ok)
        self._create_metadata(root, manifest)

        if is_reinit:
            # Re-init: stage templates, don't overwrite working files
            self._stage_templates(root, manifest)
        else:
            # First init (or --force): write everything directly
            self._generate_commands(root, manifest)
            self._update_claude_md(root, manifest)
            self._create_opencode_compat(root)

            # Create .allmight/ marker (clean up any stale templates)
            allmight_dir.mkdir(exist_ok=True)
            templates_dir = allmight_dir / "templates"
            if templates_dir.exists():
                import shutil
                shutil.rmtree(templates_dir)

    def _create_metadata(self, root: Path, manifest: ProjectManifest) -> None:
        """Create knowledge_graph/ at the project root.

        Note: config.yaml is NOT created here — it belongs to SMAK workspaces
        under knowledge_graph/*/config.yaml, not the All-Might project root.
        """
        # knowledge_graph/ — workspace container (SMAK workspaces live here)
        (root / "knowledge_graph").mkdir(exist_ok=True)

    def _stage_templates(
        self,
        root: Path,
        manifest: ProjectManifest,
    ) -> None:
        """Stage new templates to .allmight/templates/ for agent-driven /sync.

        Called on re-init when .allmight/ already exists.  Writes the same
        content that first-init would write, but to .allmight/templates/
        instead of the working locations.
        """
        tpl = root / ".allmight" / "templates"

        # --- Commands ---
        cmds_tpl = tpl / "commands"
        cmds_tpl.mkdir(parents=True, exist_ok=True)

        self._stage_command_content(cmds_tpl, manifest)

        # --- CLAUDE.md sections ---
        marker_am = "<!-- ALL-MIGHT -->"
        allmight_section = self._claude_md_section(manifest)
        (tpl / "claude-md-section.md").write_text(allmight_section)

        # --- Install /sync skill + command (directly, not staged) ---
        self._install_sync_skill(root)

    def _stage_command_content(self, cmds_tpl: Path, manifest: ProjectManifest) -> None:
        """Write fresh command template content to staging dir."""
        (cmds_tpl / "search.md").write_text(self._search_command_body())
        (cmds_tpl / "enrich.md").write_text(
            self._enrich_command_body(manifest.has_path_env)
        )
        (cmds_tpl / "ingest.md").write_text(self._ingest_command_body())
        (cmds_tpl / "corpus-link.md").write_text(self._corpus_link_command_body())
        (cmds_tpl / "corpus-unlink.md").write_text(self._corpus_unlink_command_body())
        (cmds_tpl / "corpus-list.md").write_text(self._corpus_list_command_body())

    def _install_sync_skill(self, root: Path) -> None:
        """Install /sync skill and command directly (not staged)."""
        from .sync_skill_content import SYNC_SKILL_BODY, SYNC_COMMAND_BODY

        self._write_skill(
            root / ".claude" / "skills" / "sync" / "SKILL.md",
            name="sync",
            description=(
                "Reconcile staged All-Might templates or merge conflicts. "
                "Run after allmight init (re-init) or allmight merge."
            ),
            body=SYNC_SKILL_BODY,
        )
        commands_dir = root / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        (commands_dir / "sync.md").write_text(SYNC_COMMAND_BODY)

    def _claude_md_section(
        self,
        manifest: ProjectManifest,
        linked_corpora: list[str] | None = None,
    ) -> str:
        """Return the ALL-MIGHT section content for CLAUDE.md.

        Args:
            manifest: The project manifest.
            linked_corpora: Names of linked workspaces, if any.
        """
        marker = "<!-- ALL-MIGHT -->"
        sos_prereq = ""
        if manifest.has_path_env:
            sos_prereq = """
### SOS Environment Prerequisite

This project uses **CliosoftSOS**. Set `$DDI_ROOT_PATH` before opening
the project — it determines which source layer (online vs. version
control) All-Might operates on.
"""
        linked_section = ""
        if linked_corpora:
            names = ", ".join(f"`{n}`" for n in linked_corpora)
            linked_section = f"""
### Linked Corpora

Some corpora are **linked** from external locations and shared across
projects: {names}.  These appear as symlinks in `knowledge_graph/`.
Check `knowledge_graph/.links.yaml` for details.  Linked corpora may
be **read-only** — do not run `/ingest` or `/enrich` on them unless
they are marked writable.
"""
        return f"""{marker}
## All-Might: Active Knowledge Graph

This project has an **All-Might knowledge graph** — the agent can search
code by meaning, annotate what it learns, and remember across sessions.

### Capabilities

| Command | What it does |
|---------|-------------|
| `/search <query>` | Search code by meaning (not just keywords) |
| `/enrich` | Annotate a symbol — record what it does and what it relates to |
| `/ingest` | Build or rebuild the search index from source files |
| `/corpus-link` | Link an external shared corpus into this project |
| `/corpus-unlink` | Remove a linked corpus (source untouched) |
| `/corpus-list` | Show all linked corpora and their health status |

### Concepts

- **Corpus** = a vector index built from source files by `/ingest`. Source
  files are indexed **in-place** — nothing is copied into this project.
  Only the vector index (in `knowledge_graph/<workspace>/store/`) is local.
- **Annotation** = a note on a code symbol (function, class) describing its
  purpose and connections. Stored in `.sidecar.yaml` files beside the source code.

### How to learn the details

Each command (`/search`, `/enrich`, `/ingest`) has a detailed operational
guide in `.claude/commands/`.
{sos_prereq}{linked_section}
### Getting Started

1. `/ingest` — build the search index (first time)
2. `/search "query"` — explore the codebase
3. `/enrich` — annotate symbols as you learn them
"""

    def _search_command_body(self) -> str:
        """Return search.md command content."""
        return """\
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
"""

    def _ingest_command_body(self) -> str:
        """Return ingest.md command content."""
        return """\
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
"""

    # ------------------------------------------------------------------
    # Corpus linking commands
    # ------------------------------------------------------------------

    @staticmethod
    def _corpus_link_command_body() -> str:
        """Return corpus-link.md command content."""
        return """\
Link an external SMAK corpus into this project's knowledge graph.

Linked corpora are **shared** — multiple All-Might projects can point to
the same corpus directory via symlinks.  Each project keeps its own
memory and skills but shares the search index.

## How to execute

### 1. Validate the source

The source directory must be a valid SMAK workspace (contains `config.yaml`):

```bash
ls <source_path>/config.yaml
```

### 2. Create the symlink

```bash
ln -s <source_path> knowledge_graph/<name>
```

- `<source_path>` — absolute path to the external corpus directory
- `<name>` — local alias (defaults to the directory name)

### 3. Update the manifest

Append an entry to `knowledge_graph/.links.yaml`:

```yaml
links:
  - name: <name>
    source: <source_path>
    readonly: true
    description: "<optional description>"
```

Set `readonly: false` if this project should be allowed to run `/ingest`
or `/enrich` on the shared corpus.

## After linking

- Run `/search` to verify the linked corpus is discoverable
- Run `/corpus-list` to check link health
- The linked corpus appears alongside local workspaces in `knowledge_graph/`

## Important

- **Do not** run `/ingest` or `/enrich` on read-only linked corpora
- Unlinking removes only the symlink — the source directory is never touched
- If the source is moved, the symlink breaks — run `/corpus-list` to detect this
"""

    @staticmethod
    def _corpus_unlink_command_body() -> str:
        """Return corpus-unlink.md command content."""
        return """\
Remove a linked corpus from this project.

This only removes the **symlink** inside `knowledge_graph/` and its
entry in `.links.yaml`.  The source directory is **never** touched.

## How to execute

### 1. Verify it is a symlink (not a real directory)

```bash
readlink knowledge_graph/<name>
```

If this returns a path, it is a symlink and safe to unlink.
If it fails, the workspace is a real directory — do NOT remove it with this command.

### 2. Remove the symlink

```bash
rm knowledge_graph/<name>
```

### 3. Update the manifest

Remove the entry for `<name>` from `knowledge_graph/.links.yaml`.
If no entries remain, the file can be deleted.

## After unlinking

- The source corpus directory is untouched
- `/search` will no longer find results from this corpus
- Other projects that link to the same source are unaffected
"""

    @staticmethod
    def _corpus_list_command_body() -> str:
        """Return corpus-list.md command content."""
        return """\
Show all linked corpora and their health status.

## How to execute

### 1. Read the manifest

```bash
cat knowledge_graph/.links.yaml
```

This lists all linked corpora with their source paths and readonly flags.

### 2. Validate each link

For each entry in `.links.yaml`, check:

```bash
# Is the symlink present?
readlink knowledge_graph/<name>

# Does the target still exist and have a config?
ls "$(readlink -f knowledge_graph/<name>)/config.yaml"
```

### 3. Report status

For each linked corpus, report:
- **name** — the local alias
- **source** — where it points
- **mode** — `readonly` or `writable`
- **status** — `ok` (symlink valid, config.yaml present) or `broken`
- **description** — from the manifest

### 4. Also show local (non-linked) workspaces

List all directories in `knowledge_graph/` that are NOT symlinks:

```bash
for d in knowledge_graph/*/; do
  if [ ! -L "${d%/}" ]; then
    echo "local: $(basename $d)"
  fi
done
```

## Interpreting results

- **broken** links mean the source was moved or deleted — ask the user
  for the new location and re-link with `/corpus-link`
- **readonly** corpora should not be ingested or enriched from this project
"""

    def _generate_commands(self, root: Path, manifest: ProjectManifest) -> None:
        """Generate .claude/commands/ — thick operational guides."""
        # Ensure .claude/ structure exists (skills/ is a container for
        # user-installed skills and the sync skill on re-init)
        (root / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
        commands_dir = root / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)

        (commands_dir / "search.md").write_text(self._search_command_body())
        (commands_dir / "enrich.md").write_text(
            self._enrich_command_body(manifest.has_path_env)
        )
        (commands_dir / "ingest.md").write_text(self._ingest_command_body())
        (commands_dir / "corpus-link.md").write_text(self._corpus_link_command_body())
        (commands_dir / "corpus-unlink.md").write_text(self._corpus_unlink_command_body())
        (commands_dir / "corpus-list.md").write_text(self._corpus_list_command_body())

    def _update_claude_md(self, root: Path, manifest: ProjectManifest) -> None:
        """Append All-Might baseline instructions to CLAUDE.md at project root."""
        claude_md = root / "CLAUDE.md"

        marker = "<!-- ALL-MIGHT -->"
        allmight_section = self._claude_md_section(manifest)

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
- Path mismatch warnings in workspaces are normal — you're editing in a workspace while relations point to the canonical path
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

