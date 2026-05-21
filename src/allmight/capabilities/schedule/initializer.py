"""Schedule capability initializer (T1).

T1 scope:
- ``initialize_globals(root)`` — writes the ``scheduling`` skill into
  ``.opencode/skills/scheduling/SKILL.md``. No commands, no plugins.
- ``initialize(root, instance_root)`` — creates an empty
  ``personalities/<p>/scheduled/`` directory so the agent has a
  declarative target to point at (per the SKILL.md forward
  reference). T1 does **not** read this directory; T2 will.

No Claude Code mirror — schedule is OpenCode-first; CC users have
Anthropic's Desktop scheduled tasks for the persistent-runtime
case. See ``docs/schedule-proposal.md`` P-6.
"""

from __future__ import annotations

from pathlib import Path

from ...core.skill_io import install_skill
from .skill_content import (
    SCHEDULING_SKILL_DESCRIPTION,
    build_scheduling_skill_md,
)


class ScheduleInitializer:
    """Write the project-wide skill and per-personality scaffold dir."""

    def initialize_globals(
        self,
        project_root: Path,
        *,
        force: bool = False,
        staging: bool = False,
    ) -> None:
        """Write ``.opencode/skills/scheduling/SKILL.md``.

        ``staging`` is accepted for parity with the other capability
        initializers but currently ignored — the skill body is small
        and never conflicts in practice, so it goes straight to the
        live path. If/when the skill grows surface that can conflict
        with user edits, route through ``.allmight/templates/`` here
        the same way memory does.
        """
        del staging  # T1: skill body is small, no staging path yet
        install_skill(
            project_root,
            name="scheduling",
            description=SCHEDULING_SKILL_DESCRIPTION,
            skill_body=build_scheduling_skill_md(),
            force=force,
        )

    def initialize(
        self,
        project_root: Path,
        *,
        instance_root: Path,
        staging: bool = False,
        force: bool = False,
    ) -> None:
        """Create ``personalities/<instance>/scheduled/`` (empty).

        T1 only scaffolds the directory. The agent may drop
        ``<task>.md`` files inside as a reference for the user, but
        All-Might does not read them yet — that lands in T2's
        ``allmight schedule apply``.
        """
        del project_root, staging, force  # T1 no-op apart from mkdir
        (instance_root / "scheduled").mkdir(parents=True, exist_ok=True)
