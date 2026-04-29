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

@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--sos", is_flag=True, help="Enable SOS/EDA environment support")
@click.option("--force", is_flag=True, help="Overwrite all files (ignore user customizations)")
@click.option("--writable", is_flag=True, help="Full access mode: enable ingest, enrich, annotation")
def init(path: str, sos: bool, force: bool, writable: bool):
    """Bootstrap a workspace with commands and agent memory.

    Scans the project, creates knowledge_graph/, injects
    .claude/commands, and initializes the L1/L2/L3 memory system.

    Default mode is read-only (search only). Use --writable for full
    access (ingest, enrich, annotate).

    On re-run (when .allmight/ exists), templates are staged to
    .allmight/templates/ instead of overwriting. Use --force to overwrite.
    """
    from pathlib import Path as P

    from .personalities.corpus_keeper.initializer import ProjectInitializer
    from .personalities.corpus_keeper.scanner import ProjectScanner
    from .memory.initializer import MemoryInitializer

    root = P(path).resolve()
    scanner = ProjectScanner()
    manifest = scanner.scan(root)

    if sos:
        manifest.has_path_env = True

    allmight_dir = root / ".allmight"
    is_reinit = allmight_dir.is_dir() and not force

    initializer = ProjectInitializer()
    initializer.initialize(manifest, force=force, writable=writable)

    MemoryInitializer().initialize(root, staging=is_reinit)

    mode_label = "writable" if writable else "read-only"

    if is_reinit:
        # Count staged files
        tpl_dir = root / ".allmight" / "templates"
        file_count = sum(1 for _ in tpl_dir.rglob("*") if _.is_file()) if tpl_dir.exists() else 0
        click.echo(f"All-Might! Project '{manifest.name}' — new templates staged.")
        click.echo(f"  Templates:  .allmight/templates/ ({file_count} files)")
        click.echo("")
        click.echo("  Run /sync in your agent to merge with your customizations.")
        click.echo("  Or run 'allmight init --force' to overwrite everything.")
    else:
        click.echo(f"All-Might! Project '{manifest.name}' initialized ({mode_label}).")
        click.echo(f"  Languages: {', '.join(manifest.languages) or 'none detected'}")
        click.echo(f"  Corpora:   {len(manifest.indices)}")
        click.echo(f"  Memory:    L1 (MEMORY.md) + L2 (understanding/) + L3 (journal/)")
        click.echo("")
        click.echo("What's next:")
        click.echo("  1. Open this folder in Claude Code or OpenCode")
        if writable:
            click.echo("  2. Run /ingest to build the search index")
            click.echo("  3. Run /search \"<query>\" to explore your codebase")
            click.echo("  4. Run /enrich to annotate symbols as you learn")
        else:
            click.echo("  2. Run /search \"<query>\" to explore the codebase")
        click.echo("")
        click.echo("All-Might skills auto-load — just start asking questions.")


# ------------------------------------------------------------------
# Clone
# ------------------------------------------------------------------

@main.command()
@click.argument("source", type=click.Path(exists=True))
@click.argument("path", default=".", type=click.Path())
def clone(source: str, path: str):
    """Clone an existing All-Might project (read-only).

    Creates a read-only clone where knowledge_graph/ workspaces are
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
# Merge
# ------------------------------------------------------------------

@main.command()
@click.argument("source", type=click.Path(exists=True))
@click.option("--workspace", "-w", multiple=True, help="Only merge specific workspaces")
@click.option("--dry-run", is_flag=True, help="Show what would be merged without copying")
@click.option("--no-memory", is_flag=True, help="Skip memory merge")
def merge(source: str, workspace: tuple[str, ...], dry_run: bool, no_memory: bool):
    """Merge knowledge bases from another All-Might project.

    Copies workspaces and memory from SOURCE into the current project.
    Conflicts are staged for agent-driven resolution via /sync.
    """
    from pathlib import Path as P

    from .merge.merger import ProjectMerger

    source_path = P(source).resolve()
    target_path = P(".").resolve()

    merger = ProjectMerger()
    ws_filter = list(workspace) if workspace else None

    report = merger.merge(
        source=source_path,
        target=target_path,
        workspaces=ws_filter,
        dry_run=dry_run,
        no_memory=no_memory,
    )

    prefix = "[DRY RUN] " if dry_run else ""
    click.echo(f"{prefix}All-Might merge complete.")

    if report.workspaces_added:
        click.echo(f"  Workspaces added:      {', '.join(report.workspaces_added)}")
    if report.workspaces_conflicting:
        click.echo(f"  Workspaces conflicting: {', '.join(report.workspaces_conflicting)}")
    if report.memory_files_added:
        click.echo(f"  Memory files added:    {len(report.memory_files_added)}")
    if report.memory_conflicts:
        click.echo(f"  Memory conflicts:      {len(report.memory_conflicts)}")
    if report.warnings:
        click.echo(f"  Path warnings:         {len(report.warnings)}")

    if report.action_needed:
        click.echo("")
        for action in report.action_needed:
            click.echo(f"  → {action}")


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

    from .memory.initializer import MemoryInitializer

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

    from .memory.trajectory_export import export_to_jsonl

    root_path = P(root).resolve()
    out_path = P(out).resolve()
    journal_dir = root_path / "memory" / "journal"

    skipped = export_to_jsonl(journal_dir, out_path)

    click.echo(f"Exported {fmt} to {out_path}")
    if skipped:
        click.echo(f"  Skipped {skipped} legacy/unparseable entries.")
