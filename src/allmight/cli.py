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
    hardcoded ``--sos`` knob — ``cli.py`` does not interpret it, it
    just forwards every flag as a raw dict into every
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
    """Run the scaffold-only init flow.

    ``template_options`` is the raw dict of every CliOption value. Each
    template's ``install_globals`` reads what it cares about; the CLI
    never interprets the contents.

    No personality is created at install time — ``allmight init`` writes
    the project-wide ``.opencode/`` globals, ``AGENTS.md``,
    ``MEMORY.md``, an empty registry, and a personality suggestion
    catalog at ``.allmight/suggestions/personalities/``. The
    agent-side ``/onboard`` skill then proposes from the catalog and
    shells out to ``allmight add`` for whatever the user picks.
    """
    from pathlib import Path as P

    from .core.personalities import (
        InstallContext,
        Personality,
        compose_agents_md,
        compose_role_agents,
        discover,
        read_registry,
        write_init_scaffold,
        write_registry,
    )
    from .core.state import read_onboard, write_onboard
    from .capabilities.database.scanner import ProjectScanner
    from .capabilities.database.personality_suggestions import seed_suggestions

    root = P(path).resolve()
    scanner = ProjectScanner()
    manifest = scanner.scan(root)

    allmight_dir = root / ".allmight"
    is_reinit = allmight_dir.is_dir() and not force

    templates = discover()

    # Captured onboard.yaml is preserved across re-init so /onboard
    # state survives. On first init we just seed the empty shape —
    # /onboard fills personalities[] later when the user picks.
    captured = read_onboard(root) or {
        "onboarded": False,
        "personalities": [],
        "folders": [],
    }

    write_init_scaffold(root)

    ctx = InstallContext(
        project_root=root,
        manifest=manifest,
        staging=is_reinit,
        force=force,
        options=dict(template_options),
    )
    for template in templates:
        if template.install_globals is not None:
            template.install_globals(ctx)

    # Re-init on a populated project must NOT lose the existing
    # personality registry — preserve it and recompose AGENTS.md +
    # the .opencode/agents/<name>.md subagent files from the existing
    # rows so per-role sections survive the update.
    #
    # Fresh init (no .allmight/) and `--force` still wipe to empty:
    # `--force` is the documented "overwrite everything" escape hatch.
    existing = read_registry(root) if is_reinit else []
    if existing:
        template_by_name = {t.name: t for t in templates}
        instances: list[Personality] = []
        for entry in existing:
            primary_name = (
                entry.capabilities[0] if entry.capabilities else entry.template
            )
            primary = template_by_name.get(primary_name)
            if primary is None:
                continue
            instances.append(Personality(
                template=primary,
                project_root=root,
                name=entry.instance,
                capabilities=list(entry.capabilities),
            ))
        compose_agents_md(root, instances, project_name=manifest.name)
        compose_role_agents(root, instances)
        # Registry on disk is already correct; no rewrite needed.
    else:
        # Fresh init (or --force): empty AGENTS.md + empty registry.
        # /onboard + allmight add populate them once personalities exist.
        compose_agents_md(root, [], project_name=manifest.name)
        write_registry(root, [])

    # Persist the (possibly preserved) onboard state.
    captured.setdefault("onboarded", False)
    captured.setdefault("personalities", [])
    captured.setdefault("folders", [])
    write_onboard(root, captured)

    # Seed the personality suggestion catalog so /onboard has a
    # deterministic list to propose from.
    seed_suggestions(root, force=force)

    if is_reinit:
        tpl_dir = root / ".allmight" / "templates"
        file_count = sum(1 for _ in tpl_dir.rglob("*") if _.is_file()) if tpl_dir.exists() else 0
        click.echo(f"All-Might! Project '{manifest.name}' — new templates staged.")
        click.echo(f"  Templates:  .allmight/templates/ ({file_count} files)")
        if existing:
            click.echo(
                f"  Preserved:  {len(existing)} personality "
                f"row(s) in .allmight/personalities.yaml; "
                f"AGENTS.md + .opencode/agents/ refreshed."
            )
        click.echo("")
        click.echo("  Run /sync in your agent to merge with your customizations.")
        click.echo("  Or run 'allmight init --force' to overwrite everything.")
    else:
        click.echo(f"All-Might! Project '{manifest.name}' initialized.")
        click.echo(f"  Languages:  {', '.join(manifest.languages) or 'none detected'}")
        click.echo("")
        click.echo("What's next:")
        click.echo("  Run /onboard in your agent to set up your first personality,")
        click.echo("  or just start asking questions.")


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
    from .core.personalities import compose_role_agents
    compose_role_agents(root, instances)

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
# Reconcile (orphan personality registration)
# ------------------------------------------------------------------


