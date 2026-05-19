"""``allmight reconcile`` — register orphan personalities.

A personality directory under ``personalities/<name>/`` becomes
"orphaned" when it exists on disk but is absent from
``.allmight/personalities.yaml`` (copied in from another project,
restored from ``memory-history``, or created out-of-band). The
``reconcile`` CLI scans for these dirs, infers capabilities from
subdir presence, and registers them.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from allmight.cli import main
from allmight.core.personalities import (
    OrphanPersonality,
    detect_orphan_personalities,
    read_registry,
    register_orphans,
)


def _invoke_in(root: Path, args: list[str]):
    """Run the CLI as if cwd were ``root`` (mirrors test_personality_add_list)."""
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


def _make_orphan(
    project: Path,
    name: str,
    *,
    with_role_md: bool = True,
    capabilities: tuple[str, ...] = ("database", "memory"),
) -> Path:
    """Drop a personality directory directly on disk, bypassing ``allmight add``.

    This is the situation reconcile is designed to handle: someone
    placed a personality folder there without going through the CLI.
    """
    p = project / "personalities" / name
    p.mkdir(parents=True, exist_ok=True)
    if with_role_md:
        (p / "ROLE.md").write_text(
            f"# {name}\n\nThe {name} role helps with miscellaneous tasks.\n"
        )
    for cap in capabilities:
        (p / cap).mkdir(exist_ok=True)
    return p


class TestDetectOrphans:
    def test_no_orphans_when_dir_empty(self, initted_project: Path) -> None:
        assert detect_orphan_personalities(initted_project) == []

    def test_detects_orphan_with_role_and_both_capabilities(
        self, initted_project: Path
    ) -> None:
        _make_orphan(initted_project, "stdcell_owner")
        orphans = detect_orphan_personalities(initted_project)
        assert len(orphans) == 1
        assert orphans[0].name == "stdcell_owner"
        assert orphans[0].capabilities == ["database", "memory"]
        assert orphans[0].has_role_md is True

    def test_detects_partial_capabilities(self, initted_project: Path) -> None:
        _make_orphan(
            initted_project, "reviewer", capabilities=("memory",)
        )
        orphans = detect_orphan_personalities(initted_project)
        assert orphans[0].capabilities == ["memory"]

    def test_flags_orphan_missing_role_md(self, initted_project: Path) -> None:
        _make_orphan(initted_project, "halfbaked", with_role_md=False)
        orphans = detect_orphan_personalities(initted_project)
        assert len(orphans) == 1
        assert orphans[0].has_role_md is False

    def test_flags_orphan_with_no_capability_subdirs(
        self, initted_project: Path
    ) -> None:
        _make_orphan(initted_project, "shell", capabilities=())
        orphans = detect_orphan_personalities(initted_project)
        assert orphans[0].capabilities == []
        assert orphans[0].has_role_md is True

    def test_registered_personality_not_reported(
        self, initted_project: Path
    ) -> None:
        # First add via CLI so it lands in the registry.
        result = _invoke_in(
            initted_project,
            ["add", "primary", "--capabilities", "database,memory"],
        )
        assert result.exit_code == 0
        # Then drop another directly on disk.
        _make_orphan(initted_project, "secondary")
        orphans = detect_orphan_personalities(initted_project)
        names = [o.name for o in orphans]
        assert "primary" not in names
        assert "secondary" in names

    def test_dotfiles_ignored(self, initted_project: Path) -> None:
        (initted_project / "personalities" / ".scratch").mkdir(parents=True)
        assert detect_orphan_personalities(initted_project) == []

    def test_symlinked_dir_ignored(self, initted_project: Path) -> None:
        target = initted_project / "elsewhere"
        target.mkdir()
        (initted_project / "personalities").mkdir(exist_ok=True)
        (initted_project / "personalities" / "linked").symlink_to(target)
        assert detect_orphan_personalities(initted_project) == []


class TestRegisterOrphans:
    def test_writes_registry(self, initted_project: Path) -> None:
        _make_orphan(initted_project, "stdcell_owner")
        orphans = detect_orphan_personalities(initted_project)
        register_orphans(initted_project, orphans)

        registry = read_registry(initted_project)
        assert any(
            e.instance == "stdcell_owner" and set(e.capabilities) == {"database", "memory"}
            for e in registry
        )

    def test_versions_populated_from_templates(self, initted_project: Path) -> None:
        _make_orphan(initted_project, "reviewer", capabilities=("memory",))
        orphans = detect_orphan_personalities(initted_project)
        register_orphans(initted_project, orphans)

        registry = read_registry(initted_project)
        reviewer = next(e for e in registry if e.instance == "reviewer")
        assert reviewer.versions.get("memory")  # non-empty version string

    def test_preserves_existing_entries(self, initted_project: Path) -> None:
        _invoke_in(initted_project, ["add", "alpha", "--capabilities", "memory"])
        _make_orphan(initted_project, "beta")
        orphans = detect_orphan_personalities(initted_project)
        register_orphans(initted_project, orphans)

        names = {e.instance for e in read_registry(initted_project)}
        assert names == {"alpha", "beta"}


class TestCliReconcile:
    def test_no_orphans_message(self, initted_project: Path) -> None:
        result = _invoke_in(initted_project, ["reconcile"])
        assert result.exit_code == 0
        assert "in sync with disk" in result.output

    def test_dry_run_default_does_not_write(self, initted_project: Path) -> None:
        _make_orphan(initted_project, "stdcell_owner")
        result = _invoke_in(initted_project, ["reconcile"])
        assert result.exit_code == 0
        assert "stdcell_owner" in result.output
        assert "Dry run" in result.output
        # Registry must remain untouched.
        assert read_registry(initted_project) == []

    def test_yes_writes_registry(self, initted_project: Path) -> None:
        _make_orphan(initted_project, "stdcell_owner")
        result = _invoke_in(initted_project, ["reconcile", "--yes"])
        assert result.exit_code == 0
        assert "Registered" in result.output

        names = {e.instance for e in read_registry(initted_project)}
        assert "stdcell_owner" in names

    def test_yes_recomposes_agents_md(self, initted_project: Path) -> None:
        _make_orphan(initted_project, "stdcell_owner")
        _invoke_in(initted_project, ["reconcile", "--yes"])

        agents_md = (initted_project / "AGENTS.md").read_text()
        assert "stdcell_owner" in agents_md

    def test_yes_creates_opencode_agent_file(self, initted_project: Path) -> None:
        _make_orphan(initted_project, "stdcell_owner")
        _invoke_in(initted_project, ["reconcile", "--yes"])

        agent_file = initted_project / ".opencode" / "agents" / "stdcell_owner.md"
        assert agent_file.is_file()
        content = agent_file.read_text()
        assert "mode: subagent" in content
        assert "ROLE.md" in content

    def test_skips_orphan_missing_role_md(self, initted_project: Path) -> None:
        _make_orphan(initted_project, "halfbaked", with_role_md=False)
        result = _invoke_in(initted_project, ["reconcile", "--yes"])
        assert result.exit_code == 0
        assert "missing ROLE.md" in result.output
        # Not registered.
        assert read_registry(initted_project) == []

    def test_skips_orphan_with_no_capabilities(self, initted_project: Path) -> None:
        _make_orphan(initted_project, "shell", capabilities=())
        result = _invoke_in(initted_project, ["reconcile", "--yes"])
        assert result.exit_code == 0
        assert "no capability subdirs" in result.output
        assert read_registry(initted_project) == []

    def test_mixed_actionable_and_skipped(self, initted_project: Path) -> None:
        _make_orphan(initted_project, "good")
        _make_orphan(initted_project, "bad", with_role_md=False)
        result = _invoke_in(initted_project, ["reconcile", "--yes"])
        assert result.exit_code == 0

        names = {e.instance for e in read_registry(initted_project)}
        assert "good" in names
        assert "bad" not in names

    def test_fails_outside_project(self, tmp_path: Path) -> None:
        result = _invoke_in(tmp_path, ["reconcile"])
        assert result.exit_code != 0
        assert "not an All-Might project" in result.output


class TestSyncSkillMentionsReconcile:
    """The /sync skill must teach the agent about the reconcile flow,
    otherwise users discover orphan personalities the hard way."""

    def test_skill_mentions_reconcile_command(self, initted_project: Path) -> None:
        # Re-init triggers /sync skill generation.
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(initted_project)])
        skill = initted_project / ".opencode" / "skills" / "sync" / "SKILL.md"
        content = skill.read_text()
        assert "allmight reconcile" in content
        assert "orphan" in content.lower()
