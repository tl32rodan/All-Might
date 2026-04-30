"""All-Might CLI — bootstrapping only.

All-Might is an **agent harness**, not a CLI tool.  The CLI exists only
for the one operation that cannot be agent-driven:

    allmight init [path]            — Bootstrap a workspace (includes memory)
    allmight clone <source> [path]  — Clone an All-Might project (read-only)
    allmight memory init [path]     — Re-initialize agent memory subsystem

Everything else is agent-driven through .claude/skills and commands.
The skills teach the agent how to call the underlying tools (smak CLI)
directly.
"""

from __future__ import annotations

import click

from . import __version__


@click.group()
@click.version_option(version=__version__, prog_name="allmight")
def main():
    """All-Might: Active Knowledge Graph Framework.

    Bootstrap a workspace, then let the agent drive via skills.
    """


# ------------------------------------------------------------------
# Bootstrapping
# ------------------------------------------------------------------

def _build_init_command() -> click.Command:
    """Build the ``init`` Click command with personality-contributed flags.

    The only universal option is ``--force``; everything else is
    declared by a personality template's ``cli_options`` and registered
    here at startup. This is the *core decoupling* from the old
    hardcoded ``--sos`` / ``--writable`` knobs — ``cli.py`` does not
    interpret them, it just forwards them as a raw dict to every
    ``Personality.options``.
    """
    from .core.personalities import discover

    cmd = click.Command("init", callback=_init_callback)
    cmd.help = (
        "Bootstrap a workspace with commands and agent memory.\n\n"
        "Scans the project, installs every discovered personality "
        "template, and composes their agent surface under .opencode/.\n\n"
        "On re-run (when .allmight/ exists), templates are staged to "
        ".allmight/templates/ instead of overwriting. Use --force to "
        "overwrite."
    )
    cmd.params.append(click.Argument(["path"], default=".", type=click.Path(exists=True)))
    cmd.params.append(click.Option(
        ["--force"], is_flag=True,
        help="Overwrite all files (ignore user customizations).",
    ))
    cmd.params.append(click.Option(
        ["--yes", "-y"], is_flag=True,
        help="Skip interactive prompts; accept template defaults.",
    ))
    seen: set[str] = set()
    for template in discover():
        for opt in template.cli_options:
            if opt.flag in seen:
                # Two templates contributed the same flag — surfaced
                # at startup so it can never silently shadow.
                raise RuntimeError(
                    f"flag collision on {opt.flag!r} between templates"
                )
            seen.add(opt.flag)
            cmd.params.append(click.Option(
                [opt.flag],
                is_flag=opt.is_flag,
                default=opt.default,
                help=opt.help,
            ))
    return cmd


