"""``allmight init`` on a populated project must preserve the registry.

Regression test for the recurring "init wipes ``personalities.yaml``"
bug: every re-init (the documented way to pick up framework updates)
used to overwrite ``.allmight/personalities.yaml`` with an empty
list and re-compose ``AGENTS.md`` with no personality sections.

The fix in ``_init_callback`` distinguishes:

- Fresh init (no ``.allmight/``) and ``--force`` re-init → empty
  registry, empty AGENTS.md (today's documented behaviour for the
  "wipe everything" escape hatch).
- Re-init on a project with rows in ``personalities.yaml`` →
  preserve registry, recompose AGENTS.md from the existing rows,
  refresh the ``.opencode/agents/<name>.md`` subagent files.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
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
def populated_project(tmp_path: Path) -> Path:
    """Project that has been ``init``-ed and has one personality added."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")

    r = CliRunner().invoke(main, ["init", "--yes", str(tmp_path)])
    assert r.exit_code == 0, r.output

    r = _invoke_in(
        tmp_path, ["add", "stdcell_owner", "--capabilities", "database,memory"],
    )
    assert r.exit_code == 0, r.output

    # Sanity: the registry has the row before we test re-init.
    registry = yaml.safe_load(
        (tmp_path / ".allmight" / "personalities.yaml").read_text()
    )
    names = [row.get("name") or row.get("instance") for row in registry["personalities"]]
    assert "stdcell_owner" in names

    return tmp_path


class TestReinitPreservesRegistry:
    """Re-init without ``--force`` must NOT wipe ``personalities.yaml``."""

    def test_registry_row_survives_reinit(self, populated_project: Path) -> None:
        r = _invoke_in(populated_project, ["init"])
        assert r.exit_code == 0, r.output

        registry = yaml.safe_load(
            (populated_project / ".allmight" / "personalities.yaml").read_text()
        )
        names = [
            row.get("name") or row.get("instance")
            for row in registry["personalities"]
        ]
        assert "stdcell_owner" in names

    def test_summary_message_reports_preservation(
        self, populated_project: Path,
    ) -> None:
        r = _invoke_in(populated_project, ["init"])
        assert r.exit_code == 0, r.output
        assert "Preserved" in r.output
        assert "personality row" in r.output

    def test_agents_md_includes_personality_section(
        self, populated_project: Path,
    ) -> None:
        """After re-init, AGENTS.md must still contain the personality's
        ROLE.md prose (composed in via compose_agents_md), not just the
        framework primer."""
        _invoke_in(populated_project, ["init"])
        agents_md = (populated_project / "AGENTS.md").read_text()
        # The composed-in personality section header lives below the
        # framework primer. We assert the header exists; we don't pin
        # the exact prose because ROLE.md content evolves.
        assert "stdcell_owner" in agents_md, (
            "AGENTS.md must contain the personality name somewhere — "
            "either as a section header or via the composed ROLE.md."
        )

    def test_opencode_agents_file_refreshed(self, populated_project: Path) -> None:
        """compose_role_agents must run on re-init so the subagent
        pointer file exists/refreshes with the current ROLE.md."""
        agent_file = (
            populated_project / ".opencode" / "agents" / "stdcell_owner.md"
        )
        # `add` already wrote it; assert it still exists after re-init.
        assert agent_file.is_file()
        original_bytes = agent_file.read_bytes()

        r = _invoke_in(populated_project, ["init"])
        assert r.exit_code == 0, r.output

        assert agent_file.is_file(), (
            ".opencode/agents/<name>.md must still exist after re-init."
        )
        # Content is deterministic (frontmatter + marker comment),
        # so re-writing the same content is fine. The point is the
        # file isn't deleted nor left stale-pointing at a non-existent
        # ROLE.md.
        assert b"stdcell_owner" in agent_file.read_bytes()

    def test_reinit_does_not_remove_personalities_dir(
        self, populated_project: Path,
    ) -> None:
        """The personality's directory on disk must not be touched
        by re-init — only registry-level preservation is in scope."""
        _invoke_in(populated_project, ["init"])
        p = populated_project / "personalities" / "stdcell_owner"
        assert p.is_dir()
        assert (p / "ROLE.md").is_file()


class TestReinitForceStillWipes:
    """``allmight init --force`` is the explicit "overwrite everything"
    path. It still empties the registry — this is by design."""

    def test_force_wipes_registry(self, populated_project: Path) -> None:
        r = _invoke_in(populated_project, ["init", "--force"])
        assert r.exit_code == 0, r.output
        registry = yaml.safe_load(
            (populated_project / ".allmight" / "personalities.yaml").read_text()
        )
        assert registry["personalities"] == []


class TestFreshInitUnchanged:
    """Fresh init (no existing ``.allmight/``) still produces an empty
    registry; this test guards against a regression where the
    preservation path accidentally fires on a brand-new project."""

    def test_fresh_init_writes_empty_registry(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")

        r = CliRunner().invoke(main, ["init", "--yes", str(tmp_path)])
        assert r.exit_code == 0, r.output

        registry = yaml.safe_load(
            (tmp_path / ".allmight" / "personalities.yaml").read_text()
        )
        assert registry["personalities"] == []
        assert "Preserved" not in r.output  # no preservation message on fresh
