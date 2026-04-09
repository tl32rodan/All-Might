"""All-Might CLI — the command-line interface for non-Claude-Code environments.

Commands:
    allmight init [path]        — Detroit SMAK: bootstrap a project
    allmight generate [--config] — Regenerate One For All SKILL.md
    allmight power-level        — Show knowledge graph coverage
    allmight panorama           — Export knowledge graph visualization
    allmight search             — Semantic search with graph context
    allmight lookup             — Look up a symbol by UID
    allmight enrich             — Enrich a symbol with intent/relations
    allmight ingest             — Trigger SMAK ingest
    allmight explain            — Show full graph context for a symbol
    allmight report             — Generate graph intelligence report
    allmight config             — Manage indices (add/remove/list/update)
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


# ------------------------------------------------------------------
# Search & Lookup (via SmakBridge)
# ------------------------------------------------------------------

def _workspace_config(config_path: str) -> str:
    """Resolve workspace_config.yaml path from all-might/config.yaml."""
    from pathlib import Path as P

    from .utils.yaml_io import load_config

    config = load_config(P(config_path))
    root = P(config.get("project", {}).get("root", P(config_path).parent.parent))
    rel = config.get("smak", {}).get("config_path", "workspace_config.yaml")
    return str(root / rel)


@main.command()
@click.argument("query")
@click.option("--index", default="source_code", help="SMAK index to search")
@click.option("--top-k", default=5, type=int, help="Number of results")
@click.option("--config", "config_path", default="all-might/config.yaml", type=click.Path())
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def search(query: str, index: str, top_k: int, config_path: str, as_json: bool):
    """Semantic search with graph context."""
    import json

    from .bridge import SmakBridge

    ws = _workspace_config(config_path)
    bridge = SmakBridge(workspace_config=ws)
    result = bridge.search(query, index=index, top_k=top_k)

    if as_json:
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        return

    hits = result.get("hits", [])
    if not hits:
        click.echo("No results found.")
        return

    for i, hit in enumerate(hits, 1):
        uid = hit.get("uid", "?")
        score = hit.get("score", 0)
        click.echo(f"  {i}. {uid}  (score: {score:.4f})")


@main.command()
@click.argument("uid")
@click.option("--index", default="source_code", help="SMAK index")
@click.option("--config", "config_path", default="all-might/config.yaml", type=click.Path())
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def lookup(uid: str, index: str, config_path: str, as_json: bool):
    """Look up a symbol by UID in the vector store."""
    import json

    from .bridge import SmakBridge

    ws = _workspace_config(config_path)
    bridge = SmakBridge(workspace_config=ws)
    result = bridge.lookup(uid, index=index)

    if as_json:
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if result.get("found"):
        click.echo(f"UID: {result.get('uid')}")
        click.echo(f"Content preview: {str(result.get('content', ''))[:200]}")
    else:
        click.echo(f"UID '{uid}' not found.")


# ------------------------------------------------------------------
# Enrichment (via SmakBridge)
# ------------------------------------------------------------------

@main.command()
@click.option("--file", "file_path", required=True, help="Source file path")
@click.option("--symbol", required=True, help="Symbol name")
@click.option("--intent", default=None, help="Intent description")
@click.option("--relation", "relations", multiple=True, help="Related UIDs (repeatable)")
@click.option("--index", default="source_code", help="SMAK index")
@click.option("--bidirectional", is_flag=True, help="Create bidirectional relations")
@click.option("--config", "config_path", default="all-might/config.yaml", type=click.Path())
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def enrich(file_path: str, symbol: str, intent: str | None, relations: tuple,
           index: str, bidirectional: bool, config_path: str, as_json: bool):
    """Enrich a symbol with intent and/or relations."""
    import json

    from .bridge import SmakBridge

    ws = _workspace_config(config_path)
    bridge = SmakBridge(workspace_config=ws)
    result = bridge.enrich_symbol(
        file_path, symbol,
        intent=intent,
        relations=list(relations) or None,
        index=index,
        bidirectional=bidirectional,
    )

    if as_json:
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        return

    click.echo(f"Enriched {file_path}::{symbol}")
    if intent:
        click.echo(f"  Intent: {intent}")
    if relations:
        click.echo(f"  Relations: {', '.join(relations)}")


@main.command()
@click.option("--index", default=None, help="SMAK index (all if omitted)")
@click.option("--config", "config_path", default="all-might/config.yaml", type=click.Path())
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def ingest(index: str | None, config_path: str, as_json: bool):
    """Trigger SMAK ingest for one or all indices."""
    import json

    from .bridge import SmakBridge

    ws = _workspace_config(config_path)
    bridge = SmakBridge(workspace_config=ws)
    result = bridge.ingest(index=index)

    if as_json:
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        return

    click.echo(f"Ingest complete: {result.get('files', '?')} files, {result.get('vectors', '?')} vectors")


# ------------------------------------------------------------------
# Graph Intelligence
# ------------------------------------------------------------------

@main.command()
@click.argument("uid")
@click.option("--config", "config_path", default="all-might/config.yaml", type=click.Path())
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def explain(uid: str, config_path: str, as_json: bool):
    """Show full graph context for a symbol."""
    import json
    from pathlib import Path as P

    from .panorama.analyzer import PanoramaAnalyzer
    from .panorama.graph_intel import GraphIntel

    analyzer = PanoramaAnalyzer()
    graph = analyzer.analyze(P(config_path))
    intel = GraphIntel(graph)
    result = intel.explain(uid)

    if as_json:
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if "error" in result:
        click.echo(result["error"])
        return

    click.echo(f"Symbol: {result['uid']}")
    click.echo(f"  Name:     {result['name']}")
    click.echo(f"  File:     {result['file_path']}")
    click.echo(f"  Index:    {result['index']}")
    click.echo(f"  Intent:   {result['intent'] or '(none)'}")
    click.echo(f"  Degree:   {result['degree']}")
    click.echo(f"  God Node: {'yes' if result['is_god_node'] else 'no'}")
    click.echo(f"  Cluster:  {result['cluster_id']}")
    if result["outgoing"]:
        click.echo(f"  Outgoing: {', '.join(result['outgoing'])}")
    if result["incoming"]:
        click.echo(f"  Incoming: {', '.join(result['incoming'])}")


@main.command()
@click.option("--config", "config_path", default="all-might/config.yaml", type=click.Path())
@click.option("--output", default=None, type=click.Path(), help="Output file path")
def report(config_path: str, output: str | None):
    """Generate a graph intelligence report (Markdown)."""
    from pathlib import Path as P

    from .panorama.analyzer import PanoramaAnalyzer
    from .panorama.graph_intel import GraphIntel

    analyzer = PanoramaAnalyzer()
    graph = analyzer.analyze(P(config_path))
    intel = GraphIntel(graph)
    md = intel.report()

    if output:
        out = P(output)
    else:
        out = P(config_path).parent / "panorama" / "GRAPH_REPORT.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    click.echo(f"Graph report written to {out}")


# ------------------------------------------------------------------
# Config management
# ------------------------------------------------------------------

@main.group()
def config():
    """Manage SMAK indices and project configuration."""


@config.command("add-index")
@click.option("--name", required=True, help="Index name")
@click.option("--description", required=True, help="Index description")
@click.option("--paths", required=True, multiple=True, help="Paths to include (repeatable)")
@click.option("--uri", default=None, help="Vector store URI (default: ./smak/<name>)")
@click.option("--path-env", default=None, help="Environment variable for path prefix")
@click.option("--root", "root_path", default=".", type=click.Path(exists=True), help="Project root")
def config_add_index(name: str, description: str, paths: tuple, uri: str | None, path_env: str | None, root_path: str):
    """Add a new SMAK index."""
    from pathlib import Path as P

    from .config import ConfigManager

    mgr = ConfigManager(P(root_path).resolve())
    idx = mgr.add_index(name, description, list(paths), uri=uri, path_env=path_env)
    click.echo(f"Added index '{idx.name}': {idx.description}")


@config.command("remove-index")
@click.option("--name", required=True, help="Index name to remove")
@click.option("--root", "root_path", default=".", type=click.Path(exists=True), help="Project root")
def config_remove_index(name: str, root_path: str):
    """Remove an existing SMAK index."""
    from pathlib import Path as P

    from .config import ConfigManager

    mgr = ConfigManager(P(root_path).resolve())
    mgr.remove_index(name)
    click.echo(f"Removed index '{name}'.")


@config.command("list-indices")
@click.option("--root", "root_path", default=".", type=click.Path(exists=True), help="Project root")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def config_list_indices(root_path: str, as_json: bool):
    """List all SMAK indices."""
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
    """Update an existing SMAK index."""
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
