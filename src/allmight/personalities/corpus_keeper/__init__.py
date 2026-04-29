"""corpus_keeper personality template.

Generates ``knowledge_graph/`` workspaces, the ``/search``,
``/enrich``, ``/ingest``, ``/sync`` commands, the AGENTS.md section,
and the bundled /sync skill.

The template's ``cli_options`` contribute ``--sos`` and ``--writable``
to ``allmight init`` — those flags are not interpreted by ``cli.py``;
their parsed values flow into ``Personality.options`` and are read
inside ``_install``.
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


def _install(ctx: InstallContext, instance: Personality) -> InstallResult:
    """Bootstrap one corpus_keeper instance.

    Reads ``--sos`` / ``--writable`` from ``instance.options``. The
    SOS toggle flips ``manifest.has_path_env`` so the AGENTS.md
    section and command bodies render with the SOS prerequisites.
    """
    if instance.options.get("sos"):
        ctx.manifest.has_path_env = True
    writable = bool(instance.options.get("writable", False))
    ProjectInitializer().initialize(
        ctx.manifest,
        force=ctx.force,
        writable=writable,
        instance_root=instance.root,
    )
    return InstallResult(notes=[f"corpus_keeper: writable={writable}"])


def _status(root: Path, instance: Personality) -> PersonalityStatus:
    """Reflect on-disk presence of the instance's owned files."""
    instance_root = instance.root
    installed = (instance_root / "knowledge_graph").is_dir()
    return PersonalityStatus(
        installed=installed,
        version_on_disk=TEMPLATE.version if installed else None,
        details={
            "instance_root": str(instance_root),
            "has_knowledge_graph": (instance_root / "knowledge_graph").is_dir(),
            "has_commands": (instance_root / "commands").is_dir(),
        },
    )


TEMPLATE = PersonalityTemplate(
    name="corpus_keeper",
    short_name="corpus",
    version="1.0.0",
    description=(
        "Knowledge-graph workspaces, /search /enrich /ingest /sync "
        "commands, AGENTS.md section."
    ),
    owned_paths=[
        "personalities/{instance}/skills/**",
        "personalities/{instance}/commands/**",
        "personalities/{instance}/knowledge_graph/**",
        "AGENTS.md",
    ],
    cli_options=[
        CliOption(
            name="sos",
            flag="--sos",
            help="Enable SOS/EDA environment support (sets $DDI_ROOT_PATH usage).",
        ),
        CliOption(
            name="writable",
            flag="--writable",
            help="Full access mode: enable ingest, enrich, annotation.",
        ),
    ],
    install=_install,
    status=_status,
)