def _init_callback(
    path: str,
    force: bool,
    yes: bool = False,
    **template_options: object,
) -> None:
    """Run the registry-driven init flow.

    ``template_options`` is the raw dict of every CliOption value. Each
    template's ``install`` reads what it cares about; the CLI never
    interprets the contents.

    When ``yes`` is False (default) and stdin is a TTY, the CLI prompts
    for the instance name of each personality and an optional list of
    project folders to register. The captured answers land in
    ``.allmight/onboard.yaml`` so the agent's ``/onboard`` skill can
    finish the qualitative setup later.
    """
    from pathlib import Path as P

    from .core.personalities import (
        InstallContext,
        Personality,
        RegistryEntry,
        compose,
        compose_agents_md,
        discover,
        slugify_instance_name,
        stage_compose_conflicts,
        write_init_scaffold,
        write_registry,
    )
    from .capabilities.database.scanner import ProjectScanner

    root = P(path).resolve()
    scanner = ProjectScanner()
    manifest = scanner.scan(root)

    allmight_dir = root / ".allmight"
    is_reinit = allmight_dir.is_dir() and not force

    templates = discover()

    # Decide instance names + folders. If onboard.yaml exists, reuse
    # what was captured before so re-init never asks the user the same
    # questions. Otherwise prompt (or use defaults under --yes).
    onboard_path = allmight_dir / "onboard.yaml"
    captured = _read_onboard_yaml(onboard_path)
    if captured is None:
        captured = _collect_onboard_answers(templates, manifest, interactive=not yes)
    instance_names = {row["template"]: row["instance"] for row in captured["personalities"]}

    write_init_scaffold(root)

    ctx = InstallContext(
        project_root=root,
        manifest=manifest,
        staging=is_reinit,
        force=force,
    )
    instances: list[Personality] = []
    notes: list[str] = []
    for template in templates:
        instance_name = instance_names.get(
            template.name,
            template.default_instance_name or f"{manifest.name}-{template.short_name}",
        )
        instance = Personality(
            template=template,
            project_root=root,
            name=instance_name,
            options=dict(template_options),
        )
        result = template.install(ctx, instance)
        notes.extend(result.notes)
        instances.append(instance)

    # Compose .opencode/ symlinks from each instance's surface.
    # Conflicts (user-authored files at our target paths) are NOT
    # silently overwritten — they're collected and staged so /sync can
    # walk the user through resolution.
    all_conflicts = []
    for instance in instances:
        all_conflicts.extend(compose(root, instance, force=force))
    stage_compose_conflicts(root, all_conflicts)

    # Stitch every instance's ROLE.md into the single root AGENTS.md.
    compose_agents_md(root, instances, project_name=manifest.name)

    # Persist the registry so allmight list/status can find them again.
    write_registry(root, [
        RegistryEntry(template=i.template.name, instance=i.name, version=i.template.version)
        for i in instances
    ])

    # Persist onboarding answers for the agent-side /onboard skill.
    captured["personalities"] = [
        {"template": i.template.name, "instance": i.name}
        for i in instances
    ]
    captured.setdefault("onboarded", False)
    _write_onboard_yaml(onboard_path, captured)

    writable = bool(template_options.get("writable"))
    mode_label = "writable" if writable else "read-only"

    if is_reinit:
        tpl_dir = root / ".allmight" / "templates"
        file_count = sum(1 for _ in tpl_dir.rglob("*") if _.is_file()) if tpl_dir.exists() else 0
        click.echo(f"All-Might! Project '{manifest.name}' — new templates staged.")
        click.echo(f"  Templates:  .allmight/templates/ ({file_count} files)")
        if all_conflicts:
            click.echo(f"  Conflicts:  {len(all_conflicts)} (.opencode/ entries you authored)")
        click.echo("")
        click.echo("  Run /sync in your agent to merge with your customizations.")
        click.echo("  Or run 'allmight init --force' to overwrite everything.")
    else:
        click.echo(f"All-Might! Project '{manifest.name}' initialized ({mode_label}).")
        click.echo(f"  Languages:    {', '.join(manifest.languages) or 'none detected'}")
        click.echo(f"  Corpora:      {len(manifest.indices)}")
        click.echo(f"  Personalities: {', '.join(i.name for i in instances)}")
        if all_conflicts:
            click.echo("")
            click.echo(
                f"  Heads up: {len(all_conflicts)} .opencode/ entries already exist "
                "and were not touched."
            )
            for c in all_conflicts:
                click.echo(f"    - {c.dst.relative_to(root)} ({c.existing})")
            click.echo(
                "  Manifest staged at .allmight/templates/conflicts.yaml — "
                "run /sync to resolve."
            )
        click.echo("")
        click.echo("What's next:")
        click.echo("  1. Open this folder in Claude Code or OpenCode")
        click.echo("  2. Run /onboard to finish setup (role descriptions, folder classification)")
        if writable:
            click.echo("  3. Run /ingest to build the search index")
            click.echo("  4. Run /search \"<query>\" to explore your codebase")
            click.echo("  5. Run /enrich to annotate symbols as you learn")
        else:
            click.echo("  3. Run /search \"<query>\" to explore the codebase")
        click.echo("")
        click.echo("All-Might skills auto-load — just start asking questions.")


