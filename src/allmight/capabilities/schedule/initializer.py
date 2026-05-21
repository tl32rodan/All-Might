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
        """Write ``.opencode/skills/scheduling/SKILL.md`` on fresh init only.

        Matches the established pattern (memory's ``recover``, database's
        ``onboard`` / ``one-for-all`` / ``all-for-one`` / ``split``):
        skill bodies are written on fresh init via ``install_skill``
        (which carries ``ALLMIGHT_MARKER_MD`` and uses ``write_guarded``)
        and **skipped** on re-init. The on-disk SKILL.md from the
        previous install stays in place; ``allmight init --force`` is
        the documented escape hatch when a refresh is desired.

        Only the ``/sync`` skill itself is unconditionally re-written —
        because it's the meta-skill that teaches the agent how to
        reconcile staged templates with user-customised files.

        T2 follow-up: if the scheduling docs start evolving frequently
        enough that "stale on re-init" becomes a real problem, stage
        the SKILL.md to ``.allmight/templates/skills/scheduling/SKILL.md``
        and teach the ``/sync`` skill (in
        ``src/allmight/capabilities/database/sync_skill_content.py``)
        about ``.allmight/templates/skills/<name>/`` → ``.opencode/
        skills/<name>/`` mapping. Currently no mapping exists, so
        full proper staging needs both ends updated.
        """
        if staging:
            return
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
