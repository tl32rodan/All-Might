"""Orphan personality reconciliation via ``/sync`` skill + ``allmight add --force``.

A personality directory under ``personalities/<name>/`` becomes
"orphaned" when it exists on disk but is absent from
``.allmight/personalities.yaml`` (copied in from another project,
restored from ``memory-history``, or created out-of-band).

There is **no dedicated reconcile CLI**. The ``/sync`` skill teaches
the agent to discover orphans via shell, then call
``allmight add --force --capabilities ... <name>`` per orphan. The
existing ``add`` path is intentionally incremental on populated dirs
(ROLE.md and memory data are write-once guarded), so re-running it
on an orphan registers the personality without clobbering user
content.

These tests pin:

1. The ``/sync`` skill body actually teaches this flow.
2. ``allmight add --force`` is incremental-safe on a pre-populated
   orphan dir — the contract the skill body relies on.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from allmight.cli import main
from allmight.core.personalities import read_registry


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
    role_md_body: str = "",
    journal_entries: dict[str, str] | None = None,
    understanding_entries: dict[str, str] | None = None,
    capabilities: tuple[str, ...] = ("database", "memory"),
) -> Path:
    """Drop a populated personality directory directly on disk.

    Bypasses ``allmight add``. Simulates the "copied in from another
    project" / "restored from memory-history" scenario.
    """
    p = project / "personalities" / name
    p.mkdir(parents=True, exist_ok=True)
    (p / "ROLE.md").write_text(
        role_md_body or f"# {name}\n\nThe {name} role handles its own thing.\n"
    )
    for cap in capabilities:
        (p / cap).mkdir(exist_ok=True)
    if journal_entries and "memory" in capabilities:
        journal = p / "memory" / "journal"
        journal.mkdir(parents=True, exist_ok=True)
        for fname, body in journal_entries.items():
            (journal / fname).write_text(body)
    if understanding_entries and "memory" in capabilities:
        understanding = p / "memory" / "understanding"
        understanding.mkdir(parents=True, exist_ok=True)
        for fname, body in understanding_entries.items():
            (understanding / fname).write_text(body)
    return p


# ---------------------------------------------------------------------
# 1. The /sync skill body teaches the reconciliation flow.
# ---------------------------------------------------------------------


class TestSyncSkillTeachesReconciliation:
    """The skill body is the only place that documents the orphan flow."""

    def test_skill_mentions_orphan_section(self, initted_project: Path) -> None:
        # Re-init triggers /sync skill generation.
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(initted_project)])
        skill = initted_project / ".opencode" / "skills" / "sync" / "SKILL.md"
        content = skill.read_text()
        assert "Orphan personality reconciliation" in content

    def test_skill_uses_add_force_not_invented_command(
        self, initted_project: Path
    ) -> None:
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(initted_project)])
        content = (
            initted_project / ".opencode" / "skills" / "sync" / "SKILL.md"
        ).read_text()
        assert "allmight add --force" in content
        # No invented sibling command — sync reuses the existing
        # registration path.
        assert "allmight reconcile" not in content

    def test_skill_documents_role_md_write_once_guard(
        self, initted_project: Path
    ) -> None:
        """The skill body must explain *why* re-running add is safe,
        otherwise the agent will hesitate on populated orphan dirs."""
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(initted_project)])
        content = (
            initted_project / ".opencode" / "skills" / "sync" / "SKILL.md"
        ).read_text()
        assert "write-once" in content
        assert "ROLE.md" in content

    def test_skill_mentions_memory_snapshot_before_apply(
        self, initted_project: Path
    ) -> None:
        """Agents should snapshot memory before mutating; if a
        capability inference is wrong, the user can `memory restore`."""
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(initted_project)])
        content = (
            initted_project / ".opencode" / "skills" / "sync" / "SKILL.md"
        ).read_text()
        assert "allmight memory snapshot" in content


# ---------------------------------------------------------------------
# 2. `allmight add --force` is incremental-safe on a populated orphan.
#    This is the contract the skill body relies on. If it ever breaks,
#    the skill's instructions become dangerous, so we pin it here.
# ---------------------------------------------------------------------


class TestAddForceIncrementalOnOrphan:
    def test_orphan_role_md_preserved(self, initted_project: Path) -> None:
        sentinel = "USER WROTE THIS — DO NOT OVERWRITE"
        _make_orphan(
            initted_project,
            "stdcell_owner",
            role_md_body=f"# stdcell_owner\n\n{sentinel}\n",
        )

        result = _invoke_in(
            initted_project,
            ["add", "stdcell_owner", "--capabilities", "database,memory", "--force"],
        )
        assert result.exit_code == 0, result.output

        role = (initted_project / "personalities" / "stdcell_owner" / "ROLE.md").read_text()
        assert sentinel in role

    def test_orphan_memory_journal_preserved(self, initted_project: Path) -> None:
        _make_orphan(
            initted_project,
            "stdcell_owner",
            journal_entries={
                "2026-05-19.md": "# 2026-05-19\n\nLearned about cell library swaps.\n",
            },
        )

        _invoke_in(
            initted_project,
            ["add", "stdcell_owner", "--capabilities", "database,memory", "--force"],
        )

        journal = (
            initted_project / "personalities" / "stdcell_owner"
            / "memory" / "journal" / "2026-05-19.md"
        )
        assert journal.is_file()
        assert "cell library swaps" in journal.read_text()

    def test_orphan_memory_understanding_preserved(
        self, initted_project: Path
    ) -> None:
        _make_orphan(
            initted_project,
            "stdcell_owner",
            understanding_entries={
                "stdcell.md": "# stdcell\n\nNAND2X1 is the canonical 2-input NAND.\n",
            },
        )

        _invoke_in(
            initted_project,
            ["add", "stdcell_owner", "--capabilities", "database,memory", "--force"],
        )

        understanding = (
            initted_project / "personalities" / "stdcell_owner"
            / "memory" / "understanding" / "stdcell.md"
        )
        assert understanding.is_file()
        assert "NAND2X1" in understanding.read_text()

    def test_orphan_gets_registered(self, initted_project: Path) -> None:
        _make_orphan(initted_project, "stdcell_owner")

        _invoke_in(
            initted_project,
            ["add", "stdcell_owner", "--capabilities", "database,memory", "--force"],
        )

        registry = read_registry(initted_project)
        entry = next(e for e in registry if e.instance == "stdcell_owner")
        assert set(entry.capabilities) == {"database", "memory"}

    def test_orphan_gets_agent_file(self, initted_project: Path) -> None:
        _make_orphan(initted_project, "stdcell_owner")

        _invoke_in(
            initted_project,
            ["add", "stdcell_owner", "--capabilities", "database,memory", "--force"],
        )

        agent_file = (
            initted_project / ".opencode" / "agents" / "stdcell_owner.md"
        )
        assert agent_file.is_file()
        content = agent_file.read_text()
        assert "mode: subagent" in content
        assert "ROLE.md" in content

    def test_orphan_appears_in_agents_md(self, initted_project: Path) -> None:
        _make_orphan(initted_project, "stdcell_owner")

        _invoke_in(
            initted_project,
            ["add", "stdcell_owner", "--capabilities", "database,memory", "--force"],
        )

        agents_md = (initted_project / "AGENTS.md").read_text()
        assert "stdcell_owner" in agents_md