def _collect_onboard_answers(
    templates,
    manifest,
    *,
    interactive: bool,
) -> dict:
    """Gather instance names + folders.

    Always returns the same dict shape — uses defaults under
    ``--yes`` / non-TTY, prompts otherwise.
    """
    import sys

    from .core.personalities import slugify_instance_name

    is_tty = sys.stdin.isatty() and sys.stdout.isatty()
    do_prompt = interactive and is_tty

    personalities = []
    for template in templates:
        default_name = template.default_instance_name or f"{manifest.name}-{template.short_name}"
        if do_prompt:
            raw = click.prompt(
                f"  Name for the {template.short_name} personality",
                default=default_name,
                show_default=True,
            )
            slug = slugify_instance_name(raw) or default_name
            if slug != raw:
                click.echo(f"    → using slug: {slug}")
        else:
            slug = default_name
        personalities.append({"template": template.name, "instance": slug})

    folders: list[dict] = []
    if do_prompt:
        raw_folders = click.prompt(
            "  Folders to register (comma-separated; empty to skip)",
            default="",
            show_default=False,
        ).strip()
        if raw_folders:
            for chunk in raw_folders.split(","):
                p = chunk.strip()
                if p:
                    folders.append({"path": p})

    return {
        "onboarded": False,
        "personalities": personalities,
        "folders": folders,
    }


def _read_onboard_yaml(path) -> dict | None:
    """Return the captured onboarding state, or ``None`` if absent."""
    import yaml

    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (yaml.YAMLError, OSError):
        return None
    data.setdefault("onboarded", False)
    data.setdefault("personalities", [])
    data.setdefault("folders", [])
    return data


def _write_onboard_yaml(path, data: dict) -> None:
    """Persist onboarding state for the agent-side /onboard skill."""
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


main.add_command(_build_init_command())


# ------------------------------------------------------------------
# Add / List (personality lifecycle)
# ------------------------------------------------------------------

@main.command("add")
@click.argument("name")
@click.option(
    "--capabilities",
    "capabilities_str",
    default=None,
    help=(
        "Comma-separated capability names (e.g. database,memory). "
        "Default: every discovered capability."
    ),
)
@click.option("--force", is_flag=True, help="Overwrite an existing personality.")
def add(name: str, capabilities_str: str | None, force: bool) -> None:
    """Add a personality with one or more capabilities.

    Operates on the current directory; the directory must already be
    an All-Might project (run ``allmight init`` first). Creates
    ``personalities/<name>/`` with the requested capability data dirs,
    runs each capability's install hook, projects any
    personality-specific entries into ``.opencode/`` via ``compose``,
    and appends to ``.allmight/personalities.yaml``.
    """
    from pathlib import Path as P

    from .core.personalities import (
        InstallContext,
        Personality,
        RegistryEntry,
        compose,
        compose_agents_md,
        discover,
        read_registry,
        slugify_instance_name,
        stage_compose_conflicts,
        write_registry,
    )
    from .capabilities.database.scanner import ProjectScanner

    root = P(".").resolve()
    if not (root / ".allmight").is_dir():
        click.echo(
            f"error: {root} is not an All-Might project (no .allmight/ found). "
            "Run 'allmight init' first.",
            err=True,
        )
        raise SystemExit(1)

    name = slugify_instance_name(name)
    instance_root = root / "personalities" / name

    existing_entries = read_registry(root)
    existing_names = {e.instance for e in existing_entries}
    if (instance_root.exists() or name in existing_names) and not force:
        click.echo(
            f"error: personality '{name}' already exists. Pass --force to overwrite.",
            err=True,
        )
        raise SystemExit(1)

    all_templates = discover()
    template_by_name = {t.name: t for t in all_templates}

    if capabilities_str is None:
        wanted = [t.name for t in all_templates]
    else:
        wanted = [c.strip() for c in capabilities_str.split(",") if c.strip()]

    unknown = [c for c in wanted if c not in template_by_name]
    if unknown:
        click.echo(
            f"error: unknown capability/capabilities: {', '.join(unknown)}. "
            f"Available: {', '.join(sorted(template_by_name))}.",
            err=True,
        )
        raise SystemExit(1)

    selected = [template_by_name[c] for c in wanted]
    if not selected:
        click.echo("error: --capabilities must list at least one capability.", err=True)
        raise SystemExit(1)

    scanner = ProjectScanner()
    manifest = scanner.scan(root)

    ctx = InstallContext(
        project_root=root,
        manifest=manifest,
        staging=False,
        force=force,
    )
    instance = Personality(
        template=selected[0],
        project_root=root,
        name=name,
        options={},
        capabilities=[t.name for t in selected],
    )
    for tpl in selected:
        tpl.install(ctx, instance)

    conflicts = compose(root, instance, force=force)
    stage_compose_conflicts(root, conflicts)

    new_entries = [e for e in existing_entries if e.instance != name]
    new_entries.append(RegistryEntry(
        instance=name,
        capabilities=[t.name for t in selected],
        versions={t.name: t.version for t in selected},
    ))
    write_registry(root, new_entries)

    # Recompose root AGENTS.md so the new personality's ROLE.md shows up.
    instances: list[Personality] = []
    for entry in new_entries:
        primary = template_by_name.get(
            entry.capabilities[0] if entry.capabilities else entry.template
        )
        if primary is None:
            continue
        instances.append(Personality(
            template=primary,
            project_root=root,
            name=entry.instance,
            capabilities=list(entry.capabilities),
        ))
    compose_agents_md(root, instances, project_name=manifest.name)

    click.echo(
        f"All-Might! Added personality '{name}' "
        f"(capabilities: {', '.join(t.name for t in selected)})."
    )
    if conflicts:
        click.echo(f"  Conflicts: {len(conflicts)} — run /sync to resolve.")


