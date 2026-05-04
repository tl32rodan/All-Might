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
    template_by_name = {t.name: t for t in templates}

    # Decide the single personality name + its capability set. If
    # onboard.yaml exists, reuse what was captured before so re-init
    # never asks the user again. Otherwise prompt (or use the
    # project-root dir name under --yes).
    onboard_path = allmight_dir / "onboard.yaml"
    captured = _read_onboard_yaml(onboard_path)
    if captured is None:
        captured = _collect_onboard_answers(templates, manifest, interactive=not yes)

    rows = captured.get("personalities", [])
    if not rows:
        raise RuntimeError("onboard.yaml has no personalities entry")
    row = rows[0]
    personality_name = row.get("name") or row.get("instance")
    wanted_caps = row.get("capabilities") or [row.get("template")]
    selected_templates = [template_by_name[c] for c in wanted_caps if c in template_by_name]

    write_init_scaffold(root)

    ctx = InstallContext(
        project_root=root,
        manifest=manifest,
        staging=is_reinit,
        force=force,
    )
    instance = Personality(
        template=selected_templates[0],
        project_root=root,
        name=personality_name,
        options=dict(template_options),
        capabilities=[t.name for t in selected_templates],
    )
    notes: list[str] = []
    for template in selected_templates:
        result = template.install(ctx, instance)
        notes.extend(result.notes)
    instances: list[Personality] = [instance]

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

    # Persist the registry so allmight list/status can find it again.
    write_registry(root, [
        RegistryEntry(
            instance=instance.name,
            capabilities=list(instance.capabilities),
            versions={t.name: t.version for t in selected_templates},
        ),
    ])

    # Persist onboarding answers for the agent-side /onboard skill.
    captured["personalities"] = [
        {"name": instance.name, "capabilities": list(instance.capabilities)},
    ]
    captured.setdefault("folders", [])
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
    """Gather the single personality name + its capabilities.

    Part-D commit 7: ``allmight init`` creates ONE personality with
    ALL discovered capabilities. The previous flow (one prompt per
    template + folder list) is gone — folder classification is
    deferred entirely to the agent-side ``/onboard`` skill.

    Always returns the same dict shape — uses the project-root dir
    name as the default under ``--yes`` / non-TTY, prompts otherwise.
    """
    import sys

    from .core.personalities import slugify_instance_name

    is_tty = sys.stdin.isatty() and sys.stdout.isatty()
    do_prompt = interactive and is_tty

    default_name = slugify_instance_name(manifest.root_path.name) or "main"

    if do_prompt:
        raw = click.prompt(
            "  Personality name",
            default=default_name,
            show_default=True,
        )
        slug = slugify_instance_name(raw) or default_name
        if slug != raw:
            click.echo(f"    → using slug: {slug}")
    else:
        slug = default_name

    return {
        "onboarded": False,
        "personalities": [
            {
                "name": slug,
                "capabilities": [t.name for t in templates],
            },
        ],
        "folders": [],
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
# Import (personality bundle restore)
# ------------------------------------------------------------------

@main.command("import")
@click.argument("bundle", type=click.Path(exists=True, file_okay=False))
@click.option("--as", "as_name", default=None,
              help="Install the bundled personality under this new name "
                   "(instead of the manifest's personality_name).")
def import_personality(bundle: str, as_name: str | None) -> None:
    """Restore a single personality bundle into the current All-Might project.

    Mechanical, single-bundle install — the thin path for CI,
    scripting, and fresh-project bootstrap. Reads ``manifest.yaml``
    from the bundle, runs each named capability's install hook (so the
    on-disk structure conforms to the receiving project's ``allmight``
    version), and copies the bundle's data into
    ``personalities/<name>/``. Vector indices (``store/``) are not in
    bundles; rebuild via ``/ingest`` afterward.

    If the target name already exists, this command fails. Anything
    requiring merge — multiple bundles, fold-into-existing,
    in-project consolidation — belongs to ``/all-for-one`` (the skill
    invoked from the agent), which can dialog through the per-file
    decisions a CLI flag cannot capture.
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

    project_root = P(".").resolve()
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

    click.echo(
        f"All-Might! Imported personality '{target_name}' "
        f"(capabilities: {', '.join(t.name for t in selected)})."
    )
    if subscriptions:
        click.echo(
            f"  Database subscriptions: {len(subscriptions)} "
            f"({sub_warnings} warning(s))."
        )
    click.echo("  Next: re-run /ingest to rebuild the search index.")


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
    """Clone a bundle from a git remote and import it.

    Equivalent to: ``git clone <url> <tmp> && allmight import <tmp>``,
    plus persisting the upstream URL in ``.allmight/upstream.yaml``.

    Inherits ``allmight import``'s collision behaviour: if the target
    name already exists, the pull fails and asks the user to either
    retry with ``--as <new-name>`` or run ``/all-for-one`` in the
    agent to merge.
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

        # Reuse the existing import command's body via Click's
        # invocation API. Collision-on-target is reported by import
        # itself (and includes a /all-for-one redirect message); we
        # let SystemExit propagate so the user sees the same error.
        ctx = click.get_current_context()
        sub = main.get_command(ctx, "import")
        assert sub is not None, "import command must be registered"
        try:
            ctx.invoke(sub, bundle=str(clone_dest), as_name=as_name)
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