@main.command("reconcile")
@click.option(
    "--yes",
    "apply",
    is_flag=True,
    help="Apply registration. Without this flag the command is a dry run.",
)
def reconcile(apply: bool) -> None:
    """Register personality dirs that exist on disk but aren't in the registry.

    Scans ``personalities/*/`` for directories that aren't listed in
    ``.allmight/personalities.yaml``. For each, capabilities are
    detected from the presence of a matching subdirectory (e.g.
    ``personalities/foo/database/`` implies the ``database``
    capability).

    Dry run by default: prints what would be registered and exits
    without touching the registry. Pass ``--yes`` to apply, which
    writes the registry and recomposes ``AGENTS.md`` plus the
    per-personality OpenCode agent files so the new entries show up
    in agent-visible surfaces.

    Orphans without a ``ROLE.md`` or without any detected capability
    are reported but skipped on apply — they aren't well-formed
    personalities.
    """
    from pathlib import Path as P

    from .capabilities.database.scanner import ProjectScanner
    from .core.personalities import (
        Personality,
        compose_agents_md,
        compose_role_agents,
        detect_orphan_personalities,
        discover,
        register_orphans,
    )

    root = P(".").resolve()
    if not (root / ".allmight").is_dir():
        click.echo(
            f"error: {root} is not an All-Might project (no .allmight/ found). "
            "Run 'allmight init' first.",
            err=True,
        )
        raise SystemExit(1)

    orphans = detect_orphan_personalities(root)
    if not orphans:
        click.echo("No orphan personalities found — registry is in sync with disk.")
        return

    actionable = [o for o in orphans if o.has_role_md and o.capabilities]
    click.echo(f"Found {len(orphans)} unregistered personality directory(ies):")
    for o in orphans:
        caps = ", ".join(o.capabilities) if o.capabilities else "(none detected)"
        if not o.has_role_md:
            tail = "  [skip: missing ROLE.md]"
        elif not o.capabilities:
            tail = "  [skip: no capability subdirs]"
        else:
            tail = ""
        click.echo(f"  - {o.name}  capabilities: {caps}{tail}")

    if not actionable:
        click.echo(
            "\nNothing actionable — every orphan is missing ROLE.md or a "
            "capability subdir."
        )
        return

    if not apply:
        click.echo(
            f"\nDry run: pass --yes to register the {len(actionable)} "
            f"actionable personality(ies)."
        )
        return

    new_entries = register_orphans(root, actionable)

    template_by_name = {t.name: t for t in discover()}
    scanner = ProjectScanner()
    manifest = scanner.scan(root)
    instances: list[Personality] = []
    for entry in new_entries:
        primary_name = (
            entry.capabilities[0] if entry.capabilities else entry.template
        )
        primary = template_by_name.get(primary_name)
        if primary is None:
            continue
        instances.append(Personality(
            template=primary,
            project_root=root,
            name=entry.instance,
            capabilities=list(entry.capabilities),
        ))
    compose_agents_md(root, instances, project_name=manifest.name)
    compose_role_agents(root, instances)

    names = ", ".join(o.name for o in actionable)
    click.echo(
        f"\nAll-Might! Registered {len(actionable)} personality(ies): {names}. "
        "AGENTS.md and OpenCode agent files refreshed."
    )


# ------------------------------------------------------------------
# Bundle import (internal helper for `share pull`).
#
# The standalone ``allmight import`` CLI was removed (Track C — it
# was the mechanical CI/scripting path; the agent-driven
# ``/all-for-one`` skill covers cross-project transfer). The body
# stays here as a private helper because ``share pull`` clones a git
# remote into a temp dir then runs the same install + lineage
# bookkeeping. Callers pass the project root and bundle path
# explicitly; this used to be derived from ``cwd`` via Click.
# ------------------------------------------------------------------


