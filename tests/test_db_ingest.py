"""Unit + CLI tests for the database auto-ingest closure (proposal §6).

The ``search-surface`` plugin lazily kicks ``allmight database ingest
--incremental`` off the hot path; this module pins the canonical,
testable Python core (``capabilities/database/ingest.py``) and the CLI
seam the plugin spawns. Mirrors ``tests/test_l3_auto_ingest.py`` (the
memory L3 closure) since the two share the run-cycle shape.
"""

from __future__ import annotations

import os
import stat
import sys
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


def _add_workspace(root: Path, personality: str, workspace: str) -> Path:
    """Create a SMAK workspace config (normally user-written)."""
    ws = root / "personalities" / personality / "database" / workspace
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "config.yaml").write_text("indices: []\n")
    return ws


@pytest.fixture
def initted_with_database(tmp_path: Path) -> Path:
    """Init project + add one personality with the database capability."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--yes", str(tmp_path)])
    assert result.exit_code == 0, result.output
    add = _invoke_in(tmp_path, ["add", "demo", "--capabilities", "database"])
    assert add.exit_code == 0, add.output
    _add_workspace(tmp_path, "demo", "code")
    return tmp_path


@pytest.fixture
def fake_smak(tmp_path: Path) -> Path:
    """A standin for ``smak`` that records calls; exit via $FAKE_SMAK_FAIL."""
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


# ===========================================================================
# Unit tests — capabilities/database/ingest.py
# ===========================================================================

class TestHelperFunctions:
    def test_find_db_configs_locates_each_workspace(
        self, initted_with_database: Path
    ) -> None:
        from allmight.capabilities.database.ingest import find_db_configs
        _add_workspace(initted_with_database, "demo", "docs")
        configs = find_db_configs(initted_with_database)
        assert len(configs) == 2
        assert all(c.name == "config.yaml" for c in configs)
        assert configs == sorted(configs)  # deterministic ordering
        assert "personalities/demo/database" in str(configs[0])

    def test_find_db_configs_empty_when_no_personalities(self, tmp_path: Path) -> None:
        from allmight.capabilities.database.ingest import find_db_configs
        assert find_db_configs(tmp_path) == []

    def test_run_cycle_invokes_smak_per_workspace_incremental(
        self, initted_with_database: Path, fake_smak: Path, tmp_path: Path
    ) -> None:
        from allmight.capabilities.database.ingest import run_db_ingest_cycle
        _add_workspace(initted_with_database, "demo", "docs")

        log = tmp_path / "smak_calls.log"
        os.environ["FAKE_SMAK_LOG"] = str(log)
        try:
            result = run_db_ingest_cycle(
                initted_with_database,
                smak_cmd=f"{sys.executable} {fake_smak}",
            )
        finally:
            os.environ.pop("FAKE_SMAK_LOG", None)
        assert result.errors == []
        assert len(result.succeeded) == 2
        calls = log.read_text().strip().splitlines()
        assert len(calls) == 2
        assert all("ingest" in c for c in calls)
        assert all("--incremental" in c for c in calls)
        assert all("--config" in c for c in calls)

    def test_run_cycle_full_mode_omits_incremental(
        self, initted_with_database: Path, fake_smak: Path, tmp_path: Path
    ) -> None:
        from allmight.capabilities.database.ingest import run_db_ingest_cycle
        log = tmp_path / "smak_calls.log"
        os.environ["FAKE_SMAK_LOG"] = str(log)
        try:
            run_db_ingest_cycle(
                initted_with_database,
                incremental=False,
                smak_cmd=f"{sys.executable} {fake_smak}",
            )
        finally:
            os.environ.pop("FAKE_SMAK_LOG", None)
        calls = log.read_text().strip().splitlines()
        assert calls and all("--incremental" not in c for c in calls)

    def test_run_cycle_touches_marker_on_success(
        self, initted_with_database: Path, fake_smak: Path
    ) -> None:
        from allmight.capabilities.database.ingest import (
            DB_LAST_INGEST_REL, run_db_ingest_cycle,
        )
        result = run_db_ingest_cycle(
            initted_with_database, smak_cmd=f"{sys.executable} {fake_smak}",
        )
        assert result.errors == []
        assert (initted_with_database / DB_LAST_INGEST_REL).exists()

    def test_run_cycle_keeps_marker_absent_on_failure(
        self, initted_with_database: Path, fake_smak: Path
    ) -> None:
        from allmight.capabilities.database.ingest import (
            DB_LAST_INGEST_REL, run_db_ingest_cycle,
        )
        os.environ["FAKE_SMAK_FAIL"] = "2"
        try:
            result = run_db_ingest_cycle(
                initted_with_database, smak_cmd=f"{sys.executable} {fake_smak}",
            )
        finally:
            os.environ.pop("FAKE_SMAK_FAIL", None)
        assert result.succeeded == []
        assert len(result.errors) == 1
        assert not (initted_with_database / DB_LAST_INGEST_REL).exists()

    def test_run_cycle_no_configs_is_noop(self, tmp_path: Path) -> None:
        from allmight.capabilities.database.ingest import (
            DB_LAST_INGEST_REL, run_db_ingest_cycle,
        )
        result = run_db_ingest_cycle(tmp_path, smak_cmd="this-should-not-be-called")
        assert result.errors == []
        assert result.succeeded == []
        assert not (tmp_path / DB_LAST_INGEST_REL).exists()

    def test_run_cycle_handles_smak_missing(
        self, initted_with_database: Path
    ) -> None:
        from allmight.capabilities.database.ingest import run_db_ingest_cycle
        result = run_db_ingest_cycle(
            initted_with_database, smak_cmd="/no/such/binary/at/all",
        )
        assert len(result.errors) == 1
        assert result.succeeded == []


# ===========================================================================
# CLI integration — ``allmight database ingest``
# ===========================================================================

class TestCliDatabaseIngest:
    def test_ingest_command_succeeds_with_fake_smak(
        self, initted_with_database: Path, fake_smak: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ALLMIGHT_SMAK_CMD", f"{sys.executable} {fake_smak}")
        result = _invoke_in(initted_with_database, ["database", "ingest"])
        assert result.exit_code == 0, result.output
        assert "Ingested" in result.output

    def test_ingest_command_returns_nonzero_on_failure(
        self, initted_with_database: Path, fake_smak: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ALLMIGHT_SMAK_CMD", f"{sys.executable} {fake_smak}")
        monkeypatch.setenv("FAKE_SMAK_FAIL", "2")
        result = _invoke_in(initted_with_database, ["database", "ingest"])
        assert result.exit_code != 0
