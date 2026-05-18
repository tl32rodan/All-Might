"""Integration + unit tests for L3 SMAK auto-ingest closure (work item C').

Two-half closure:
1. Stop hook (memory-history.ts / memory_history.py) — after the
   snapshot spawn, if any journal file is newer than
   ``.allmight/last_ingest``, touch ``.allmight/ingest.pending``.
2. SessionStart drain (memory-load.ts / memory_load.py) — if
   ``.allmight/ingest.pending`` exists, spawn
   ``allmight memory ingest --incremental`` fire-and-forget.

The CLI subcommand ``allmight memory ingest`` is the canonical
orchestrator: walks ``personalities/*/memory/smak_config.yaml``, runs
``smak ingest`` for each, and on overall success touches
``.allmight/last_ingest`` and removes ``.allmight/ingest.pending``.

See ``docs/plan.md`` work item C' for the rationale (closes the
silent-stale-index bug where ``/recall`` returned outdated results).
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from allmight.cli import main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _invoke_in(root: Path, args: list[str]):
    runner = CliRunner()
    cwd = os.getcwd()
    try:
        os.chdir(root)
        return runner.invoke(main, args, catch_exceptions=False)
    finally:
        os.chdir(cwd)


@pytest.fixture
def initted_with_memory(tmp_path: Path) -> Path:
    """Init project + add one personality with memory capability.

    Result: ``personalities/demo/memory/`` with smak_config.yaml,
    understanding/, journal/, store/.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--yes", str(tmp_path)])
    assert result.exit_code == 0, result.output
    add = _invoke_in(tmp_path, ["add", "demo", "--capabilities", "memory"])
    assert add.exit_code == 0, add.output
    return tmp_path


@pytest.fixture
def fake_smak(tmp_path: Path) -> Path:
    """A standin for the ``smak`` binary that records calls.

    Writes one line per invocation to ``$FAKE_SMAK_LOG`` with the args
    joined by tabs. Exit code is controlled by ``$FAKE_SMAK_FAIL``
    (defaults to 0). Uses the current Python interpreter so we do not
    rely on ``#!`` shebang resolution being identical across CI envs.
    """
    script = tmp_path / "fake_smak.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "log = os.environ.get('FAKE_SMAK_LOG')\n"
        "if log:\n"
        "    with open(log, 'a') as f:\n"
        "        f.write('\\t'.join(sys.argv[1:]) + '\\n')\n"
        "sys.exit(int(os.environ.get('FAKE_SMAK_FAIL') or 0))\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script


def _write_journal_entry(personality_dir: Path, workspace: str, name: str) -> Path:
    """Write a journal entry under ``personalities/<p>/memory/journal/<ws>/``."""
    journal = personality_dir / "memory" / "journal" / workspace
    journal.mkdir(parents=True, exist_ok=True)
    entry = journal / f"{name}.md"
    entry.write_text(f"# {name}\nSeed body.\n")
    return entry


# ===========================================================================
# Unit tests — helper module ``capabilities/memory/ingest.py``
# ===========================================================================

