"""``schedule`` capability template (T1).

T1 ships the agent skill (`.opencode/skills/scheduling/SKILL.md`)
plus an empty per-personality ``scheduled/`` directory. The runtime
is the [`opencode-scheduler`](https://github.com/different-ai/opencode-scheduler)
OpenCode plugin — All-Might does not own the cron / launchd /
systemd wrapping. See ``docs/schedule-proposal.md``.

T2 (deferred) will add ``allmight schedule apply``, a schema probe,
and the ``schedule-sync.ts`` marker-file plugin.
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
from .initializer import ScheduleInitializer


def _install_globals(ctx: InstallContext) -> None:
    """Project-wide install — writes the scheduling skill once."""
    ScheduleInitializer().initialize_globals(
        ctx.project_root,
        force=ctx.force,
        staging=ctx.staging,
    )


def _install(ctx: InstallContext, instance: Personality) -> InstallResult:
    """Per-personality install — creates the empty ``scheduled/`` dir."""
    ScheduleInitializer().initialize(
        ctx.project_root,
        staging=ctx.staging,
        instance_root=instance.root,
        force=ctx.force,
    )
    return InstallResult(notes=[f"schedule: staging={ctx.staging}"])


def _status(root: Path, instance: Personality) -> PersonalityStatus:
    """Reflect on-disk presence of the per-personality ``scheduled/`` dir
    and the project-wide skill."""
    scheduled_dir = instance.root / "scheduled"
    skill_md = root / ".opencode" / "skills" / "scheduling" / "SKILL.md"
    installed = scheduled_dir.is_dir() and skill_md.exists()
    return PersonalityStatus(
        installed=installed,
        version_on_disk=TEMPLATE.version if installed else None,
        details={
            "instance_root": str(instance.root),
            "scheduled_dir": str(scheduled_dir),
            "has_skill": skill_md.exists(),
            "declared_tasks": (
                sorted(p.name for p in scheduled_dir.glob("*.md"))
                if scheduled_dir.is_dir()
                else []
            ),
        },
    )


TEMPLATE = PersonalityTemplate(
    name="schedule",
    short_name="schedule",
    version="1.0.0",
    default_instance_name="schedule",
    description=(
        "Periodic All-Might tasks via the opencode-scheduler plugin. "
        "T1 ships the agent skill + per-personality scheduled/ dir; "
        "T2 adds declarative apply + schema probe."
    ),
    owned_paths=[
        "personalities/{instance}/scheduled/**",
        ".opencode/skills/scheduling/**",
    ],
    cli_options=[],
    install=_install,
    install_globals=_install_globals,
    status=_status,
)
