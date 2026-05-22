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
from ...core.skill_io import install_skill


class ProjectInitializer:
    """Creates the All-Might workspace and Claude Code integration files."""

    def __init__(self) -> None:
        # Defaults so legacy direct calls (e.g. merge's
        # ``_install_sync_skill``) work without going through
        # ``initialize()``. ``initialize()`` overwrites them when
        # called.
        self._instance_root: Path | None = None

    def initialize_globals(
        self,
        root: Path,
        manifest: ProjectManifest,
        *,
        force: bool = False,
        staging: bool = False,
    ) -> None:
        """Project-wide install — skills, commands, ``.allmight/`` setup.

        Called once per init (no ``Personality`` instance involved).
        Per-personality writes (instance dir, ROLE.md) live in
        :meth:`initialize`. Idempotent: write_guarded paths are safe
        to refresh on every call.
        """
        allmight_dir = root / ".allmight"

        if staging:
            self._stage_templates_globals(root, manifest)
            # Always stage removal of the deprecated commands so /sync
            # can clean up projects that still have enrich.md/ingest.md
            # from before the slash commands were retired.
            tpl = root / ".allmight" / "templates"
            tpl.mkdir(parents=True, exist_ok=True)
            (tpl / "remove.txt").write_text("enrich.md\ningest.md\n")
        else:
            self._generate_commands(root, manifest, force=force)
            self._install_onboard_skill(root, force=force)
            self._install_one_for_all_skill(root, force=force)
            self._install_all_for_one_skill(root, force=force)
            self._install_split_skill(root, force=force)

            allmight_dir.mkdir(exist_ok=True)
            templates_dir = allmight_dir / "templates"
            if templates_dir.exists():
                import shutil
                shutil.rmtree(templates_dir)
            # Clean up legacy enrich.md / ingest.md if they survived
            # from an older writable-mode install. The slash commands
            # are gone; the files should not linger.
            commands_dir = root / ".opencode" / "commands"
            for stale in ("enrich.md", "ingest.md"):
                stale_path = commands_dir / stale
                if stale_path.exists():
                    stale_path.unlink()

        (allmight_dir / "mode").write_text("read-only")

    def initialize(
        self,
        manifest: ProjectManifest,
        force: bool = False,
        instance_root: Path | None = None,
    ) -> None:
        """Execute Detroit SMAK — bootstrap globals + one personality instance.

        Args:
            manifest: Project characteristics from the Scanner.
            force: If True, overwrite everything even on re-init.
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
        is_reinit = (root / ".allmight").is_dir() and not force

        # Project-wide writes
        self.initialize_globals(
            root, manifest,
            force=force, staging=is_reinit,
        )

        # Per-instance writes
        self._create_metadata(root, manifest)
        if is_reinit:
            self._stage_templates_role(root, manifest)
        else:
            self._write_role_md(root, manifest, force=force)

    def _create_metadata(self, root: Path, manifest: ProjectManifest) -> None:
        """Create database/ inside the instance dir.

        Note: config.yaml is NOT created here — it belongs to SMAK workspaces
        under <db_root>/<workspace>/config.yaml, not the All-Might project root.
        """
        (self._instance_root / "database").mkdir(parents=True, exist_ok=True)

    def _stage_templates_globals(
        self,
        root: Path,
        manifest: ProjectManifest,
    ) -> None:
        """Re-init: stage project-wide templates to ``.allmight/templates/``.

        Globals only — per-personality ROLE.md staging lives in
        :meth:`_stage_templates_role`.
        """
        tpl = root / ".allmight" / "templates"
        cmds_tpl = tpl / "commands"
        cmds_tpl.mkdir(parents=True, exist_ok=True)
        self._stage_command_content(cmds_tpl, manifest)
        # /sync skill + command are written directly to .opencode/, not staged
        self._install_sync_skill(root)

    def _stage_templates_role(
        self,
        root: Path,
        manifest: ProjectManifest,
    ) -> None:
        """Re-init: stage one personality's ROLE.md to ``.allmight/templates/``."""
        tpl = root / ".allmight" / "templates"
        if self._instance_root is not None and self._instance_root != root:
            inst_rel = self._instance_root.relative_to(root)
            staged_role = tpl / inst_rel / "ROLE.md"
            staged_role.parent.mkdir(parents=True, exist_ok=True)
            write_guarded(staged_role, self._role_md_body(manifest), ALLMIGHT_MARKER_MD)
        else:
            # Legacy: stage the marker-fenced section file like before
            # so existing /sync flow + tests keep working.
            marker = "<!-- ALL-MIGHT -->"
            body = self._role_md_body(manifest)
            if body.startswith(ALLMIGHT_MARKER_MD):
                body = body[len(ALLMIGHT_MARKER_MD):].lstrip("\n")
            tpl.mkdir(parents=True, exist_ok=True)
            (tpl / "claude-md-section.md").write_text(f"{marker}\n{body}")

    def _stage_command_content(
        self, cmds_tpl: Path, manifest: ProjectManifest,
    ) -> None:
        """Write fresh command template content to staging dir."""
        write_guarded(
            cmds_tpl / "search.md",
            self._search_command_body(),
            ALLMIGHT_MARKER_MD,
        )

    def _install_sync_skill(self, root: Path) -> None:
        """Install /sync skill + command (project-wide; not staged)."""
        from .sync_skill_content import SYNC_SKILL_BODY, SYNC_COMMAND_BODY

        install_skill(
            root,
            name="sync",
            description=(
                "Reconcile staged All-Might templates with user-customized "
                "files. Run after allmight init on a re-initialized project."
            ),
            skill_body=SYNC_SKILL_BODY,
            command_body=SYNC_COMMAND_BODY,
        )

    def _install_one_for_all_skill(self, root: Path, *, force: bool = False) -> None:
        """Install /one-for-all skill + command (1 personality → 1 bundle)."""
        from .one_for_all_skill_content import (
            ONE_FOR_ALL_COMMAND_BODY,
            ONE_FOR_ALL_SKILL_BODY,
        )

        install_skill(
            root,
            name="one-for-all",
            description=(
                "Bundle a personality for transfer to another All-Might "
                "project (1 → 1). Applies per-capability export rules "
                "and reviews content for PII before writing the bundle."
            ),
            skill_body=ONE_FOR_ALL_SKILL_BODY,
            command_body=ONE_FOR_ALL_COMMAND_BODY,
            force=force,
        )

    def _install_all_for_one_skill(self, root: Path, *, force: bool = False) -> None:
        """Install /all-for-one skill + command (N sources → 1 target)."""
        from .all_for_one_skill_content import (
            ALL_FOR_ONE_COMMAND_BODY,
            ALL_FOR_ONE_SKILL_BODY,
        )

        install_skill(
            root,
            name="all-for-one",
            description=(
                "Absorb multiple personalities (bundles or in-project) "
                "into a single target (N → 1). Handles per-capability "
                "merge conflicts and ROLE.md prose reconciliation."
            ),
            skill_body=ALL_FOR_ONE_SKILL_BODY,
            command_body=ALL_FOR_ONE_COMMAND_BODY,
            force=force,
        )

    def _install_split_skill(self, root: Path, *, force: bool = False) -> None:
        """Install /split skill + command (1 personality → 1 personality, in-project).

        Personality-lifecycle refactor: extract a slice of one
        personality's memory + ROLE.md scope into another (new or
        existing) personality in the same project. Database
        workspaces are deliberately untouched (see skill body for
        rationale). Trigger is manual-only — no plugin, no
        "When to suggest" entry in the AGENTS.md primer.
        """
        from .split_skill_content import (
            SPLIT_COMMAND_BODY,
            SPLIT_SKILL_BODY,
        )

        install_skill(
            root,
            name="split",
            description=(
                "Refactor responsibilities within a project — extract "
                "memory and scope from one personality into another "
                "(existing or new). Same-project 1 → 1. Rare; manual "
                "only."
            ),
            skill_body=SPLIT_SKILL_BODY,
            command_body=SPLIT_COMMAND_BODY,
            force=force,
        )

    def _install_onboard_skill(self, root: Path, *, force: bool = False) -> None:
        """Install /onboard skill + command on every fresh init.

        Stage 2 of bootstrap; must exist immediately after the first
        ``allmight init`` so the user has somewhere to run it.
        """
        from .onboard_skill_content import ONBOARD_SKILL_BODY, ONBOARD_COMMAND_BODY

        install_skill(
            root,
            name="onboard",
            description=(
                "Finish All-Might setup: capture user intent in each "
                "personality's ROLE.md and classify the folders listed "
                "during init."
            ),
            skill_body=ONBOARD_SKILL_BODY,
            command_body=ONBOARD_COMMAND_BODY,
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

    def _role_md_body(self, manifest: ProjectManifest) -> str:
        """Return the corpus keeper's ROLE.md body.

        The knowledge graph is read-only: agents search the SMAK
        index via ``/search`` but never mutate the corpus through
        All-Might slash commands. Index builds and sidecar edits
        are handled directly by SMAK CLI / SOS workflows outside the
        agent surface.
        """
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
modify corpora through agent slash commands. Index rebuilds and sidecar
edits happen out-of-band via the SMAK CLI.

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

    def _search_command_body(self) -> str:
        """Return search.md command content (generic — agent resolves <active>).

        The ``db_root`` path is prefixed with ``${ALLMIGHT_PROJECT_ROOT:-.}``
        so the emitted ``smak search`` invocations resolve correctly in
        both single-user mode (env unset → cwd-relative) and shared-agent
        mode (env points at the shared project root).
        """
        from ...core.project_root import BASH_PROJECT_ROOT_PREFIX
        from ...core.routing import ROUTING_PREAMBLE
        db_root = (
            f"{BASH_PROJECT_ROOT_PREFIX}/personalities/<active>/database"
        )
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
  sidecar for its annotated intent and relations.
- Present results to the user in terms of "knowledge graph" — do not mention SMAK.
"""

    def _generate_commands(
        self,
        root: Path,
        manifest: ProjectManifest,
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

    def _write_role_md(
        self,
        root: Path,
        manifest: ProjectManifest,
        force: bool = False,
    ) -> None:
        """Write the corpus keeper's role description **once**.

        ROLE.md is user-owned: ``/onboard`` rewrites the body to
        describe the personality's actual role, and the All-Might
        marker on line 1 typically survives that edit. Pre-fix,
        ``write_guarded`` saw the marker and overwrote on every
        re-init; under ``--force`` the overwrite happened even
        without a marker, silently destroying user content.

        ROLE.md is now **write-once at the framework level**. We
        emit a starter template only when no file exists. ``--force``
        is reserved for plugin/command/hook regeneration; user role
        descriptions are always preserved. To deliberately reset
        ROLE.md, the user removes the file and re-runs init.

        ``force`` is accepted for backward-compat in the call signature
        but intentionally ignored on this path.

        Legacy direct-call mode (no ``instance_root`` — used by tests,
        clone, merge that bypass the registry) still splices a
        marker-fenced section directly into root ``AGENTS.md``. That
        path goes away once those callers migrate to the registry-
        driven flow (tracked in §B.6.3).
        """
        if self._instance_root is not None and self._instance_root != root:
            target = self._instance_root / "ROLE.md"
            if target.exists():
                # User-owned. Never overwrite — including under --force.
                return
            self._instance_root.mkdir(parents=True, exist_ok=True)
            write_guarded(
                target,
                self._role_md_body(manifest),
                ALLMIGHT_MARKER_MD,
            )
        else:
            self._write_legacy_agents_md(root, manifest)

    def _write_legacy_agents_md(
        self, root: Path, manifest: ProjectManifest,
    ) -> None:
        """Splice the corpus section into root AGENTS.md (legacy path)."""
        agents_md = root / "AGENTS.md"
        if agents_md.is_symlink():
            agents_md.unlink()

        marker = "<!-- ALL-MIGHT -->"
        body = self._role_md_body(manifest)
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

