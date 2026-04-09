"""All-Might CLI — the command-line interface for non-Claude-Code environments.

Commands:
    allmight init [path]        — Detroit SMAK: bootstrap a project
    allmight generate [--config] — Regenerate One For All SKILL.md
    allmight power-level        — Show knowledge graph coverage
    allmight panorama           — Export knowledge graph visualization
"""

from __future__ import annotations

import click

from . import __version__


@click.group()
@click.version_option(version=__version__, prog_name="allmight")
def main():
    """All-Might: Active Knowledge Graph Framework.

    The active layer on top of SMAK — transforms agents from passive
    queriers into active knowledge curators.
    """


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--smak-path", type=click.Path(exists=True), help="Path to SMAK installation (for skill copying)")
@click.option("--sos", is_flag=True, help="Enable SOS/EDA environment support")
def init(path: str, smak_path: str | None, sos: bool):
    """Detroit SMAK — one punch to bootstrap the entire workspace.

    Scans the project, creates all-might/ workspace, generates
    workspace_config.yaml, and injects .claude/skills and commands.
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

    click.echo(f"Detroit SMAK! Project '{manifest.name}' initialized.")
    click.echo(f"  Languages: {', '.join(manifest.languages) or 'none detected'}")
    click.echo(f"  Indices:   {len(manifest.indices)}")
    click.echo(f"  Workspace: {root / 'all-might'}")


@main.command()
@click.option("--config", "config_path", default="all-might/config.yaml", type=click.Path())
def generate(config_path: str):
    """Regenerate One For All — update SKILL.md with current project state."""
    from pathlib import Path as P

    from .one_for_all.generator import OneForAllGenerator

    generator = OneForAllGenerator()
    skill_content = generator.generate(P(config_path))
    click.echo("One For All regenerated.")
    click.echo(f"  Output: .claude/skills/one-for-all/SKILL.md")
    click.echo(f"  Length: {len(skill_content)} characters")


@main.command("power-level")
@click.option("--config", "config_path", default="all-might/config.yaml", type=click.Path())
def power_level(config_path: str):
    """Show the project's Power Level — knowledge graph coverage metrics."""
    from pathlib import Path as P

    from rich.console import Console
    from rich.table import Table

    from .enrichment.tracker import PowerTracker

    console = Console()
    tracker = PowerTracker()
    level = tracker.calculate(P(config_path))

    console.print(f"\n[bold]⚡ Power Level: {level.coverage_pct:.1f}%[/bold]\n")

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


@main.command()
@click.option("--config", "config_path", default="all-might/config.yaml", type=click.Path())
@click.option("--format", "fmt", type=click.Choice(["json", "mermaid", "obsidian"]), default="json")
@click.option("--output", "output_dir", default="all-might/panorama", type=click.Path())
def panorama(config_path: str, fmt: str, output_dir: str):
    """Export the knowledge graph as a panoramic visualization."""
    from pathlib import Path as P

    from .panorama.exporter import PanoramaExporter

    exporter = PanoramaExporter()
    output = exporter.export(P(config_path), fmt=fmt, output_dir=P(output_dir))
    click.echo(f"Panorama exported: {output}")
