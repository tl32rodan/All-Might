"""All-Might CLI — bootstrapping only.

All-Might is an **agent harness**, not a CLI tool.  The CLI exists only
for the one operation that cannot be agent-driven:

    allmight init [path]            — Bootstrap a workspace
    allmight memory init [path]     — Add agent memory subsystem

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
@click.option("--smak-path", type=click.Path(exists=True), help="Path to SMAK installation (for skill copying)")
@click.option("--sos", is_flag=True, help="Enable SOS/EDA environment support")
@click.option("--with-memory", is_flag=True, help="Also initialize the agent memory subsystem")
def init(path: str, smak_path: str | None, sos: bool, with_memory: bool):
    """Bootstrap a workspace with skills and commands.

    Scans the project, creates config.yaml, and injects .claude/skills
    and .claude/commands that teach the agent how to operate.
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

    click.echo(f"All-Might! Project '{manifest.name}' initialized.")
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
# Agent Memory System
# ------------------------------------------------------------------

@main.group()
def memory():
    """Agent memory system — three-layer persistent memory."""


@memory.command("init")
@click.argument("path", default=".", type=click.Path(exists=True))
def memory_init(path: str):
    """Add agent memory to an existing workspace.

    Creates memory/ directory structure, appends memory guide to the
    one-for-all skill, and generates /remember, /recall, /consolidate
    commands.  Requires config.yaml (run 'allmight init' first).
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
