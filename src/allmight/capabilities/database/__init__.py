"""database capability template.

Generates ``database/`` workspaces (the on-disk vector index +
SMAK config), the ``/search`` and ``/sync`` commands, the AGENTS.md
section, and the bundled /sync skill.

The template's ``cli_options`` contribute ``--sos`` to ``allmight
init`` — that flag is not interpreted by ``cli.py``; its parsed
value flows into ``Personality.options`` and is read inside
``_install``.
"""

from __future__ import annotations

from pathlib import Path

from ...core.personalities import (
    CliOption,
    InstallContext,
    InstallResult,
    Personality,
    PersonalityStatus,
    PersonalityTemplate,
)
from .initializer import ProjectInitializer


def _install_globals(ctx: InstallContext) -> None:
    """Project-wide install — skills, commands, ``.allmight/`` setup.

    Reads ``sos`` from ``ctx.options``. No ``Personality`` instance
    exists at this stage — per-personality writes happen later in
    :func:`_install` when the user runs ``allmight add`` (or
    ``/onboard`` shells out to ``add``).
    """
    if ctx.options.get("sos"):
        ctx.manifest.has_path_env = True
    ProjectInitializer().initialize_globals(
        ctx.project_root,
        ctx.manifest,
        force=ctx.force,
        staging=ctx.staging,
    )


def _install(ctx: InstallContext, instance: Personality) -> InstallResult:
    """Bootstrap one database capability instance.

    Reads ``--sos`` from ``instance.options``. The SOS toggle flips
    ``manifest.has_path_env`` so the AGENTS.md section renders with
    the SOS prerequisites.
    """
    if instance.options.get("sos"):
        ctx.manifest.has_path_env = True
    ProjectInitializer().initialize(
        ctx.manifest,
        force=ctx.force,
        instance_root=instance.root,
    )
    return InstallResult(notes=["database: installed"])


def _status(root: Path, instance: Personality) -> PersonalityStatus:
    """Reflect on-disk presence of the instance's owned files."""
    instance_root = instance.root
    installed = (instance_root / "database").is_dir()
    return PersonalityStatus(
        installed=installed,
        version_on_disk=TEMPLATE.version if installed else None,
        details={
            "instance_root": str(instance_root),
            "has_database": (instance_root / "database").is_dir(),
            "has_commands": (instance_root / "commands").is_dir(),
        },
    )


TEMPLATE = PersonalityTemplate(
    name="database",
    short_name="database",
    version="1.0.0",
    default_instance_name="knowledge",
    description=(
        "Knowledge-graph workspaces, /search /sync commands, "
        "AGENTS.md section."
    ),
    owned_paths=[
        "personalities/{instance}/skills/**",
        "personalities/{instance}/commands/**",
        "personalities/{instance}/database/**",
        "AGENTS.md",
    ],
    cli_options=[
        CliOption(
            name="sos",
            flag="--sos",
            help="Enable SOS/EDA environment support (sets $DDI_ROOT_PATH usage).",
        ),
    ],
    install=_install,
    install_globals=_install_globals,
    status=_status,
)