@main.command("list")
def list_personalities() -> None:
    """List installed personalities in the current All-Might project."""
    from pathlib import Path as P

    from .core.personalities import read_registry

    root = P(".").resolve()
    if not (root / ".allmight").is_dir():
        click.echo(
            f"error: {root} is not an All-Might project (no .allmight/ found).",
            err=True,
        )
        raise SystemExit(1)

    entries = read_registry(root)
    if not entries:
        click.echo("No personalities installed.")
        return

    name_w = max(len("Personality"), max(len(e.instance) for e in entries))
    cap_w = max(
        len("Capabilities"),
        max(len(", ".join(e.capabilities) or e.template) for e in entries),
    )
    click.echo(f"{'Personality':<{name_w}}  {'Capabilities':<{cap_w}}  {'Version'}")
    click.echo(f"{'-' * name_w}  {'-' * cap_w}  {'-' * 7}")
    for e in entries:
        caps = ", ".join(e.capabilities) if e.capabilities else e.template
        version = (
            e.versions.get(e.capabilities[0]) if e.capabilities and e.versions
            else e.version
        )
        click.echo(f"{e.instance:<{name_w}}  {caps:<{cap_w}}  {version}")


# ------------------------------------------------------------------
# Clone
# ------------------------------------------------------------------

@main.command()
@click.argument("source", type=click.Path(exists=True))
@click.argument("path", default=".", type=click.Path())
def clone(source: str, path: str):
    """Clone an existing All-Might project (read-only).

    Creates a read-only clone where database/ workspaces are
    symlinks to the source project. Memory is fresh (new L1/L2/L3).

    The clone can search the source's corpora but cannot ingest or
    enrich. File-system permissions control write access.
    """
    from pathlib import Path as P

    from .clone.cloner import ProjectCloner

    source_path = P(source).resolve()
    target_path = P(path).resolve()

    cloner = ProjectCloner()
    report = cloner.clone(source_path, target_path)

    click.echo(f"All-Might! Cloned from '{source_path.name}' (read-only).")
    if report.workspaces_linked:
        click.echo(f"  Workspaces: {', '.join(report.workspaces_linked)}")
    click.echo(f"  Memory:     L1 (MEMORY.md) + L2 (understanding/) + L3 (journal/)")
    click.echo("")
    click.echo("What's next:")
    click.echo("  1. Open this folder in Claude Code or OpenCode")
    click.echo("  2. Run /search \"<query>\" to explore the codebase")
    click.echo("")
    click.echo("All-Might skills auto-load — just start asking questions.")


