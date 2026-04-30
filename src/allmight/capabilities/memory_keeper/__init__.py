"""memory_keeper personality template.

Generates the L1/L2/L3 agent memory system: ``MEMORY.md`` at the
project root, ``memory/`` inside the instance dir (config + journal +
understanding + store), the ``/remember`` ``/recall``
commands, the AGENTS.md memory section, and the OpenCode plugins
(``memory-load``, ``remember-trigger``, ``todo-curator``,
``trajectory-writer``, ``usage-logger``).

memory_keeper exposes no CLI flags; ``allmight init`` always installs it.

L1/L2/L3 recap (matches the original system):
- L1 — ``MEMORY.md`` at project root, always in context via hook.
- L2 — ``personalities/<m>/memory/understanding/`` per-corpus knowledge.
- L3 — ``personalities/<m>/memory/journal/`` searchable via SMAK.
"""

from __future__ import annotations

from pathlib import Path

from ...core.personalities import (
    InstallContext,
    InstallResult,
    Personality,
    PersonalityStatus,
    PersonalityTemplate,
)
from .initializer import MemoryInitializer


def _install(ctx: InstallContext, instance: Personality) -> InstallResult:
    """Bootstrap one memory_keeper instance.

    Honours ``ctx.staging``: when re-initialising an existing project
    the templates land in ``.allmight/templates/`` for ``/sync`` to
    merge. Otherwise writes directly into the instance dir.
    """
    MemoryInitializer().initialize(
        ctx.project_root,
        staging=ctx.staging,
        instance_root=instance.root,
    )
    return InstallResult(notes=[f"memory_keeper: staging={ctx.staging}"])


def _status(root: Path, instance: Personality) -> PersonalityStatus:
    """Reflect on-disk presence of the instance's memory dir."""
    memory_dir = instance.root / "memory"
    installed = memory_dir.is_dir() and (root / "MEMORY.md").exists()
    return PersonalityStatus(
        installed=installed,
        version_on_disk=TEMPLATE.version if installed else None,
        details={
            "instance_root": str(instance.root),
            "memory_dir": str(memory_dir),
            "has_memory_md": (root / "MEMORY.md").exists(),
            "has_journal": (memory_dir / "journal").is_dir(),
        },
    )


TEMPLATE = PersonalityTemplate(
    name="memory_keeper",
    short_name="memory",
    version="1.0.0",
    default_instance_name="memory",
    description=(
        "L1/L2/L3 agent memory: MEMORY.md, /remember (record + reflect) "
        "/recall, OpenCode plugins."
    ),
    owned_paths=[
        "personalities/{instance}/commands/**",
        "personalities/{instance}/plugins/**",
        "personalities/{instance}/memory/**",
        "MEMORY.md",
    ],
    cli_options=[],
    install=_install,
    status=_status,
)
