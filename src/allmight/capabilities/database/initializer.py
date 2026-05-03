"""Database capability initializer — bootstraps the knowledge-graph data dir.

Takes a ProjectManifest from the Scanner and generates:
- database/ directory (per-instance)
- .opencode/commands/ (slash commands) or per-instance commands
- ROLE.md inside the personality dir
"""

from __future__ import annotations

from pathlib import Path

from ...core.domain import ProjectManifest
from ...core.markers import ALLMIGHT_MARKER_MD
from ...core.safe_write import write_guarded


class ProjectInitializer:
    """Creates the All-Might workspace and Claude Code integration files."""

    def __init__(self) -> None:
        # Defaults so legacy direct calls (e.g. merge's
        # ``_install_sync_skill``) work without going through
        # ``initialize()``. ``initialize()`` overwrites them when
        # called.
        self._instance_root: Path | None = None

    def initialize(
        self,
        manifest: ProjectManifest,
        force: bool = False,
        writable: bool = False,
        instance_root: Path | None = None,
    ) -> None:
        """Execute Detroit SMAK — bootstrap the entire workspace.

        Args:
            manifest: Project characteristics from the Scanner.
            force: If True, overwrite everything even on re-init.
            writable: If True, generate ingest/enrich commands (full access).
                      Default is read-only (search only).
            instance_root: Personality instance directory under
                ``personalities/<name>/``. The per-instance content
                (database/, skills/, commands/) lives here. If ``None``,
                defaults to ``manifest.root_path`` for callers (clone,
                merge) that haven't migrated yet.
        """
        root = manifest.root_path
        if instance_root is None:
            instance_root = root
        self._instance_root = instance_root
        allmight_dir = root / ".allmight"
        is_reinit = allmight_dir.is_dir() and not force

        # Validate mode transition (applies to both re-init and --force)
        mode_file = allmight_dir / "mode"
        if mode_file.exists():
            current_mode = mode_file.read_text().strip()
            if current_mode == "read-only" and writable:
                raise ValueError(
                    "Cannot upgrade from read-only to writable mode. "
                    "Read-only projects cannot be converted to writable."
                )

        # 1. Create database/ (always safe — mkdir exist_ok)
        self._create_metadata(root, manifest)

        if is_reinit:
            # Detect mode downgrade before staging
            current_mode = (
                mode_file.read_text().strip() if mode_file.exists() else None
            )

            # Re-init: stage templates, don't overwrite working files
            self._stage_templates(root, manifest, writable=writable)

            # If downgrading writable → read-only, stage removal list
            if current_mode == "writable" and not writable:
                tpl = root / ".allmight" / "templates"
                tpl.mkdir(parents=True, exist_ok=True)
                (tpl / "remove.txt").write_text("enrich.md\ningest.md\n")

            # Update mode file
            (allmight_dir / "mode").write_text(
                "writable" if writable else "read-only"
            )
        else:
            # First init (or --force): write everything directly
            self._generate_commands(root, manifest, writable=writable, force=force)
            self._write_role_md(root, manifest, writable=writable, force=force)
            self._install_onboard_skill(root, force=force)
            self._install_export_skill(root, force=force)

            # Create .allmight/ marker (clean up any stale templates)
            allmight_dir.mkdir(exist_ok=True)
            templates_dir = allmight_dir / "templates"
            if templates_dir.exists():
                import shutil
                shutil.rmtree(templates_dir)

            # Persist access mode
            (allmight_dir / "mode").write_text(
                "writable" if writable else "read-only"
            )

    def _create_metadata(self, root: Path, manifest: ProjectManifest) -> None:
        """Create database/ inside the instance dir.

        Note: config.yaml is NOT created here — it belongs to SMAK workspaces
        under <db_root>/<workspace>/config.yaml, not the All-Might project root.
        """
        (self._instance_root / "database").mkdir(parents=True, exist_ok=True)

    def _stage_templates(
        self,
        root: Path,
        manifest: ProjectManifest,
        writable: bool = False,
    ) -> None:
        """Stage new templates to .allmight/templates/ for agent-driven /sync.

        Called on re-init when .allmight/ already exists. Writes the same
        content that first-init would write, but to
        ``.allmight/templates/`` (mirroring the project layout) instead
        of the live locations.
        """
        tpl = root / ".allmight" / "templates"

        # --- Commands (still under .allmight/templates/commands/ for
        # backwards compat with existing /sync flow; instance-aware
        # staging is a follow-up) ---
        cmds_tpl = tpl / "commands"
        cmds_tpl.mkdir(parents=True, exist_ok=True)
        self._stage_command_content(cmds_tpl, manifest, writable=writable)

        # --- ROLE / AGENTS section staged ---
        if self._instance_root is not None and self._instance_root != root:
            # Registry-driven: mirror project layout for /sync to find.
            inst_rel = self._instance_root.relative_to(root)
            staged_role = tpl / inst_rel / "ROLE.md"
            staged_role.parent.mkdir(parents=True, exist_ok=True)
            write_guarded(staged_role, self._role_md_body(manifest, writable=writable), ALLMIGHT_MARKER_MD)
        else:
            # Legacy: stage the marker-fenced section file like before
            # so existing /sync flow + tests keep working.
            marker = "<!-- ALL-MIGHT -->"
            body = self._role_md_body(manifest, writable=writable)
            if body.startswith(ALLMIGHT_MARKER_MD):
                body = body[len(ALLMIGHT_MARKER_MD):].lstrip("\n")
            (tpl / "claude-md-section.md").write_text(f"{marker}\n{body}")

        # --- Install /sync skill + command (directly, not staged) ---
        self._install_sync_skill(root)

    def _stage_command_content(
        self, cmds_tpl: Path, manifest: ProjectManifest, writable: bool = False,
    ) -> None:
        """Write fresh command template content to staging dir."""
        write_guarded(
            cmds_tpl / "search.md",
            self._search_command_body(),
            ALLMIGHT_MARKER_MD,
        )
        if writable:
            write_guarded(
                cmds_tpl / "enrich.md",
                self._enrich_command_body(manifest.has_path_env),
                ALLMIGHT_MARKER_MD,
            )
            write_guarded(
                cmds_tpl / "ingest.md",
                self._ingest_command_body(),
                ALLMIGHT_MARKER_MD,
            )

    def _install_sync_skill(self, root: Path) -> None:
        """Install /sync skill and command directly (not staged).

        Writes inside the instance dir (``skills/`` and ``commands/``);
        composition then symlinks them under root ``.opencode/``. When
        the legacy fallback is active (``instance_root == root``), the
        old ``.opencode/`` paths are used directly.
        """
        from .sync_skill_content import SYNC_SKILL_BODY, SYNC_COMMAND_BODY

        skill_dir, commands_dir = self._agent_surface_dirs(root)
        self._write_skill(
            skill_dir / "sync" / "SKILL.md",
            name="sync",
            description=(
                "Reconcile staged All-Might templates with user-customized "
                "files. Run after allmight init on a re-initialized project."
            ),
            body=SYNC_SKILL_BODY,
        )
        commands_dir.mkdir(parents=True, exist_ok=True)
        write_guarded(commands_dir / "sync.md", SYNC_COMMAND_BODY, ALLMIGHT_MARKER_MD)

    def _install_export_skill(self, root: Path, *, force: bool = False) -> None:
        """Install /export and /one-for-all skill + commands.

        ``/export`` is agent-driven (PII review, per-capability
        rules). This installs the skill body and the companion
        slash command so the user can invoke it after any
        ``allmight init``.

        ``/one-for-all`` is a permanent alias whose body is identical
        to ``/export``'s. It signals the *direction* of the operation
        (passing a personality on to another project) and matches the
        ``allmight all-for-one`` import alias added in cli.py. Both
        names are first-class — there is no deprecation path.
        """
        from .export_skill_content import EXPORT_SKILL_BODY, EXPORT_COMMAND_BODY

        skill_dir, commands_dir = self._agent_surface_dirs(root)
        skill_description = (
            "Bundle a personality for transfer to another All-Might "
            "project. Applies per-capability export rules and "
            "reviews content for PII before writing the bundle."
        )
        # /export — the original verb.
        self._write_skill(
            skill_dir / "export" / "SKILL.md",
            name="export",
            description=skill_description,
            body=EXPORT_SKILL_BODY,
        )
        # /one-for-all — alias whose body is identical to /export's.
        # Same skill, two callable names.
        self._write_skill(
            skill_dir / "one-for-all" / "SKILL.md",
            name="one-for-all",
            description=skill_description,
            body=EXPORT_SKILL_BODY,
        )

        commands_dir.mkdir(parents=True, exist_ok=True)
        write_guarded(
            commands_dir / "export.md",
            EXPORT_COMMAND_BODY,
            ALLMIGHT_MARKER_MD,
            force=force,
        )
        write_guarded(
            commands_dir / "one-for-all.md",
            EXPORT_COMMAND_BODY,
            ALLMIGHT_MARKER_MD,
            force=force,
        )

    def _install_onboard_skill(self, root: Path, *, force: bool = False) -> None:
        """Install /onboard skill + command on every fresh init.

        Unlike /sync (only useful on re-init), /onboard is the
        agent-side stage 2 of bootstrap and must exist immediately
        after the first ``allmight init`` so the user has somewhere to
        run it.
        """
        from .onboard_skill_content import ONBOARD_SKILL_BODY, ONBOARD_COMMAND_BODY

        skill_dir, commands_dir = self._agent_surface_dirs(root)
        self._write_skill(
            skill_dir / "onboard" / "SKILL.md",
            name="onboard",
            description=(
                "Finish All-Might setup: capture user intent in each "
                "personality's ROLE.md and classify the folders listed "
                "during init."
            ),
            body=ONBOARD_SKILL_BODY,
        )
        commands_dir.mkdir(parents=True, exist_ok=True)
        write_guarded(
            commands_dir / "onboard.md",
            ONBOARD_COMMAND_BODY,
            ALLMIGHT_MARKER_MD,
            force=force,
        )

    def _agent_surface_dirs(self, root: Path) -> tuple[Path, Path]:
        """Return (skills_dir, commands_dir) — always project-global ``.opencode/``.

        Part-D: capability templates write the agent surface once into
        the global ``.opencode/{skills,commands}/``. ``compose`` then
        creates upward symlinks ``personalities/<p>/{skills,commands}``
        back into the global set. Bodies are generic
        (``personalities/<active>/...`` placeholders), so a single
        global write serves every personality.
        """
        return root / ".opencode" / "skills", root / ".opencode" / "commands"

    def _role_md_body(
        self, manifest: ProjectManifest, writable: bool = False,
    ) -> str:
        """Return the corpus keeper's ROLE.md body."""
        if writable:
            return self._role_md_writable(manifest)
        return self._role_md_readonly(manifest)

    def _role_md_readonly(self, manifest: ProjectManifest) -> str:
        """ROLE.md for the corpus keeper, read-only mode."""
        db_root = "personalities/<active>/database"
        sos_prereq = ""
        if manifest.has_path_env:
            sos_prereq = """
### SOS Environment Prerequisite

This project uses **CliosoftSOS**. Set `$DDI_ROOT_PATH` before opening
the project — it determines which source layer (online vs. version
control) the corpus operates on.
"""
        return f"""{ALLMIGHT_MARKER_MD}
# Corpus Keeper

You manage a **knowledge graph** for this project — searching code by
meaning and tracking what the agent has learned across sessions.

**Access: read-only** — you may search the knowledge graph but must NOT
modify corpora (no ingesting, no enriching, no sidecar edits).

### Capabilities

| Command | What it does |
|---------|-------------|
| `/search <query>` | Search code by meaning (not just keywords) |

### Concepts

- **Corpus** (= **workspace**) — one independently-indexed source domain.
  Each corpus maps to `{db_root}/<workspace>/` and has its own SMAK
  vector store. A project may have multiple corpora (e.g. `stdcell`, `pll`).
  Source files are indexed **in-place** — only the index is stored locally.
  The corpus name and workspace name are the same string throughout All-Might.

### How to learn the details

The `/search` command has a detailed operational guide in `.opencode/commands/`.
{sos_prereq}
### Getting Started

1. `/search "query"` — explore the codebase
"""

    def _role_md_writable(self, manifest: ProjectManifest) -> str:
        """ROLE.md for the corpus keeper, writable mode."""
        db_root = "personalities/<active>/database"
        sos_prereq = ""
        if manifest.has_path_env:
            sos_prereq = """
### SOS Environment Prerequisite

This project uses **CliosoftSOS**. Set `$DDI_ROOT_PATH` before opening
the project — it determines which source layer (online vs. version
control) the corpus operates on.
"""
        return f"""{ALLMIGHT_MARKER_MD}
# Corpus Keeper

You manage a **knowledge graph** for this project — searching code by
meaning, annotating what the agent learns, and tracking knowledge
across sessions.

### Capabilities

| Command | What it does |
|---------|-------------|
| `/search <query>` | Search code by meaning (not just keywords) |
| `/enrich` | Annotate a symbol — record what it does and what it relates to |
| `/ingest` | Build or rebuild the search index from source files |

### Concepts

- **Corpus** (= **workspace**) — one independently-indexed source domain.
  Each corpus maps to `{db_root}/<workspace>/` and has its own SMAK
  vector store. A project may have multiple corpora (e.g. `stdcell`, `pll`).
  Source files are indexed **in-place** — only the index is stored locally.
  The corpus name and workspace name are the same string throughout All-Might.
- **Annotation** = a note on a code symbol (function, class) describing its
  purpose and connections. Stored in `.sidecar.yaml` files beside the source code.

### How to learn the details

Each command (`/search`, `/enrich`, `/ingest`) has a detailed operational
guide in `.opencode/commands/`.
{sos_prereq}
### Getting Started

1. `/ingest` — build the search index (first time)
2. `/search "query"` — explore the codebase
3. `/enrich` — annotate symbols as you learn them
"""

    def _search_command_body(self) -> str:
        """Return search.md command content (generic — agent resolves <active>)."""
        from ...core.routing import ROUTING_PREAMBLE
        db_root = "personalities/<active>/database"
        return ROUTING_PREAMBLE + self._SEARCH_BODY.replace("{db_root}", db_root)

    _SEARCH_BODY = """\
Search the codebase by semantic meaning.

SMAK searches the vector index — source files are never copied.
Results point back to files at their original paths.

## How to execute

```bash
smak search "<query>" --config {db_root}/<workspace>/config.yaml --index source_code --top-k 5 --json
```

To search across all corpora at once:
```bash
smak search-all "<query>" --config {db_root}/<workspace>/config.yaml --top-k 3 --json
```

To look up a specific symbol by UID:
```bash
smak lookup "<file_path>::<symbol_name>" --config {db_root}/<workspace>/config.yaml --index source_code --json
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
        """Return ingest.md command content (generic — agent resolves <active>)."""
        from ...core.routing import ROUTING_PREAMBLE
        db_root = "personalities/<active>/database"
        return ROUTING_PREAMBLE + self._INGEST_BODY.replace("{db_root}", db_root)

    _INGEST_BODY = """\
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
smak ingest --config {db_root}/<workspace>/config.yaml --json
```

Rebuild a specific corpus:
```bash
smak ingest --config {db_root}/<workspace>/config.yaml --index source_code --json
```

## What to expect

- The `store/` directory inside the workspace is populated with vector index data
- `/search` will return results from the indexed files
- Source files remain at their original paths — nothing is copied

## Troubleshooting

- If `smak` is not found, ensure SMAK is installed and on PATH
- Check `smak health --config {db_root}/<workspace>/config.yaml --json` for diagnostics
- List available corpora: `smak describe --config {db_root}/<workspace>/config.yaml --json`
"""

    def _generate_commands(
        self,
        root: Path,
        manifest: ProjectManifest,
        writable: bool = False,
        force: bool = False,
    ) -> None:
        """Generate database capability command guides inside the instance dir."""
        _, commands_dir = self._agent_surface_dirs(root)
        commands_dir.mkdir(parents=True, exist_ok=True)

        write_guarded(
            commands_dir / "search.md",
            self._search_command_body(),
            ALLMIGHT_MARKER_MD,
            force=force,
        )
        if writable:
            write_guarded(
                commands_dir / "enrich.md",
                self._enrich_command_body(manifest.has_path_env),
                ALLMIGHT_MARKER_MD,
                force=force,
            )
            write_guarded(
                commands_dir / "ingest.md",
                self._ingest_command_body(),
                ALLMIGHT_MARKER_MD,
                force=force,
            )

    def _write_role_md(
        self,
        root: Path,
        manifest: ProjectManifest,
        writable: bool = False,
        force: bool = False,
    ) -> None:
        """Write the corpus keeper's role description.

        Registry-driven mode (``instance_root`` set and != ``root``):
        writes ``personalities/<n>/ROLE.md``; the registry's
        ``compose_agents_md`` stitches every instance's ROLE.md into
        the single root ``AGENTS.md`` afterwards.

        Legacy direct-call mode (no ``instance_root`` — used by tests,
        clone, merge that bypass the registry): writes a marker-fenced
        section directly into root ``AGENTS.md``. This path goes away
        once those callers migrate to the registry-driven flow
        (tracked in §B.6.3).
        """
        if self._instance_root is not None and self._instance_root != root:
            self._instance_root.mkdir(parents=True, exist_ok=True)
            write_guarded(
                self._instance_root / "ROLE.md",
                self._role_md_body(manifest, writable=writable),
                ALLMIGHT_MARKER_MD,
                force=force,
            )
        else:
            self._write_legacy_agents_md(root, manifest, writable=writable)

    def _write_legacy_agents_md(
        self, root: Path, manifest: ProjectManifest, writable: bool = False,
    ) -> None:
        """Splice the corpus section into root AGENTS.md (legacy path)."""
        agents_md = root / "AGENTS.md"
        if agents_md.is_symlink():
            agents_md.unlink()

        marker = "<!-- ALL-MIGHT -->"
        body = self._role_md_body(manifest, writable=writable)
        if body.startswith(ALLMIGHT_MARKER_MD):
            body = body[len(ALLMIGHT_MARKER_MD):].lstrip("\n")
        section = f"{marker}\n{body}"

        if agents_md.exists():
            content = agents_md.read_text()
            if marker in content:
                before = content[: content.index(marker)]
                content = before.rstrip() + "\n\n" + section
            else:
                content = content.rstrip() + "\n\n" + section
            agents_md.write_text(content)
        else:
            agents_md.write_text(f"# {manifest.name}\n\n{section}")

    @staticmethod
    def _enrich_command_body(has_path_env: bool) -> str:
        """Return the enrich.md command content, SOS-aware when applicable.

        Prepends the routing preamble so the agent resolves
        ``<active>`` before substituting it into the SMAK paths
        below.
        """
        from ...core.routing import ROUTING_PREAMBLE
        base = """\
Annotate a code symbol with intent and/or relations.

## How to execute

Set intent (what the symbol does and why):
```bash
smak enrich --config personalities/<active>/database/<workspace>/config.yaml \\
    --index source_code \\
    --file <relative_path> --symbol "<SymbolName>" \\
    --intent "Human-readable description of purpose"
```

Add a relation to another symbol:
```bash
smak enrich --config personalities/<active>/database/<workspace>/config.yaml \\
    --index source_code \\
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
            return ROUTING_PREAMBLE + base

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
        return ROUTING_PREAMBLE + base + sos_section

    def _write_skill(
        self,
        path: Path,
        name: str,
        description: str,
        body: str,
        disable_model_invocation: bool = False,
    ) -> None:
        """Write a SKILL.md file with YAML frontmatter."""
        frontmatter_lines = [
            "---",
            f"name: {name}",
            f"description: {description}",
        ]
        if disable_model_invocation:
            frontmatter_lines.append("disable-model-invocation: true")
        frontmatter_lines.append("---")

        # Marker goes after the frontmatter so OpenCode still parses the
        # leading "---"; write_guarded sees it and won't re-prepend.
        content = (
            "\n".join(frontmatter_lines)
            + "\n\n"
            + ALLMIGHT_MARKER_MD
            + "\n\n"
            + body
        )
        write_guarded(path, content, ALLMIGHT_MARKER_MD)

