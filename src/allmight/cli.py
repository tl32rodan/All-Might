"""All-Might CLI — thin bootstrapping surface.

All-Might is an **agent harness**, not a CLI tool.  The CLI exists only for
operations that cannot be agent-driven:

    allmight init [path]                — Bootstrap a workspace
    allmight power-level [--config]     — Show knowledge graph coverage
    allmight config add-index           — Add a corpus
    allmight config remove-index        — Remove a corpus
    allmight config list-indices        — List configured indices
    allmight config update-index        — Update an existing index

Everything else (search, enrich, explain, panorama, report, generate) is
agent-driven through .claude/ skills.  See the hub's CLAUDE.md and
.claude/skills/ for the full skill architecture.
"""

from __future__ import annotations

import click

from . import __version__


@click.group()
@click.version_option(version=__version__, prog_name="allmight")
def main():
    """All-Might: Active Knowledge Graph Framework.

    Agent harness for multi-workspace knowledge graph orchestration.
    Use 'init' to bootstrap, then let the agent drive via skills.
    """


# ------------------------------------------------------------------
# Bootstrapping
# ------------------------------------------------------------------

@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--smak-path", type=click.Path(exists=True), help="Path to skill installation (for skill copying)")
@click.option("--sos", is_flag=True, help="Enable SOS/EDA environment support")
@click.option("--with-memory", is_flag=True, help="Also initialize the agent memory subsystem")
def init(path: str, smak_path: str | None, sos: bool, with_memory: bool):
    """Detroit — one punch to bootstrap the entire workspace.

    Scans the project, creates config.yaml with project metadata and
    corpora, and injects .claude/skills and commands.
    """
    from pathlib import Path as P

    from .detroit_smak.initializer import ProjectInitializer
    from .detroit_smak.scanner import ProjectScanner

    root = P(path).resolve()
    scanner = ProjectScanner()
    manifest = scanner.scan(root)

    if sos:
        manifest.has_path_env = True

    initializer = ProjectInitializer()
    smak = P(smak_path).resolve() if smak_path else None
    initializer.initialize(manifest, smak_path=smak)

    click.echo(f"Detroit! Project '{manifest.name}' initialized.")
    click.echo(f"  Languages: {', '.join(manifest.languages) or 'none detected'}")
    click.echo(f"  Corpora:   {len(manifest.indices)}")
    click.echo(f"  Config:    {root / 'config.yaml'}")

    if with_memory:
        from .memory.initializer import MemoryInitializer

        MemoryInitializer().initialize(root)
        click.echo("  Memory:    agent memory system enabled")

    click.echo("")
    click.echo("What's next:")
    click.echo("  1. Open this folder in Claude Code or OpenCode")
    click.echo("  2. Run /ingest to build the search index")
    click.echo("  3. Run /search \"<query>\" to explore your codebase")
    click.echo("  4. Run /enrich to annotate symbols as you learn")
    click.echo("")
    click.echo("All-Might skills auto-load — just start asking questions.")


# ------------------------------------------------------------------
# Metrics
# ------------------------------------------------------------------

@main.command("power-level")
@click.option("--config", "config_path", default="config.yaml", type=click.Path())
def power_level(config_path: str):
    """Show the project's Power Level — knowledge graph coverage metrics."""
    from pathlib import Path as P

    from rich.console import Console
    from rich.table import Table

    from .enrichment.tracker import PowerTracker

    console = Console()
    tracker = PowerTracker()
    level = tracker.calculate(P(config_path))

    console.print(f"\n[bold]Power Level: {level.coverage_pct:.1f}%[/bold]\n")

    table = Table(title="Coverage by Index")
    table.add_column("Index", style="cyan")
    table.add_column("Coverage", justify="right")

    for index_name, pct in level.by_index.items():
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        table.add_row(index_name, f"{bar} {pct:.1f}%")

    console.print(table)
    console.print(f"\nSymbols: {level.enriched_symbols}/{level.total_symbols}")
    console.print(f"Files with sidecars: {level.files_with_sidecars}/{level.total_files}")
    console.print(f"Total relations: {level.total_relations}")


# ------------------------------------------------------------------
# Config management
# ------------------------------------------------------------------

@main.group()
def config():
    """Manage corpora and project configuration."""


@config.command("add-index")
@click.option("--name", required=True, help="Index name")
@click.option("--description", required=True, help="Index description")
@click.option("--paths", required=True, multiple=True, help="Paths to include (repeatable)")
@click.option("--uri", default=None, help="Corpus storage path (default: ./smak/<name>)")
@click.option("--path-env", default=None, help="Environment variable for path prefix")
@click.option("--root", "root_path", default=".", type=click.Path(exists=True), help="Project root")
def config_add_index(name: str, description: str, paths: tuple, uri: str | None, path_env: str | None, root_path: str):
    """Add a new corpus."""
    from pathlib import Path as P

    from .config import ConfigManager

    mgr = ConfigManager(P(root_path).resolve())
    idx = mgr.add_index(name, description, list(paths), uri=uri, path_env=path_env)
    click.echo(f"Added index '{idx.name}': {idx.description}")


@config.command("remove-index")
@click.option("--name", required=True, help="Index name to remove")
@click.option("--root", "root_path", default=".", type=click.Path(exists=True), help="Project root")
def config_remove_index(name: str, root_path: str):
    """Remove an existing corpus."""
    from pathlib import Path as P

    from .config import ConfigManager

    mgr = ConfigManager(P(root_path).resolve())
    mgr.remove_index(name)
    click.echo(f"Removed index '{name}'.")


