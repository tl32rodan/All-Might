"""Upward-symlink composition.

Part-D commit 5 contract: capability templates write the agent
surface (commands, skills, plugins) into the global ``.opencode/``
once. Each personality owns the **upward symlinks**
``personalities/<p>/skills → ../../.opencode/skills`` and
``personalities/<p>/commands → ../../.opencode/commands``, written
by ``core.personalities.compose``.

Before Part-D commit 5, the model was inverted: each personality
instance held its own ``commands/`` / ``skills/`` / ``plugins/``
dirs and ``compose`` created **downward** symlinks
``.opencode/<kind>/<basename> → personalities/<inst>/<kind>/<basename>``.
That made adding a personality cost N file copies even though
generic bodies (commit 3) made the per-instance copies identical.
The flip simplifies the layout and makes
``ls personalities/<p>/`` browsable as a unit (skills/commands link
back to the global set rather than holding stale copies).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from click.testing import CliRunner

from allmight.cli import main


@pytest.fixture
def initted_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")

    runner = CliRunner()
    result = runner.invoke(main, ["init", "--yes", str(tmp_path)])
    assert result.exit_code == 0, result.output
    return tmp_path


def _personalities(root: Path) -> list[Path]:
    base = root / "personalities"
    if not base.exists():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and not p.is_symlink())


class TestUpwardSymlinks:
    def test_each_personality_has_skills_symlink(self, initted_project: Path) -> None:
        personalities = _personalities(initted_project)
        assert personalities, "init must produce at least one personality"
        for p in personalities:
            link = p / "skills"
            assert link.is_symlink(), (
                f"{link.relative_to(initted_project)} must be a symlink "
                f"to ../../.opencode/skills"
            )

    def test_each_personality_has_commands_symlink(self, initted_project: Path) -> None:
        personalities = _personalities(initted_project)
        for p in personalities:
            link = p / "commands"
            assert link.is_symlink(), (
                f"{link.relative_to(initted_project)} must be a symlink "
                f"to ../../.opencode/commands"
            )

    def test_skills_symlink_resolves_to_opencode(self, initted_project: Path) -> None:
        target = (initted_project / ".opencode" / "skills").resolve()
        for p in _personalities(initted_project):
            link = p / "skills"
            assert link.resolve() == target, (
                f"{link.relative_to(initted_project)} must resolve to "
                f".opencode/skills, got {link.resolve()}"
            )

    def test_commands_symlink_resolves_to_opencode(self, initted_project: Path) -> None:
        target = (initted_project / ".opencode" / "commands").resolve()
        for p in _personalities(initted_project):
            link = p / "commands"
            assert link.resolve() == target

    def test_opencode_command_files_are_regular_not_symlink(
        self, initted_project: Path,
    ) -> None:
        """Capability writers go straight to ``.opencode/``; the files
        there are real, not downward symlinks to per-instance copies."""
        opencode_commands = initted_project / ".opencode" / "commands"
        assert opencode_commands.is_dir()
        for cmd in opencode_commands.iterdir():
            if cmd.is_dir():
                continue
            assert not cmd.is_symlink(), (
                f"{cmd.relative_to(initted_project)} is a symlink — "
                f"capability templates should write directly to .opencode/."
            )

    def test_opencode_skill_files_are_regular_not_symlink(
        self, initted_project: Path,
    ) -> None:
        opencode_skills = initted_project / ".opencode" / "skills"
        if not opencode_skills.exists():
            pytest.skip("project has no skills (none was emitted)")
        for entry in opencode_skills.rglob("*"):
            if entry.is_file():
                assert not entry.is_symlink(), (
                    f"{entry.relative_to(initted_project)} is a symlink — "
                    f"skills should be written directly to .opencode/skills/."
                )

    def test_no_per_instance_command_files(self, initted_project: Path) -> None:
        """No personality holds its own ``commands/`` real directory.

        After commit 5 each personality's ``commands`` IS the upward
        symlink, not a real subdirectory full of stale copies.
        """
        for p in _personalities(initted_project):
            cmds = p / "commands"
            # The symlink itself is fine; what we forbid is a real dir
            # filled with per-instance copies.
            if cmds.is_symlink():
                continue
            if cmds.exists():
                concrete = list(cmds.iterdir())
                assert not concrete, (
                    f"{cmds.relative_to(initted_project)} is a real "
                    f"directory with files {[c.name for c in concrete]}; "
                    f"after commit 5 it must be the upward symlink."
                )