class TestHelperFunctions:
    """Direct unit tests for the orchestration helpers."""

    def test_find_smak_configs_locates_each_personality(self, initted_with_memory: Path) -> None:
        from allmight.capabilities.memory.ingest import find_smak_configs
        configs = find_smak_configs(initted_with_memory)
        assert len(configs) == 1
        assert configs[0].name == "smak_config.yaml"
        assert "personalities/demo/memory" in str(configs[0])

    def test_find_smak_configs_empty_when_no_personalities(self, tmp_path: Path) -> None:
        from allmight.capabilities.memory.ingest import find_smak_configs
        assert find_smak_configs(tmp_path) == []

    def test_journal_has_unindexed_files_true_when_no_last_ingest(
        self, initted_with_memory: Path
    ) -> None:
        from allmight.capabilities.memory.ingest import journal_has_unindexed_files
        _write_journal_entry(
            initted_with_memory / "personalities" / "demo",
            "general", "2026-05-17-seed",
        )
        assert journal_has_unindexed_files(initted_with_memory) is True

    def test_journal_has_unindexed_files_false_when_last_ingest_newer(
        self, initted_with_memory: Path
    ) -> None:
        from allmight.capabilities.memory.ingest import (
            LAST_INGEST_REL, journal_has_unindexed_files,
        )
        _write_journal_entry(
            initted_with_memory / "personalities" / "demo",
            "general", "2026-05-17-seed",
        )
        # Touch last_ingest to NOW; the journal entry is older.
        last_ingest = initted_with_memory / LAST_INGEST_REL
        last_ingest.parent.mkdir(parents=True, exist_ok=True)
        last_ingest.touch()
        time.sleep(0.01)  # ensure mtime resolution captures the touch
        os.utime(last_ingest, None)
        assert journal_has_unindexed_files(initted_with_memory) is False

    def test_journal_has_unindexed_files_true_when_entry_newer_than_last_ingest(
        self, initted_with_memory: Path
    ) -> None:
        from allmight.capabilities.memory.ingest import (
            LAST_INGEST_REL, journal_has_unindexed_files,
        )
        last_ingest = initted_with_memory / LAST_INGEST_REL
        last_ingest.parent.mkdir(parents=True, exist_ok=True)
        last_ingest.touch()
        # Sleep then write — entry mtime > last_ingest mtime.
        time.sleep(0.02)
        _write_journal_entry(
            initted_with_memory / "personalities" / "demo",
            "general", "fresh",
        )
        assert journal_has_unindexed_files(initted_with_memory) is True

    def test_journal_has_unindexed_files_handles_no_personalities(
        self, tmp_path: Path
    ) -> None:
        from allmight.capabilities.memory.ingest import journal_has_unindexed_files
        assert journal_has_unindexed_files(tmp_path) is False

    def test_run_ingest_cycle_invokes_smak_per_personality(
        self, initted_with_memory: Path, fake_smak: Path, tmp_path: Path
    ) -> None:
        from allmight.capabilities.memory.ingest import run_ingest_cycle
        # Second personality with memory.
        add = _invoke_in(initted_with_memory, ["add", "lab", "--capabilities", "memory"])
        assert add.exit_code == 0, add.output

        log = tmp_path / "smak_calls.log"
        os.environ["FAKE_SMAK_LOG"] = str(log)
        try:
            result = run_ingest_cycle(
                initted_with_memory,
                smak_cmd=f"{sys.executable} {fake_smak}",
            )
        finally:
            os.environ.pop("FAKE_SMAK_LOG", None)
            os.environ.pop("FAKE_SMAK_FAIL", None)
        assert result.errors == []
        assert len(result.succeeded) == 2
        calls = log.read_text().strip().splitlines()
        assert len(calls) == 2
        assert all("ingest" in c for c in calls)
        assert all("--incremental" in c for c in calls)

    def test_run_ingest_cycle_touches_last_ingest_on_success(
        self, initted_with_memory: Path, fake_smak: Path
    ) -> None:
        from allmight.capabilities.memory.ingest import (
            LAST_INGEST_REL, run_ingest_cycle,
        )
        result = run_ingest_cycle(
            initted_with_memory,
            smak_cmd=f"{sys.executable} {fake_smak}",
        )
        assert result.errors == []
        assert (initted_with_memory / LAST_INGEST_REL).exists()

    def test_run_ingest_cycle_removes_pending_on_success(
        self, initted_with_memory: Path, fake_smak: Path
    ) -> None:
        from allmight.capabilities.memory.ingest import (
            INGEST_PENDING_REL, run_ingest_cycle,
        )
        pending = initted_with_memory / INGEST_PENDING_REL
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.touch()
        result = run_ingest_cycle(
            initted_with_memory,
            smak_cmd=f"{sys.executable} {fake_smak}",
        )
        assert result.errors == []
        assert not pending.exists()

    def test_run_ingest_cycle_keeps_pending_on_failure(
        self, initted_with_memory: Path, fake_smak: Path
    ) -> None:
        from allmight.capabilities.memory.ingest import (
            INGEST_PENDING_REL, LAST_INGEST_REL, run_ingest_cycle,
        )
        pending = initted_with_memory / INGEST_PENDING_REL
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.touch()

        os.environ["FAKE_SMAK_FAIL"] = "2"
        try:
            result = run_ingest_cycle(
                initted_with_memory,
                smak_cmd=f"{sys.executable} {fake_smak}",
            )
        finally:
            os.environ.pop("FAKE_SMAK_FAIL", None)
        assert result.succeeded == []
        assert len(result.errors) == 1
        assert pending.exists(), "pending should survive smak failure for next retry"
        assert not (initted_with_memory / LAST_INGEST_REL).exists()

    def test_run_ingest_cycle_no_personalities_is_noop(self, tmp_path: Path) -> None:
        from allmight.capabilities.memory.ingest import (
            INGEST_PENDING_REL, LAST_INGEST_REL, run_ingest_cycle,
        )
        result = run_ingest_cycle(tmp_path, smak_cmd="this-should-not-be-called")
        assert result.errors == []
        assert result.succeeded == []
        # No personalities → do not create markers spuriously.
        assert not (tmp_path / LAST_INGEST_REL).exists()
        assert not (tmp_path / INGEST_PENDING_REL).exists()

    def test_run_ingest_cycle_handles_smak_missing(self, initted_with_memory: Path) -> None:
        from allmight.capabilities.memory.ingest import run_ingest_cycle
        result = run_ingest_cycle(
            initted_with_memory,
            smak_cmd="/no/such/binary/at/all",
        )
        # Either FileNotFoundError surfaces as an error entry, or the
        # shell fails with non-zero exit — both end up in errors.
        assert len(result.errors) == 1
        assert result.succeeded == []