def _import_bundle(
    project_root: "Path",
    bundle: str,
    as_name: str | None = None,
) -> None:
    """Install a single personality bundle into ``project_root``.

    Same semantics as the (removed) ``allmight import`` CLI: refuses
    on collision and points the user at ``/all-for-one``. Used by
    ``share pull`` after the git clone lands a bundle in a temp dir.
    """
    from pathlib import Path as P
    import shutil

    import yaml as _yaml

    from .core.personalities import (
        DerivedFrom,
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

    if not (project_root / ".allmight").is_dir():
        click.echo(
            f"error: {project_root} is not an All-Might project (no .allmight/ found). "
            "Run 'allmight init' first.",
            err=True,
        )
        raise SystemExit(1)

    bundle_path = P(bundle).resolve()
    manifest_path = bundle_path / "manifest.yaml"
    if not manifest_path.is_file():
        click.echo(
            f"error: bundle {bundle_path} has no manifest.yaml — not an "
            "allmight personality export.",
            err=True,
        )
        raise SystemExit(1)

    try:
        manifest_data = _yaml.safe_load(manifest_path.read_text()) or {}
    except _yaml.YAMLError as exc:
        click.echo(f"error: malformed manifest.yaml: {exc}", err=True)
        raise SystemExit(1)

    bundle_name = manifest_data.get("personality_name")
    if not bundle_name:
        click.echo("error: manifest.yaml is missing personality_name.", err=True)
        raise SystemExit(1)
    bundle_caps = list((manifest_data.get("capabilities") or {}).keys())
    if not bundle_caps:
        click.echo("error: manifest.yaml lists no capabilities.", err=True)
        raise SystemExit(1)

    # Parse database_subscriptions (optional, schema v2+).
    # Warn when an entry's nfs_path is missing on the receiver's box.
    # Never block the import — receivers often install bundles before
    # mounting team NFS, and they need to be able to fix paths after.
    subscriptions = manifest_data.get("database_subscriptions") or []
    if not isinstance(subscriptions, list):
        click.echo(
            "warning: manifest.yaml database_subscriptions is not a list, "
            "ignoring.",
            err=True,
        )
        subscriptions = []
    sub_warnings = 0
    for sub in subscriptions:
        if not isinstance(sub, dict):
            continue
        nfs_path = sub.get("nfs_path")
        index = sub.get("index", "<unnamed>")
        required = bool(sub.get("required", True))
        if not nfs_path:
            continue
        if not P(str(nfs_path)).exists():
            sub_warnings += 1
            level = "warning" if required else "note"
            click.echo(
                f"{level}: database subscription '{index}' references "
                f"missing path '{nfs_path}'. The personality will import, "
                "but you must mount the shared SMAK or update its "
                "database/config.yaml before /search will work.",
                err=True,
            )

    target_name = slugify_instance_name(as_name or bundle_name)
    target_root = project_root / "personalities" / target_name
    existing_entries = read_registry(project_root)
    existing_names = {e.instance for e in existing_entries}
    if target_root.exists() or target_name in existing_names:
        click.echo(
            f"error: personality '{target_name}' already exists. "
            "To merge this bundle into it (or combine with other "
            "sources), run /all-for-one in the agent — that skill "
            "handles per-file conflicts and ROLE.md prose "
            "reconciliation. To install under a different fresh "
            "name, retry with '--as <new-name>'.",
            err=True,
        )
        raise SystemExit(1)

    all_templates = discover()
    template_by_name = {t.name: t for t in all_templates}
    unknown = [c for c in bundle_caps if c not in template_by_name]
    if unknown:
        click.echo(
            f"error: bundle requires unknown capability/capabilities: "
            f"{', '.join(unknown)}. "
            f"Available: {', '.join(sorted(template_by_name))}.",
            err=True,
        )
        raise SystemExit(1)

    selected = [template_by_name[c] for c in bundle_caps]

    scanner = ProjectScanner()
    project_manifest = scanner.scan(project_root)

    ctx = InstallContext(
        project_root=project_root,
        manifest=project_manifest,
        staging=False,
        force=False,
    )
    instance = Personality(
        template=selected[0],
        project_root=project_root,
        name=target_name,
        options={},
        capabilities=[t.name for t in selected],
    )
    for tpl in selected:
        tpl.install(ctx, instance)

    # Copy bundle data into the freshly-installed personality dir.
    # ``store/`` subdirs are intentionally absent from bundles; we
    # don't fabricate them here.
    if (bundle_path / "ROLE.md").is_file():
        shutil.copy2(bundle_path / "ROLE.md", target_root / "ROLE.md")
    for cap in bundle_caps:
        bundle_cap_dir = bundle_path / cap
        if not bundle_cap_dir.is_dir():
            continue
        target_cap_dir = target_root / cap
        target_cap_dir.mkdir(parents=True, exist_ok=True)
        for src in bundle_cap_dir.rglob("*"):
            if src.is_dir():
                continue
            rel = src.relative_to(bundle_cap_dir)
            dst = target_cap_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    conflicts = compose(project_root, instance, force=False)
    stage_compose_conflicts(project_root, conflicts)

    # Lineage: capture bundle_id / bundle_version from manifest into a
    # single-entry derived_from list. Empty when the bundle predates
    # the lineage schema; in that case we still record an empty
    # ``derived_from`` so re-export by ``/one-for-all`` produces a
    # well-formed manifest.
    bundle_id = str(manifest_data.get("bundle_id") or "")
    bundle_version = str(manifest_data.get("bundle_version") or "")
    from datetime import datetime, timezone as _tz
    derived_at_iso = (
        datetime.now(tz=_tz.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    derived_from: list[DerivedFrom] = []
    if bundle_id:
        derived_from.append(DerivedFrom(
            kind="bundle",
            bundle_id=bundle_id,
            bundle_version=bundle_version,
        ))

    new_entries = [e for e in existing_entries if e.instance != target_name]
    new_entries.append(RegistryEntry(
        instance=target_name,
        capabilities=[t.name for t in selected],
        versions={t.name: t.version for t in selected},
        derived_from=derived_from,
        derived_at=(derived_at_iso if derived_from else ""),
    ))
    write_registry(project_root, new_entries)

    instances: list[Personality] = []
    for entry in new_entries:
        primary = template_by_name.get(
            entry.capabilities[0] if entry.capabilities else entry.template
        )
        if primary is None:
            continue
        instances.append(Personality(
            template=primary,
            project_root=project_root,
            name=entry.instance,
            capabilities=list(entry.capabilities),
        ))
    compose_agents_md(project_root, instances, project_name=project_manifest.name)
    from .core.personalities import compose_role_agents
    compose_role_agents(project_root, instances)

    click.echo(
        f"All-Might! Imported personality '{target_name}' "
        f"(capabilities: {', '.join(t.name for t in selected)})."
    )
    if subscriptions:
        click.echo(
            f"  Database subscriptions: {len(subscriptions)} "
            f"({sub_warnings} warning(s))."
        )
    click.echo(
        "  Next: rebuild the SMAK index out-of-band (smak ingest) for the "
        "imported database workspaces."
    )


# ------------------------------------------------------------------
# Share (publish + pull personality bundles via git transport)
# ------------------------------------------------------------------


@main.group("share")
def share() -> None:
    """Publish and pull personality bundles through a git remote.

    Mode-1 team-share transport: bundles travel through any git URL
    All-Might can reach via the local git CLI (NFS-hosted bare repo,
    internal Gerrit/Gitea, etc). Authentication is the user's
    environment's responsibility.

    Pre-built bundles come from ``/one-for-all``. The CLI is purely
    a transport layer — it never edits memory or runs PII review.
    """


@share.command("publish")
@click.argument("bundle_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--to", "git_url", required=True,
              help="Git URL to push the bundle to (file://, ssh, https).")
@click.option("--message", default=None,
              help="Commit message. Defaults to 'publish bundle <id>'.")
@click.option("--branch", default="main",
              help="Branch to push to (default: main).")
def share_publish(
    bundle_dir: str, git_url: str,
    message: str | None, branch: str,
) -> None:
    """Push a pre-built bundle directory to a git remote.

    Workflow:
      1. Run /one-for-all inside Claude Code / OpenCode to produce
         a reviewed bundle directory.
      2. allmight share publish <bundle-dir> --to <git-url>

    The bundle dir must contain manifest.yaml. For first-time
    publishes to a local file:// URL, the target bare repo is
    initialised automatically.
    """
    from datetime import datetime, timezone as _tz
    from pathlib import Path as P

    from .share.git_share import (
        GitShareError,
        UpstreamRecord,
        publish_bundle,
        read_upstream,
        write_upstream,
    )

    project_root = P(".").resolve()
    if not (project_root / ".allmight").is_dir():
        click.echo(
            f"error: {project_root} is not an All-Might project "
            "(no .allmight/). Run 'allmight init' first.",
            err=True,
        )
        raise SystemExit(1)

    bundle_path = P(bundle_dir).resolve()
    try:
        result = publish_bundle(
            bundle_path, git_url, message=message, branch=branch,
        )
    except GitShareError as exc:
        click.echo(f"error: {exc}", err=True)
        raise SystemExit(1)

    # Persist the upstream pointer keyed by personality name (read
    # from the bundle manifest).
    import yaml as _yaml
    manifest = _yaml.safe_load(
        (bundle_path / "manifest.yaml").read_text()
    ) or {}
    name = manifest.get("personality_name") or bundle_path.name
    records = read_upstream(project_root)
    rec = records.get(name) or UpstreamRecord()
    rec.upstream = git_url
    rec.last_published_bundle_id = result.bundle_id
    rec.last_published_at = (
        datetime.now(tz=_tz.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    records[name] = rec
    write_upstream(project_root, records)

    click.echo(
        f"All-Might! Published '{name}' ({result.files_pushed} files) "
        f"to {git_url} on branch {result.pushed_to_branch}."
    )
    if result.bundle_id:
        click.echo(f"  bundle_id: {result.bundle_id}")


@share.command("pull")
@click.argument("git_url")
@click.option("--as", "as_name", default=None,
              help="Install the pulled personality under this name.")
def share_pull(git_url: str, as_name: str | None) -> None:
    """Clone a bundle from a git remote and install it.

    Internally: ``git clone <url> <tmp>`` then runs the bundle-import
    helper. Persists the upstream URL in ``.allmight/upstream.yaml``.

    Collision behaviour: if the target name already exists, the pull
    fails and asks the user to either retry with ``--as <new-name>``
    or run ``/all-for-one`` in the agent to merge.
    """
    import shutil as _shutil
    import tempfile as _tempfile
    from datetime import datetime, timezone as _tz
    from pathlib import Path as P

    from .share.git_share import (
        GitShareError,
        UpstreamRecord,
        pull_to_temp,
        read_upstream,
        write_upstream,
    )

    project_root = P(".").resolve()
    if not (project_root / ".allmight").is_dir():
        click.echo(
            f"error: {project_root} is not an All-Might project "
            "(no .allmight/). Run 'allmight init' first.",
            err=True,
        )
        raise SystemExit(1)

    tmpdir = P(_tempfile.mkdtemp(prefix="allmight-pull-"))
    try:
        try:
            clone_dest = pull_to_temp(git_url, tmpdir / "bundle")
        except GitShareError as exc:
            click.echo(f"error: {exc}", err=True)
            raise SystemExit(1)

        # Reuse the bundle-import helper directly. Collision-on-target
        # is reported by the helper (and includes a /all-for-one
        # redirect message); we let SystemExit propagate so the user
        # sees the same error.
        try:
            _import_bundle(project_root, str(clone_dest), as_name)
        except SystemExit:
            raise

        # Read bundle_id from manifest for upstream record.
        import yaml as _yaml
        manifest = _yaml.safe_load(
            (clone_dest / "manifest.yaml").read_text()
        ) or {}
        name = manifest.get("personality_name") or "(unknown)"
        bundle_id = str(manifest.get("bundle_id") or "")

        records = read_upstream(project_root)
        rec = records.get(as_name or name) or UpstreamRecord()
        rec.upstream = git_url
        rec.last_pulled_bundle_id = bundle_id
        rec.last_pulled_at = (
            datetime.now(tz=_tz.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        records[as_name or name] = rec
        write_upstream(project_root, records)

        click.echo(
            f"  Recorded upstream: {git_url}"
        )
    finally:
        _shutil.rmtree(tmpdir, ignore_errors=True)


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

    The clone can search the source's corpora. The All-Might agent
    surface is search-only — there are no slash commands that mutate
    the corpus; SMAK CLI handles ingest/enrich out-of-band.
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


@memory.command("ingest")
@click.option(
    "--incremental/--full", default=True,
    help="Pass --incremental to smak (default) or --full to rebuild.",
)
@click.option(
    "--root", default=".", type=click.Path(exists=True),
    help="Project root (defaults to the current directory).",
)
def memory_ingest(incremental: bool, root: str):
    """Index every personality's journal into the SMAK store.

    Walks ``personalities/*/memory/smak_config.yaml`` and runs
    ``smak ingest --config <cfg>`` for each. On overall success,
    touches ``.allmight/last_ingest`` and removes
    ``.allmight/ingest.pending`` so the next Stop hook treats the
    journal as indexed.

    Spawned fire-and-forget by the memory-load drain when
    ``.allmight/ingest.pending`` exists. Safe to invoke directly
    too — incremental mode is cheap when nothing has changed.
    """
    import os as _os
    from pathlib import Path as _Path

    from .capabilities.memory.ingest import run_ingest_cycle

    root_path = _Path(root).resolve()
    smak_cmd = _os.environ.get("ALLMIGHT_SMAK_CMD", "smak")
    result = run_ingest_cycle(
        root_path, incremental=incremental, smak_cmd=smak_cmd,
    )

    if result.errors:
        click.echo("smak ingest failures:", err=True)
        for personality_dir, err in result.errors:
            click.echo(f"  {personality_dir.name}: {err}", err=True)
        raise click.exceptions.Exit(code=1)

    if not result.succeeded:
        click.echo("No personalities with memory capability found.")
        return
    click.echo(f"Ingested {len(result.succeeded)} personality(ies):")
    for personality_dir in result.succeeded:
        click.echo(f"  {personality_dir.name}")


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


# ------------------------------------------------------------------
# Agent Memory: version-control mirror (recovery from accidental edits)
# ------------------------------------------------------------------

def _memory_history():
    from .capabilities.memory.history import MemoryHistory
    return MemoryHistory()


@memory.command("snapshot")
@click.option("--message", "-m", default=None,
              help="Commit message. Defaults to 'manual: <change summary>'.")
@click.option("--trigger", default="manual",
              help="Trigger label recorded in the commit message "
                   "(used by plugins / hooks to mark auto-snapshots).")
@click.option("--session-id", "session_id", default="",
              help="Session id recorded in the commit body.")
def memory_snapshot(
    message: str | None, trigger: str, session_id: str,
) -> None:
    """Sync live memory data into the recovery mirror and commit.

    Run automatically by the OpenCode plugin / Claude Code hook after
    each turn. Safe to run by hand at any time. No-op if nothing
    changed since the last snapshot.
    """
    from pathlib import Path as P

    project_root = P(".").resolve()
    history = _memory_history()
    if message is None:
        sha = history.snapshot(
            project_root, trigger=trigger, session_id=session_id,
        )
    else:
        history.sync(project_root)
        sha = history.commit(project_root, message)
    if sha is None:
        click.echo("No changes to snapshot.")
    else:
        click.echo(f"Snapshot: {sha[:12]}")


@memory.command("log")
@click.option("--personality", default=None,
              help="Filter to commits that touched this personality's tree.")
@click.option("-n", "limit", default=20, type=int,
              help="Maximum number of commits to print (default: 20).")
def memory_log(personality: str | None, limit: int) -> None:
    """Print the memory-history commit log.

    Each line: ``<short-sha> <iso-timestamp> <subject>``.
    """
    from pathlib import Path as P

    history = _memory_history()
    records = history.log(
        P(".").resolve(),
        personality=personality, n=limit,
    )
    if not records:
        click.echo("(no commits in memory-history yet)")
        return
    for rec in records:
        click.echo(f"{rec.sha[:12]}  {rec.timestamp}  {rec.subject}")


@memory.command("diff")
@click.argument("rev")
@click.option("--file", "relpath", default=None,
              help="Restrict the diff to one file (project-relative path).")
def memory_diff(rev: str, relpath: str | None) -> None:
    """Show what changed at <rev>, optionally for a single file."""
    from pathlib import Path as P

    history = _memory_history()
    out = history.diff(P(".").resolve(), rev, relpath=relpath)
    click.echo(out)


@memory.command("restore")
@click.argument("relpath", metavar="FILE")
@click.option("--rev", default="HEAD",
              help="Mirror revision to restore from. Default: HEAD "
                   "(the most recent snapshot).")
@click.option("--to", "dest", default=None, type=click.Path(),
              help="Destination path (project-relative or absolute). "
                   "Default: overwrite the live file at <file>.")
@click.option("--yes", is_flag=True,
              help="Skip the overwrite confirmation prompt.")
def memory_restore(
    relpath: str, rev: str, dest: str | None, yes: bool,
) -> None:
    """Restore <file> from a memory-history snapshot.

    With no ``--to``, overwrites the live file. Confirms before
    overwriting unless ``--yes``.
    """
    from pathlib import Path as P

    project_root = P(".").resolve()
    target = P(dest).resolve() if dest else (project_root / relpath)
    if target.exists() and not yes:
        if not click.confirm(
            f"Overwrite {target}? This replaces the current contents."
        ):
            click.echo("Aborted.")
            raise SystemExit(1)
    history = _memory_history()
    out = history.restore(
        project_root, relpath, rev=rev, dest=target,
    )
    click.echo(f"Restored: {out}")


@memory.command("gc")
def memory_gc() -> None:
    """Run ``git gc`` inside the memory-history mirror."""
    from pathlib import Path as P

    history = _memory_history()
    out = history.gc(P(".").resolve())
    if out.strip():
        click.echo(out.strip())
    click.echo("Memory-history gc complete.")


# ------------------------------------------------------------------
# Plugin observability
# ------------------------------------------------------------------

@main.group("plugin")
def plugin() -> None:
    """Plugin observability — see what fires and what doesn't.

    See ``docs/plugin-observability.md`` for the design rationale.
    """


@plugin.command("status")
@click.argument("path", default=".", type=click.Path(exists=True))
def plugin_status(path: str) -> None:
    """Print last-fire time for every known plugin / hook.

    Reads ``.allmight/plugins/heartbeats/{oc,cc}/`` and lists each
    plugin's last-fired mtime. Plugins that have never fired show
    ``never fired`` — that is the signal to investigate.
    """
    import time
    from pathlib import Path as P

    from .core.plugin_telemetry import (
        KNOWN_OPENCODE_PLUGINS,
        PLUGIN_MANIFEST,
        SURFACE_CLAUDE,
        SURFACE_OPENCODE,
        cc_unavailable_reasons,
        read_heartbeats,
    )

    root = P(path).resolve()
    data = read_heartbeats(root)
    now = time.time()

    def _fmt_age(mtime: float | None) -> str:
        if mtime is None:
            return "never fired"
        delta = max(0, int(now - mtime))
        if delta < 60:
            return f"fired {delta}s ago"
        if delta < 3600:
            return f"fired {delta // 60}m ago"
        if delta < 86400:
            return f"fired {delta // 3600}h ago"
        return f"fired {delta // 86400}d ago"

    # ---- OpenCode plugins (all known plugins, fire-time only) ----
    click.echo("OpenCode plugins:")
    oc_entries = data.get(SURFACE_OPENCODE, {})
    oc_width = max((len(n) for n in KNOWN_OPENCODE_PLUGINS), default=12)
    for name in KNOWN_OPENCODE_PLUGINS:
        click.echo(f"  {name:<{oc_width}}  {_fmt_age(oc_entries.get(name))}")
    extras = sorted(n for n in oc_entries if n not in set(KNOWN_OPENCODE_PLUGINS))
    for name in extras:
        click.echo(f"  {name:<{oc_width}}  {_fmt_age(oc_entries.get(name))} (unregistered)")

    # ---- Claude Code hooks: manifest-derived (Capability Manifest) ----
    # OC-only plugins show "unavailable (requires: <cap>)" so users
    # can tell structural absence apart from never-fired bugs.
    click.echo()
    click.echo("Claude Code hooks:")
    cc_entries = data.get(SURFACE_CLAUDE, {})
    cc_width = max((len(n) for n in PLUGIN_MANIFEST), default=12)
    for plugin_name in KNOWN_OPENCODE_PLUGINS:
        entry = PLUGIN_MANIFEST.get(plugin_name, {})
        mirror = entry.get("claude_code_mirror")
        if mirror:
            hook_stem = mirror.removesuffix(".py")
            status = _fmt_age(cc_entries.get(hook_stem))
            click.echo(f"  {plugin_name:<{cc_width}}  {status}")
        else:
            blockers = cc_unavailable_reasons(plugin_name)
            reason = ", ".join(blockers) if blockers else "OpenCode-only"
            click.echo(f"  {plugin_name:<{cc_width}}  unavailable (requires: {reason})")


@plugin.command("matrix")
def plugin_matrix() -> None:
    """Print the plugin × platform compatibility matrix.

    Single source of truth: ``src/allmight/core/plugin_telemetry.py::
    PLUGIN_MANIFEST``. The README's matrix block must match this
    output — tests in ``test_capability_manifest.py`` enforce drift
    detection.
    """
    from .core.plugin_telemetry import format_compatibility_matrix
    click.echo(format_compatibility_matrix())