# ------------------------------------------------------------------
# Migrate (one-shot upgrade for old-layout projects)
# ------------------------------------------------------------------

@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True,
              help="Print the migration plan without modifying disk.")
def migrate(path: str, dry_run: bool):
    """Migrate an All-Might project to the post-Part-C layout.

    Detects the legacy shape (``<project>-corpus``/``-memory`` instance
    dirs, ``/reflect`` command, single-file AGENTS.md with marker
    fences) and rewrites it in place. Idempotent on already-migrated
    projects.
    """
    from pathlib import Path as P

    from .migrate.migrator import migrate as run_migrate

    root = P(path).resolve()
    plan = run_migrate(root, dry_run=dry_run)

    prefix = "[DRY RUN] " if dry_run else ""
    if not plan.needs_migration:
        click.echo(f"{prefix}Nothing to migrate — '{root.name}' already on the new layout.")
        return

    click.echo(f"{prefix}Migration plan for '{root.name}':")
    if plan.rename:
        click.echo("  Rename instance dirs:")
        for old, new in plan.rename.items():
            click.echo(f"    personalities/{old}/ -> personalities/{new}/")
    if plan.dropped_files:
        click.echo("  Drop legacy files:")
        for entry in plan.dropped_files:
            click.echo(f"    {entry}")
    if plan.written_role_files:
        click.echo("  Wrote ROLE.md:")
        for entry in plan.written_role_files:
            click.echo(f"    {entry}")
    if plan.notes:
        click.echo("  Notes:")
        for note in plan.notes:
            click.echo(f"    - {note}")

    if dry_run:
        click.echo("")
        click.echo("Re-run without --dry-run to apply.")


# ------------------------------------------------------------------
# Agent Memory System
# ------------------------------------------------------------------

@main.group()
def memory():
    """Agent memory system — L1/L2/L3 persistent memory."""


@memory.command("init")
@click.argument("path", default=".", type=click.Path(exists=True))
def memory_init(path: str):
    """Add agent memory to an existing project.

    Creates MEMORY.md (L1), memory/understanding/ (L2), memory/journal/ (L3),
    and generates /remember, /recall commands.
    """
    from pathlib import Path as P

    from .capabilities.memory.initializer import MemoryInitializer

    root = P(path).resolve()

    initializer = MemoryInitializer()
    initializer.initialize(root)

    click.echo("Agent Memory System initialized.")
    click.echo("  L1 cache:        MEMORY.md")
    click.echo("  L2 understanding: memory/understanding/")
    click.echo("  L3 journal:      memory/journal/")


@memory.command("export")
@click.option("--format", "fmt", type=click.Choice(["jsonl"]), default="jsonl",
              help="Export format (only jsonl is supported today).")
@click.option("--root", default=".", type=click.Path(exists=True),
              help="Project root (defaults to the current directory).")
@click.option("--out", "out", required=True, type=click.Path(),
              help="Destination file for the export.")
def memory_export(fmt: str, root: str, out: str):
    """Export structured journal entries for offline analysis.

    Only entries carrying the ``allmight_journal: v1`` frontmatter
    sentinel are exported. Legacy freeform entries are skipped and
    counted in the summary.
    """
    from pathlib import Path as P

    from .capabilities.memory.trajectory_export import export_to_jsonl

    root_path = P(root).resolve()
    out_path = P(out).resolve()
    journal_dir = root_path / "memory" / "journal"

    skipped = export_to_jsonl(journal_dir, out_path)

    click.echo(f"Exported {fmt} to {out_path}")
    if skipped:
        click.echo(f"  Skipped {skipped} legacy/unparseable entries.")
