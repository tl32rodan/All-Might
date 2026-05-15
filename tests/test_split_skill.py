"""``/split`` skill — in-project personality refactor (1 → 1).

``/split`` is the third corner of the personality-lifecycle triangle:
``/onboard`` creates (0 → N), ``/one-for-all`` exports (1 → 1
outward), ``/all-for-one`` absorbs (N → 1 inward). ``/split`` covers
the in-project refactor case (1 → 1, same project) — extract a slice
of one personality's memory + ROLE.md scope into another personality
(new or existing).

Design invariants this file pins:

* Manual-only trigger. The AGENTS.md primer must not list ``/split``
  in its "When to suggest user actions" table (tested in
  ``test_personalities_compose.py::test_split_listed_but_not_in_when_to_suggest``).
* Database workspaces are explicitly **not** moved. The skill body
  must say so and must point at ``smak ingest`` as the user-driven
  bootstrap path.
* Lineage is recorded in the target's ``derived_from`` list with the
  schema ``{kind: personality, name: <src>, action: split}``. The
  ``action: split`` discriminator distinguishes split-derived
  ancestry from merge-derived (``/all-for-one``) ancestry.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from allmight.cli import main


def _invoke_in(root: Path, args: list[str]):
    runner = CliRunner()
    cwd = os.getcwd()
    try:
        os.chdir(root)
        return runner.invoke(main, args, catch_exceptions=False)
    finally:
        os.chdir(cwd)


@pytest.fixture
def initted_project(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("def f(): pass\n")
    (project / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--yes", str(project)])
    assert result.exit_code == 0, result.output
    return project


# -----------------------------------------------------------------------
# Skill body content
# -----------------------------------------------------------------------


class TestSplitSkillBody:
    def test_skill_body_imports(self) -> None:
        from allmight.capabilities.database.split_skill_content import (
            SPLIT_COMMAND_BODY,
            SPLIT_SKILL_BODY,
        )
        assert SPLIT_SKILL_BODY
        assert SPLIT_COMMAND_BODY

    def test_skill_body_cardinality_callout(self) -> None:
        """The skill body must state ``1 → 1, same project`` and point
        at the inverse / sibling skills so the agent never confuses
        ``/split`` with ``/all-for-one`` (N → 1) or ``/one-for-all``
        (cross-project)."""
        from allmight.capabilities.database.split_skill_content import (
            SPLIT_SKILL_BODY,
        )
        body = SPLIT_SKILL_BODY
        assert "1 → 1" in body or "1 → 1" in body
        assert "same project" in body.lower() or "in-project" in body.lower()
        assert "/one-for-all" in body
        assert "/all-for-one" in body

    def test_skill_body_describes_target_kinds(self) -> None:
        """Target can be a new personality (triggers ``allmight add``)
        or an existing one (in-place merge)."""
        from allmight.capabilities.database.split_skill_content import (
            SPLIT_SKILL_BODY,
        )
        body = SPLIT_SKILL_BODY
        assert "new" in body.lower()
        assert "existing" in body.lower()
        assert "allmight add" in body

    def test_skill_body_describes_memory_buckets(self) -> None:
        """Migration plan must cover both memory buckets explicitly —
        ``understanding/`` (per-file) and ``journal/`` (per-subdir)."""
        from allmight.capabilities.database.split_skill_content import (
            SPLIT_SKILL_BODY,
        )
        body = SPLIT_SKILL_BODY
        assert "understanding" in body
        assert "journal" in body

    def test_skill_body_uses_git_mv(self) -> None:
        """Memory moves go through ``git mv`` so the post-turn snapshot
        hook captures the move correctly."""
        from allmight.capabilities.database.split_skill_content import (
            SPLIT_SKILL_BODY,
        )
        assert "git mv" in SPLIT_SKILL_BODY

    def test_skill_body_excludes_database_workspaces(self) -> None:
        """The defining decision: ``/split`` does not touch database
        workspaces. The skill body must say so explicitly and point at
        ``smak ingest`` as the user-driven bootstrap path."""
        from allmight.capabilities.database.split_skill_content import (
            SPLIT_SKILL_BODY,
        )
        body = SPLIT_SKILL_BODY
        body_lower = body.lower()
        # Hard rule: workspaces stay put.
        assert "not touch" in body_lower or "not moved" in body_lower \
            or "untouched" in body_lower or "stay put" in body_lower
        # Pointer to the user-driven bootstrap path.
        assert "smak ingest" in body

    def test_skill_body_describes_lineage_schema(self) -> None:
        """``derived_from`` is the lineage record. Schema must be
        ``{kind: personality, name, action: split}`` so split-derived
        ancestry is distinguishable from ``/all-for-one``'s
        merge-derived entries."""
        from allmight.capabilities.database.split_skill_content import (
            SPLIT_SKILL_BODY,
        )
        body = SPLIT_SKILL_BODY
        assert "derived_from" in body
        assert "kind: personality" in body
        assert "action: split" in body

    def test_skill_body_forbids_auto_trigger(self) -> None:
        """``/split`` is manual-only. The skill body must instruct the
        agent **not** to volunteer the command on context cues, so a
        cold reading reinforces the design promise."""
        from allmight.capabilities.database.split_skill_content import (
            SPLIT_SKILL_BODY,
        )
        body = SPLIT_SKILL_BODY
        body_lower = body.lower()
        assert "manual only" in body_lower or "manual-only" in body_lower
        # Explicit "do not propose" / "do not volunteer" language.
        assert "do not propose" in body_lower or \
            "do not volunteer" in body_lower

    def test_skill_body_forbids_pending_bootstrap_annotation(self) -> None:
        """Earlier design rounds proposed writing a "pending bootstrap"
        section into the target's ROLE.md. We deliberately do not do
        this — the role description itself is the indexing hint. Pin
        the rejection so a future contributor does not re-introduce
        it from the converged design notes."""
        from allmight.capabilities.database.split_skill_content import (
            SPLIT_SKILL_BODY,
        )
        body_lower = SPLIT_SKILL_BODY.lower()
        assert "pending bootstrap" in body_lower
        # Must explicitly say *do not* write it.
        assert "do not write" in body_lower or "no \"pending" in body_lower


# -----------------------------------------------------------------------
# Command body content
# -----------------------------------------------------------------------


class TestSplitCommandBody:
    def test_command_body_imports(self) -> None:
        from allmight.capabilities.database.split_skill_content import (
            SPLIT_COMMAND_BODY,
        )
        assert SPLIT_COMMAND_BODY

    def test_command_body_points_at_sibling_skills(self) -> None:
        """Command body must teach the agent the surface map so it
        doesn't mis-route between the three lifecycle commands."""
        from allmight.capabilities.database.split_skill_content import (
            SPLIT_COMMAND_BODY,
        )
        body = SPLIT_COMMAND_BODY
        assert "/one-for-all" in body
        assert "/all-for-one" in body
        assert "/onboard" in body

    def test_command_body_calls_out_rarity(self) -> None:
        """Rarity framing keeps the agent from over-suggesting."""
        from allmight.capabilities.database.split_skill_content import (
            SPLIT_COMMAND_BODY,
        )
        assert "rare" in SPLIT_COMMAND_BODY.lower()


# -----------------------------------------------------------------------
# Install presence
# -----------------------------------------------------------------------


class TestSplitSkillIsInstalled:
    def test_skill_present_after_init(self, initted_project: Path) -> None:
        skill = initted_project / ".opencode" / "skills" / "split" / "SKILL.md"
        assert skill.exists()

    def test_command_present_after_init(self, initted_project: Path) -> None:
        cmd = initted_project / ".opencode" / "commands" / "split.md"
        assert cmd.exists()

    def test_installed_skill_carries_expected_signals(
        self, initted_project: Path,
    ) -> None:
        """End-to-end check: the file on disk after ``allmight init``
        carries the same invariants the body-level tests pin (manual
        only, ``derived_from`` schema, no DB workspace migration).
        Catches the regression where the constant exists but isn't
        wired into ``initialize_globals``."""
        skill = initted_project / ".opencode" / "skills" / "split" / "SKILL.md"
        content = skill.read_text()
        assert "manual only" in content.lower() or \
            "manual-only" in content.lower()
        assert "derived_from" in content
        assert "action: split" in content
        assert "smak ingest" in content
