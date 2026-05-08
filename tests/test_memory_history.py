"""Memory version-control mirror at ``.allmight/memory-history/``.

Tests the round-trip the user actually cares about: edit memory data,
auto-snapshot, accidentally delete, restore from history. Plus the
hooks/plugins exist and the CLI subcommands are wired.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from allmight.cli import main
from allmight.capabilities.memory.history import (
    HISTORY_REL,
    TRACKED_GLOBS,
    MemoryHistory,
)


def _invoke_in(root: Path, args: list[str]):
    runner = CliRunner()
    cwd = os.getcwd()
    try:
        os.chdir(root)
        return runner.invoke(main, args, catch_exceptions=False)
    finally:
        os.chdir(cwd)


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_AUTHOR_NAME", "all-might-test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "all-might-test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "all-might-test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "all-might-test@example.com")


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


# ----------------------------------------------------------------------
# Mirror initialisation
# ----------------------------------------------------------------------


class TestInit:
    def test_history_dir_created_at_init(self, initted_project: Path) -> None:
        history = initted_project / HISTORY_REL
        assert history.is_dir()
        assert (history / ".git").is_dir()
        # Default branch is main.
        head = (history / ".git" / "HEAD").read_text()
        assert "refs/heads/main" in head

    def test_init_seeds_first_commit(self, initted_project: Path) -> None:
        """Init runs sync + commit so the user has a baseline to
        restore back to even before they edit anything."""
        history = MemoryHistory()
        records = history.log(initted_project)
        assert records, "expected at least one initial commit"
        assert records[-1].subject.startswith("init:")

    def test_gitignore_excludes_store(self, initted_project: Path) -> None:
        gitignore = (initted_project / HISTORY_REL / ".gitignore").read_text()
        assert "store/" in gitignore

    def test_init_idempotent(self, initted_project: Path) -> None:
        """Calling init again on an already-init'd project must not
        fail or duplicate the .git tree."""
        history = MemoryHistory()
        history.init(initted_project)  # second call
        assert (initted_project / HISTORY_REL / ".git").is_dir()


# ----------------------------------------------------------------------
# Sync — copy live tree into mirror
# ----------------------------------------------------------------------


class TestSync:
    def test_sync_picks_up_new_understanding_file(
        self, initted_project: Path, tmp_path: Path,
    ) -> None:
        # init creates a personality with a memory dir; add a file.
        understanding = (
            initted_project / "personalities" / "demo"
            / "memory" / "understanding"
        )
        understanding.mkdir(parents=True, exist_ok=True)
        (understanding / "topic.md").write_text(
            "# topic\nFresh notes.\n"
        )
        history = MemoryHistory()
        changes = history.sync(initted_project)
        rel = "personalities/demo/memory/understanding/topic.md"
        assert any(c[0] == rel and c[1] in ("create", "update") for c in changes)
        # Mirror tree mirrors live layout.
        mirror_path = initted_project / HISTORY_REL / rel
        assert mirror_path.exists()
        assert mirror_path.read_text() == "# topic\nFresh notes.\n"

    def test_sync_excludes_store_dir(self, initted_project: Path) -> None:
        """``store/`` is rebuildable derived data — never mirrored."""
        store = (
            initted_project / "personalities" / "demo"
            / "memory" / "store"
        )
        store.mkdir(parents=True, exist_ok=True)
        (store / "vectors.bin").write_text("BINARY-DATA")
        history = MemoryHistory()
        history.sync(initted_project)
        # The mirror tree should not contain store/ files.
        mirror = initted_project / HISTORY_REL
        store_in_mirror = list(mirror.rglob("store/vectors.bin"))
        assert not store_in_mirror, (
            f"store/ should be excluded from the mirror, found: {store_in_mirror}"
        )

    def test_sync_propagates_deletion(self, initted_project: Path) -> None:
        understanding = (
            initted_project / "personalities" / "demo"
            / "memory" / "understanding"
        )
        understanding.mkdir(parents=True, exist_ok=True)
        f = understanding / "delete-me.md"
        f.write_text("body\n")
        history = MemoryHistory()
        history.sync(initted_project)
        history.commit(initted_project, "test: add file")

        f.unlink()
        changes = history.sync(initted_project)
        rel = "personalities/demo/memory/understanding/delete-me.md"
        assert (rel, "delete") in changes
        # Mirror file gone too.
        assert not (initted_project / HISTORY_REL / rel).exists()


# ----------------------------------------------------------------------
# Commit + log
# ----------------------------------------------------------------------


class TestCommit:
    def test_commit_returns_sha_when_changed(
        self, initted_project: Path,
    ) -> None:
        memory_md = initted_project / "MEMORY.md"
        memory_md.write_text(memory_md.read_text() + "\n# Edit\n")
        history = MemoryHistory()
        history.sync(initted_project)
        sha = history.commit(initted_project, "test: edit MEMORY.md")
        assert sha and len(sha) >= 12
        # log shows it.
        records = history.log(initted_project)
        assert records[0].sha == sha
        assert "edit MEMORY.md" in records[0].subject

    def test_commit_returns_none_when_nothing_changed(
        self, initted_project: Path,
    ) -> None:
        history = MemoryHistory()
        history.sync(initted_project)  # no live drift
        sha = history.commit(initted_project, "test: should be no-op")
        assert sha is None

    def test_snapshot_high_level_helper(
        self, initted_project: Path,
    ) -> None:
        memory_md = initted_project / "MEMORY.md"
        memory_md.write_text(memory_md.read_text() + "\n# More\n")
        history = MemoryHistory()
        sha = history.snapshot(
            initted_project, trigger="chat-message", session_id="abc",
        )
        assert sha
        records = history.log(initted_project, n=1)
        assert "chat-message" in records[0].subject or any(
            "chat-message" in line
            for line in history.diff(initted_project, sha).splitlines()
        )


# ----------------------------------------------------------------------
# Restore — the user's actual recovery use case
# ----------------------------------------------------------------------


class TestRestore:
    def test_restore_round_trip_recovers_deleted_file(
        self, initted_project: Path,
    ) -> None:
        """User edits a memory file, snapshots, then accidentally
        deletes — restore brings it back byte-for-byte."""
        understanding = (
            initted_project / "personalities" / "demo"
            / "memory" / "understanding"
        )
        understanding.mkdir(parents=True, exist_ok=True)
        topic = understanding / "stdcell.md"
        topic.write_text("# stdcell\nKey insight.\n")
        history = MemoryHistory()
        history.snapshot(initted_project, trigger="manual")

        # User's "oops" moment.
        topic.unlink()
        assert not topic.exists()
        history.snapshot(initted_project, trigger="manual")  # records delete

        # Restore from one commit before the delete (HEAD~1).
        out = history.restore(
            initted_project,
            "personalities/demo/memory/understanding/stdcell.md",
            rev="HEAD~1",
        )
        assert out == topic
        assert topic.read_text() == "# stdcell\nKey insight.\n"

    def test_restore_to_alternate_destination(
        self, initted_project: Path, tmp_path: Path,
    ) -> None:
        """``--to`` lands the restored content at a different path —
        useful for inspecting an old version without clobbering the
        live tree."""
        memory_md = initted_project / "MEMORY.md"
        original = memory_md.read_text()
        memory_md.write_text(original + "\n# After-edit\n")
        history = MemoryHistory()
        history.snapshot(initted_project, trigger="manual")

        sandbox = tmp_path / "old-version.md"
        out = history.restore(
            initted_project, "MEMORY.md",
            rev="HEAD~1", dest=sandbox,
        )
        assert out == sandbox
        assert sandbox.read_text() == original
        # Live file untouched by the restore.
        assert "After-edit" in memory_md.read_text()


# ----------------------------------------------------------------------
# CLI surface
# ----------------------------------------------------------------------


class TestMemoryCli:
    def test_snapshot_command_runs(self, initted_project: Path) -> None:
        memory_md = initted_project / "MEMORY.md"
        memory_md.write_text(memory_md.read_text() + "\n# CLI test\n")
        result = _invoke_in(
            initted_project, ["memory", "snapshot", "-m", "from-cli"],
        )
        assert result.exit_code == 0, result.output
        assert "Snapshot:" in result.output

    def test_snapshot_no_op_when_clean(
        self, initted_project: Path,
    ) -> None:
        # Drain any lingering drift first.
        _invoke_in(initted_project, ["memory", "snapshot", "-m", "drain"])
        result = _invoke_in(
            initted_project, ["memory", "snapshot", "-m", "second"],
        )
        assert result.exit_code == 0, result.output
        assert "No changes" in result.output

    def test_log_command(self, initted_project: Path) -> None:
        result = _invoke_in(initted_project, ["memory", "log"])
        assert result.exit_code == 0, result.output
        # Init seeded a commit; expect a SHA-shaped token.
        assert re.search(r"[0-9a-f]{12}", result.output)

    def test_log_with_personality_filter(
        self, initted_project: Path,
    ) -> None:
        result = _invoke_in(
            initted_project,
            ["memory", "log", "--personality", "demo"],
        )
        assert result.exit_code == 0, result.output

    def test_restore_round_trip_via_cli(
        self, initted_project: Path,
    ) -> None:
        understanding = (
            initted_project / "personalities" / "demo"
            / "memory" / "understanding"
        )
        understanding.mkdir(parents=True, exist_ok=True)
        topic = understanding / "stdcell.md"
        topic.write_text("# Original\n")
        _invoke_in(initted_project, ["memory", "snapshot", "-m", "first"])

        topic.unlink()
        _invoke_in(initted_project, ["memory", "snapshot", "-m", "deleted"])

        rel = "personalities/demo/memory/understanding/stdcell.md"
        result = _invoke_in(
            initted_project,
            ["memory", "restore", rel, "--rev", "HEAD~1", "--yes"],
        )
        assert result.exit_code == 0, result.output
        assert topic.read_text() == "# Original\n"

    def test_diff_command(self, initted_project: Path) -> None:
        memory_md = initted_project / "MEMORY.md"
        memory_md.write_text(memory_md.read_text() + "\n# diff test\n")
        _invoke_in(initted_project, ["memory", "snapshot", "-m", "for-diff"])
        # Get the most recent sha via log.
        log = _invoke_in(initted_project, ["memory", "log", "-n", "1"])
        sha = log.output.split()[0]
        result = _invoke_in(
            initted_project, ["memory", "diff", sha],
        )
        assert result.exit_code == 0, result.output
        assert "diff test" in result.output

    def test_gc_command(self, initted_project: Path) -> None:
        result = _invoke_in(initted_project, ["memory", "gc"])
        assert result.exit_code == 0, result.output
        assert "gc complete" in result.output


# ----------------------------------------------------------------------
# Plugin / hook content (dual-platform contract)
# ----------------------------------------------------------------------


class TestPluginAndHook:
    def test_opencode_plugin_present_after_init(
        self, initted_project: Path,
    ) -> None:
        plugin = (
            initted_project / ".opencode" / "plugins" / "memory-history.ts"
        )
        assert plugin.is_file()
        body = plugin.read_text()
        # Every documented hook must be wired.
        for hook in (
            '"chat.message"',
            '"experimental.session.compacting"',
            '"session.deleted"',
        ):
            assert hook in body, f"plugin missing {hook}"
        # The CLI it spawns is what the user can also run by hand.
        assert 'allmight' in body
        assert 'memory' in body and 'snapshot' in body

    def test_claude_hook_present_after_init(
        self, initted_project: Path,
    ) -> None:
        hook = (
            initted_project / ".claude" / "hooks" / "memory_history.py"
        )
        assert hook.is_file()
        # Executable bit set so Claude Code can run it.
        assert os.access(hook, os.X_OK)

    def test_claude_settings_registers_stop_hook(
        self, initted_project: Path,
    ) -> None:
        import json
        settings = json.loads(
            (initted_project / ".claude" / "settings.json").read_text()
        )
        hooks = settings.get("hooks", {})
        stop_blocks = hooks.get("Stop") or []
        commands = [
            h.get("command", "")
            for block in stop_blocks
            for h in block.get("hooks", [])
        ]
        assert any(
            "memory_history.py" in cmd for cmd in commands
        ), f"expected memory_history.py in Stop hooks, got: {commands}"

    def test_claude_hook_runs_cleanly(
        self, initted_project: Path,
    ) -> None:
        """End-to-end: feed the hook a stub stdin, verify it exits 0
        and emits the empty-output JSON shape Claude Code expects."""
        hook = (
            initted_project / ".claude" / "hooks" / "memory_history.py"
        )
        proc = subprocess.run(
            ["python3", str(hook)],
            input='{"cwd": "%s", "session_id": "test"}' % initted_project,
            capture_output=True, text=True, timeout=10,
        )
        assert proc.returncode == 0, proc.stderr
        # Hook must emit valid JSON (Claude Code's contract).
        import json
        parsed = json.loads(proc.stdout)
        assert isinstance(parsed, dict)


# ----------------------------------------------------------------------
# Tracked-glob coverage
# ----------------------------------------------------------------------


class TestTrackedGlobs:
    def test_tracked_globs_cover_l1_l2_l3(self) -> None:
        joined = " ".join(TRACKED_GLOBS)
        assert "MEMORY.md" in joined  # L1
        assert "memory/understanding" in joined  # L2
        assert "memory/journal" in joined  # L3

    def test_tracked_globs_exclude_store(self) -> None:
        for pat in TRACKED_GLOBS:
            assert "store/" not in pat, (
                f"glob {pat!r} would pull in derived SMAK index data"
            )