@config.command("list-indices")
@click.option("--root", "root_path", default=".", type=click.Path(exists=True), help="Project root")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def config_list_indices(root_path: str, as_json: bool):
    """List all corpora."""
    import json
    from pathlib import Path as P

    from .config import ConfigManager

    mgr = ConfigManager(P(root_path).resolve())
    indices = mgr.list_indices()

    if as_json:
        data = [{"name": i.name, "uri": i.uri, "description": i.description, "paths": i.paths} for i in indices]
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return

    if not indices:
        click.echo("No indices configured.")
        return

    for idx in indices:
        click.echo(f"  {idx.name}: {idx.description} ({', '.join(idx.paths)})")


@config.command("update-index")
@click.option("--name", required=True, help="Index name to update")
@click.option("--description", default=None, help="New description")
@click.option("--paths", multiple=True, help="New paths (repeatable)")
@click.option("--root", "root_path", default=".", type=click.Path(exists=True), help="Project root")
def config_update_index(name: str, description: str | None, paths: tuple, root_path: str):
    """Update an existing corpus."""
    from pathlib import Path as P

    from .config import ConfigManager

    kwargs: dict = {}
    if description is not None:
        kwargs["description"] = description
    if paths:
        kwargs["paths"] = list(paths)

    if not kwargs:
        click.echo("Nothing to update. Provide --description or --paths.")
        return

    mgr = ConfigManager(P(root_path).resolve())
    updated = mgr.update_index(name, **kwargs)
    click.echo(f"Updated index '{updated.name}'.")


# ------------------------------------------------------------------
# Agent Memory System
# ------------------------------------------------------------------

@main.group()
def memory():
    """Agent memory system — three-layer persistent memory."""


@memory.command("init")
@click.argument("path", default=".", type=click.Path(exists=True))
def memory_init(path: str):
    """Initialize the agent memory subsystem.

    Creates memory/ directory structure, config, memory stores for
    episodes and semantic facts, memory skill, and slash commands.
    Requires config.yaml to exist (run 'allmight init' first).
    """
    from pathlib import Path as P

    from .memory.initializer import MemoryInitializer

    root = P(path).resolve()
    config_path = root / "config.yaml"
    if not config_path.exists():
        click.echo("Error: config.yaml not found. Run 'allmight init' first.")
        raise SystemExit(1)

    initializer = MemoryInitializer()
    initializer.initialize(root)

    click.echo("Agent Memory System initialized.")
    click.echo("  Working memory:  memory/working/MEMORY.md")
    click.echo("  Episodic store:  memory/episodes/")
    click.echo("  Semantic store:  memory/semantic/")
    click.echo("  Memory config:   memory/config.yaml")


@memory.command("status")
@click.option("--config", "config_path", default="config.yaml", type=click.Path())
def memory_status(config_path: str):
    """Show memory health: episodes, facts, working memory usage, decay."""
    from pathlib import Path as P

    from rich.console import Console
    from rich.table import Table

    from .memory.config import MemoryConfigManager
    from .memory.episodic import EpisodicMemoryStore
    from .memory.semantic import SemanticMemoryStore
    from .memory.working import WorkingMemoryManager

    console = Console()
    root = P(config_path).resolve().parent

    cfg = MemoryConfigManager(root).load()
    working = WorkingMemoryManager(root, budget=cfg.working_memory_budget)
    episodic = EpisodicMemoryStore(root)
    semantic = SemanticMemoryStore(root)

    console.print("\n[bold]Agent Memory Health[/bold]\n")

    # Working memory
    budget = working.budget_status()
    console.print(f"Working Memory: {budget['tokens_used']}/{budget['budget']} tokens"
                  f" ({'OVER' if budget['over_budget'] else 'OK'})")

    # Episodic
    ep_total = episodic.count()
    ep_uncon = episodic.count_unconsolidated()
    console.print(f"Episodes: {ep_total} total, {ep_uncon} unconsolidated")

    # Semantic
    fact_total = semantic.count()
    avg_conf = semantic.avg_confidence()
    console.print(f"Semantic Facts: {fact_total} total, avg confidence {avg_conf:.2f}")


@memory.command("gc")
@click.option("--config", "config_path", default="config.yaml", type=click.Path())
@click.option("--dry-run", is_flag=True, help="Show what would be archived without doing it")
def memory_gc(config_path: str, dry_run: bool):
    """Run decay sweep and report dormant/archivable entries."""
    from pathlib import Path as P

    from .memory.decay import DecayEngine
    from .memory.semantic import SemanticMemoryStore

    root = P(config_path).resolve().parent
    semantic = SemanticMemoryStore(root)
    engine = DecayEngine()

    facts = semantic.list_facts(limit=10000)
    dormant = 0
    archivable = 0

    for fact in facts:
        status = engine.classify(
            fact.last_accessed or fact.updated_at or fact.created_at,
            fact.access_count,
        )
        if status == "dormant":
            dormant += 1
        elif status == "archivable":
            archivable += 1

    action = "Would archive" if dry_run else "Archivable"
    click.echo(f"Total facts: {len(facts)}")
    click.echo(f"Dormant: {dormant}")
    click.echo(f"{action}: {archivable}")

    if not dry_run and archivable > 0:
        click.echo("(Use --dry-run to preview. Actual archival not yet implemented.)")
