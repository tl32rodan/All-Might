"""``allmight add`` / ``allmight list`` — flat personality lifecycle CLI.

Part-D commit 6 contract: a flat (no ``personality`` subgroup)
surface for managing personality instances inside an existing
All-Might project. The CLI operates on the current working
directory, validates that it is an All-Might project, and
delegates real work to the same ``InstallContext`` /
``PersonalityTemplate.install`` plumbing that ``allmight init``
uses.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from allmight.cli import main


def _invoke_in(root: Path, args: list[str]):
    """Invoke CLI as if cwd were ``root``.

    CliRunner has no built-in cwd option, so we ``os.chdir`` for the
    duration of the call. ``catch_exceptions=False`` surfaces real
    tracebacks for debugging.
    """
    runner = CliRunner()
    cwd = os.getcwd()
    try:
        os.chdir(root)
        return runner.invoke(main, args, catch_exceptions=False)
    finally:
        os.chdir(cwd)


@pytest.fixture
def initted_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--yes", str(tmp_path)])
    assert result.exit_code == 0, result.output
    return tmp_path


class TestAddCreatesPersonality:
    def test_creates_personality_dir(self, initted_project: Path) -> None:
        result = _invoke_in(
            initted_project,
            ["add", "stdcell_owner", "--capabilities", "database,memory"],
        )
        assert result.exit_code == 0, result.output
        p = initted_project / "personalities" / "stdcell_owner"
        assert p.is_dir()
        assert (p / "database").is_dir()
        assert (p / "memory").is_dir()
        assert (p / "ROLE.md").is_file()

    def test_creates_real_empty_command_skill_dirs(self, initted_project: Path) -> None:
        """Per commit 5: each personality gets real empty
        ``commands/`` and ``skills/`` slots for personality-specific
        entries."""
        _invoke_in(
            initted_project,
            ["add", "stdcell_owner", "--capabilities", "database,memory"],
        )
        p = initted_project / "personalities" / "stdcell_owner"
        for kind in ("commands", "skills"):
            d = p / kind
            assert d.is_dir() and not d.is_symlink(), (
                f"{d.relative_to(initted_project)} must be a real, "
                f"non-symlinked, initially empty dir."
            )
            assert list(d.iterdir()) == []


class TestAddCapabilitySelection:
    def test_subset_only_creates_chosen_capabilities(
        self, initted_project: Path,
    ) -> None:
        result = _invoke_in(
            initted_project,
            ["add", "code_reviewer", "--capabilities", "memory"],
        )
        assert result.exit_code == 0, result.output
        p = initted_project / "personalities" / "code_reviewer"
        assert (p / "memory").is_dir()
        assert not (p / "database").exists()

    def test_default_capabilities_includes_all(self, initted_project: Path) -> None:
        """Without ``--capabilities``, install every discoverable capability."""
        result = _invoke_in(initted_project, ["add", "general"])
        assert result.exit_code == 0, result.output
        p = initted_project / "personalities" / "general"
        assert (p / "database").is_dir()
        assert (p / "memory").is_dir()

    def test_unknown_capability_errors(self, initted_project: Path) -> None:
        result = _invoke_in(
            initted_project,
            ["add", "xxx", "--capabilities", "nonexistent"],
        )
        assert result.exit_code != 0
        joined = result.output.lower() + (result.stderr or "").lower()
        assert "nonexistent" in joined or "unknown" in joined


class TestAddRegistry:
    def test_appends_row_to_personalities_yaml(self, initted_project: Path) -> None:
        _invoke_in(
            initted_project,
            ["add", "stdcell_owner", "--capabilities", "database,memory"],
        )
        registry = yaml.safe_load(
            (initted_project / ".allmight" / "personalities.yaml").read_text()
        )
        names = [row.get("name") or row.get("instance") for row in registry["personalities"]]
        assert "stdcell_owner" in names

    def test_part_d_row_has_capabilities_list(self, initted_project: Path) -> None:
        _invoke_in(
            initted_project,
            ["add", "code_reviewer", "--capabilities", "memory"],
        )
        registry = yaml.safe_load(
            (initted_project / ".allmight" / "personalities.yaml").read_text()
        )
        rows = [r for r in registry["personalities"] if (r.get("name") or r.get("instance")) == "code_reviewer"]
        assert len(rows) == 1
        row = rows[0]
        assert row.get("capabilities") == ["memory"]


class TestAddGuards:
    def test_duplicate_name_without_force_errors(self, initted_project: Path) -> None:
        first = _invoke_in(
            initted_project,
            ["add", "stdcell_owner", "--capabilities", "memory"],
        )
        assert first.exit_code == 0
        second = _invoke_in(
            initted_project,
            ["add", "stdcell_owner", "--capabilities", "memory"],
        )
        assert second.exit_code != 0

    def test_outside_allmight_project_errors(self, tmp_path: Path) -> None:
        result = _invoke_in(tmp_path, ["add", "x", "--capabilities", "memory"])
        assert result.exit_code != 0


class TestListCommand:
    def test_lists_default_init_personality(self, initted_project: Path) -> None:
        """Per commit 7, ``allmight init --yes`` creates ONE personality
        named after the project-root dir, with all capabilities."""
        result = _invoke_in(initted_project, ["list"])
        assert result.exit_code == 0, result.output
        assert initted_project.name in result.output
        # And the row should mention both default capabilities.
        assert "database" in result.output
        assert "memory" in result.output

    def test_lists_newly_added_personality(self, initted_project: Path) -> None:
        _invoke_in(
            initted_project,
            ["add", "stdcell_owner", "--capabilities", "database,memory"],
        )
        result = _invoke_in(initted_project, ["list"])
        assert result.exit_code == 0
        assert "stdcell_owner" in result.output
        # And the capability list should be visible.
        assert "database" in result.output
        assert "memory" in result.output

    def test_outside_allmight_project_errors(self, tmp_path: Path) -> None:
        result = _invoke_in(tmp_path, ["list"])
        assert result.exit_code != 0