# ===========================================================================
# CLI integration — ``allmight memory ingest``
# ===========================================================================

class TestCliMemoryIngest:
    def test_ingest_command_succeeds_with_fake_smak(
        self, initted_with_memory: Path, fake_smak: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLMIGHT_SMAK_CMD", f"{sys.executable} {fake_smak}")
        result = _invoke_in(initted_with_memory, ["memory", "ingest"])
        assert result.exit_code == 0, result.output
        assert "Ingested" in result.output

    def test_ingest_command_returns_nonzero_on_failure(
        self, initted_with_memory: Path, fake_smak: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLMIGHT_SMAK_CMD", f"{sys.executable} {fake_smak}")
        monkeypatch.setenv("FAKE_SMAK_FAIL", "2")
        result = _invoke_in(initted_with_memory, ["memory", "ingest"])
        assert result.exit_code != 0


# ===========================================================================
# Hook content — TS and PY both inline the marker-write logic
# ===========================================================================

class TestHookContentParity:
    """Pin the marker-write logic in both generated hook surfaces.

    These tests do NOT execute the hooks — they verify the strings
    are present so OpenCode and Claude Code drift is caught at init
    time, not by an end user opening the project in the other editor.
    """

    def test_ts_memory_history_writes_ingest_pending_marker(
        self, initted_with_memory: Path
    ) -> None:
        plugin = initted_with_memory / ".opencode" / "plugins" / "memory-history.ts"
        body = plugin.read_text()
        assert "ingest.pending" in body
        # Reference to the journal walk that decides whether to touch.
        assert "last_ingest" in body

    def test_py_memory_history_writes_ingest_pending_marker(
        self, initted_with_memory: Path
    ) -> None:
        hook = initted_with_memory / ".claude" / "hooks" / "memory_history.py"
        body = hook.read_text()
        assert "ingest.pending" in body
        assert "last_ingest" in body

    def test_ts_memory_load_spawns_drain_on_session_created(
        self, initted_with_memory: Path
    ) -> None:
        plugin = initted_with_memory / ".opencode" / "plugins" / "memory-load.ts"
        body = plugin.read_text()
        assert "ingest.pending" in body
        assert "memory" in body and "ingest" in body
        # Drain is fire-and-forget; must use detach pattern.
        assert "detached" in body or "unref" in body

    def test_py_memory_load_spawns_drain_on_session_start(
        self, initted_with_memory: Path
    ) -> None:
        hook = initted_with_memory / ".claude" / "hooks" / "memory_load.py"
        body = hook.read_text()
        assert "ingest.pending" in body
        assert "memory" in body and "ingest" in body


# ===========================================================================
# End-to-end: Stop hook (Python) actually creates the marker
# ===========================================================================

class TestStopHookMarksPending:
    """Run the generated memory_history.py end-to-end.

    The hook always spawns ``allmight memory snapshot`` fire-and-forget;
    that side effect is not under test here (it is covered by
    test_memory_history.py). What we assert: after the hook runs in a
    project with a fresh journal entry, ``.allmight/ingest.pending``
    exists.
    """

    def test_marks_pending_when_journal_has_new_entry(
        self, initted_with_memory: Path
    ) -> None:
        _write_journal_entry(
            initted_with_memory / "personalities" / "demo",
            "general", "first",
        )
        self._run_hook(initted_with_memory)
        assert (initted_with_memory / ".allmight" / "ingest.pending").exists()

    def test_does_not_mark_pending_when_no_journal_changes(
        self, initted_with_memory: Path
    ) -> None:
        # Pretend a previous ingest already covered the empty journal.
        last_ingest = initted_with_memory / ".allmight" / "last_ingest"
        last_ingest.parent.mkdir(parents=True, exist_ok=True)
        last_ingest.touch()
        time.sleep(0.02)
        self._run_hook(initted_with_memory)
        assert not (initted_with_memory / ".allmight" / "ingest.pending").exists()

    @staticmethod
    def _run_hook(project_root: Path) -> None:
        hook = project_root / ".claude" / "hooks" / "memory_history.py"
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(project_root)
        payload = json.dumps({"cwd": str(project_root), "session_id": "test"})
        proc = subprocess.run(
            [sys.executable, str(hook)],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert proc.returncode == 0, proc.stderr
