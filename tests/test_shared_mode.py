"""Shared-agent deployment via ``setup.cshrc``.

Pins the contract that:

1. ``ALLMIGHT_PROJECT_ROOT`` and ``ALLMIGHT_ROLE`` are the env-var
   names every TS plugin and Python hook reads (and that both surfaces
   read them the same way).
2. ``setup.cshrc`` is written into the project root at init time,
   carries the All-Might marker, and self-locates via ``$_`` / ``$0``.
3. Read-only role (``ALLMIGHT_ROLE=user``) short-circuits write-bearing
   hooks (memory-history snapshot, reflection injection) cleanly —
   both the OpenCode plugin and the Claude Code mirror.
4. Command bodies that touch personality data carry the
   ``${ALLMIGHT_PROJECT_ROOT:-.}/`` prefix so a shell run from any cwd
   resolves correctly.

These three are the load-bearing parts of the design; other surfaces
(AGENTS.md prose, /sync mapping table) are documentation that the
agent reads, not invariants the runtime depends on.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from allmight.capabilities.memory.initializer import MemoryInitializer
from allmight.cli import main
from allmight.core.markers import ALLMIGHT_MARKER_CSH
from allmight.core.project_root import (
    BASH_PROJECT_ROOT_PREFIX,
    PROJECT_ROOT_ENV,
    PY_IS_READ_ONLY_EXPR,
    PY_RESOLVE_CWD_SNIPPET,
    ROLE_ENV,
    ROLE_OWNER,
    ROLE_USER,
    TS_IS_READ_ONLY_EXPR,
    TS_RESOLVE_CWD_EXPR,
    is_read_only_py,
    resolve_project_root_py,
)


@pytest.fixture
def initted_project(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("def f(): pass\n")
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--yes", str(project)])
    assert result.exit_code == 0, result.output
    return project


class TestEnvVarContract:
    """The names and shapes pin down what users put in setup.cshrc."""

    def test_env_var_names_are_stable(self) -> None:
        assert PROJECT_ROOT_ENV == "ALLMIGHT_PROJECT_ROOT"
        assert ROLE_ENV == "ALLMIGHT_ROLE"
        assert ROLE_USER == "user"
        assert ROLE_OWNER == "owner"

    def test_bash_prefix_defaults_to_cwd(self) -> None:
        """``${ALLMIGHT_PROJECT_ROOT:-.}`` keeps single-user mode working
        even when the var is unset — the shell expands to ``.``."""
        env = {**os.environ}
        env.pop("ALLMIGHT_PROJECT_ROOT", None)
        out = subprocess.check_output(
            ["bash", "-c", f'echo "{BASH_PROJECT_ROOT_PREFIX}"'],
            env=env,
        ).decode().strip()
        assert out == ".", f"expected '.' when env unset, got {out!r}"

    def test_bash_prefix_uses_env_when_set(self, tmp_path: Path) -> None:
        env = {**os.environ, "ALLMIGHT_PROJECT_ROOT": str(tmp_path)}
        out = subprocess.check_output(
            ["bash", "-c", f'echo "{BASH_PROJECT_ROOT_PREFIX}"'],
            env=env,
        ).decode().strip()
        assert out == str(tmp_path)


class TestPythonResolver:
    """The Python resolver is the runtime contract for Claude Code hooks."""

    def test_resolver_returns_cwd_when_env_unset(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.delenv("ALLMIGHT_PROJECT_ROOT", raising=False)
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        assert resolve_project_root_py() == tmp_path

    def test_resolver_prefers_allmight_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        shared = tmp_path / "shared"
        shared.mkdir()
        other = tmp_path / "other"
        other.mkdir()
        monkeypatch.setenv("ALLMIGHT_PROJECT_ROOT", str(shared))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(other))
        monkeypatch.chdir(other)
        assert resolve_project_root_py() == shared

    def test_resolver_falls_back_to_claude_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.delenv("ALLMIGHT_PROJECT_ROOT", raising=False)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        assert resolve_project_root_py() == tmp_path

    def test_is_read_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ALLMIGHT_ROLE", raising=False)
        assert not is_read_only_py()
        monkeypatch.setenv("ALLMIGHT_ROLE", "user")
        assert is_read_only_py()
        monkeypatch.setenv("ALLMIGHT_ROLE", "owner")
        assert not is_read_only_py()


class TestSetupCshrc:
    """The setup.cshrc artifact: presence, marker, env-var exports."""

    def test_setup_cshrc_is_written_at_init(self, initted_project: Path) -> None:
        path = initted_project / "setup.cshrc"
        assert path.is_file(), "init must emit setup.cshrc at project root"

    def test_setup_cshrc_carries_marker(self, initted_project: Path) -> None:
        body = (initted_project / "setup.cshrc").read_text()
        assert body.startswith(ALLMIGHT_MARKER_CSH), (
            "setup.cshrc must lead with the All-Might marker so re-init "
            "can distinguish framework-emitted from user-customised."
        )

    def test_setup_cshrc_exports_required_envs(
        self, initted_project: Path,
    ) -> None:
        body = (initted_project / "setup.cshrc").read_text()
        assert "setenv ALLMIGHT_PROJECT_ROOT" in body
        assert "setenv ALLMIGHT_ROLE" in body
        assert "user" in body, "default role for shared mode is read-only"

    def test_setup_cshrc_aliases_opencode_and_allmight(
        self, initted_project: Path,
    ) -> None:
        body = (initted_project / "setup.cshrc").read_text()
        assert 'alias opencode' in body and "$ALLMIGHT_PROJECT_ROOT" in body
        assert 'alias allmight' in body


class TestPluginsResolveSharedRoot:
    """Every generated TS plugin reads ``process.env.ALLMIGHT_PROJECT_ROOT``."""

    def test_every_plugin_consults_env_var(
        self, initted_project: Path,
    ) -> None:
        plugins = sorted((initted_project / ".opencode" / "plugins").glob("*.ts"))
        assert plugins, "init must emit OpenCode plugins"
        offenders = []
        for plugin in plugins:
            body = plugin.read_text()
            if "process.env.ALLMIGHT_PROJECT_ROOT" not in body:
                offenders.append(plugin.name)
        assert not offenders, (
            "Every plugin must resolve cwd via ALLMIGHT_PROJECT_ROOT first "
            "so shared-agent mode works from any cwd. Offenders: "
            f"{offenders}"
        )

    def test_resolver_snippet_is_canonical(self) -> None:
        """The TS resolution snippet is fixed — ``test_capability_manifest``
        depends on this exact shape so the surfaces cannot drift."""
        assert "process.env.ALLMIGHT_PROJECT_ROOT" in TS_RESOLVE_CWD_EXPR
        assert "directory as string | undefined" in TS_RESOLVE_CWD_EXPR
        assert "process.cwd()" in TS_RESOLVE_CWD_EXPR


class TestReadOnlyShortCircuit:
    """Read-only role must skip writes in BOTH surfaces (TS + Python)."""

    def test_memory_history_ts_checks_role(
        self, initted_project: Path,
    ) -> None:
        body = (initted_project / ".opencode" / "plugins" / "memory-history.ts").read_text()
        assert TS_IS_READ_ONLY_EXPR in body, (
            "memory-history.ts must check ALLMIGHT_ROLE before snapshotting"
        )

    def test_reflection_ts_checks_role(
        self, initted_project: Path,
    ) -> None:
        body = (initted_project / ".opencode" / "plugins" / "reflection.ts").read_text()
        assert TS_IS_READ_ONLY_EXPR in body, (
            "reflection.ts must check ALLMIGHT_ROLE before injecting"
        )

    def test_memory_history_py_checks_role(
        self, initted_project: Path,
    ) -> None:
        body = (initted_project / ".claude" / "hooks" / "memory_history.py").read_text()
        assert PY_IS_READ_ONLY_EXPR in body, (
            "memory_history.py must check ALLMIGHT_ROLE before snapshotting"
        )

    def test_reflection_py_checks_role(
        self, initted_project: Path,
    ) -> None:
        body = (initted_project / ".claude" / "hooks" / "reflection.py").read_text()
        assert PY_IS_READ_ONLY_EXPR in body, (
            "reflection.py must check ALLMIGHT_ROLE before injecting"
        )

    def test_memory_history_py_skips_under_read_only(
        self, initted_project: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """End-to-end: running the hook with ``ALLMIGHT_ROLE=user``
        produces an empty hook output and never spawns the snapshot
        subprocess. Stand-in for the OpenCode plugin which we cannot
        execute in pytest (no JS runtime in CI)."""
        hook = initted_project / ".claude" / "hooks" / "memory_history.py"
        env = {**os.environ, "ALLMIGHT_ROLE": "user"}
        env.pop("ALLMIGHT_PROJECT_ROOT", None)
        result = subprocess.run(
            [sys.executable, str(hook)],
            input="{}",
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "{}", (
            "read-only memory-history hook must emit '{}' and skip the "
            f"snapshot subprocess. Got: {result.stdout!r}"
        )

    def test_remember_command_body_handles_read_only(
        self, initted_project: Path,
    ) -> None:
        body = (initted_project / ".opencode" / "commands" / "remember.md").read_text()
        assert "ALLMIGHT_ROLE" in body, (
            "remember.md must teach the agent to detect read-only sessions"
        )
        assert "read-only" in body.lower()


class TestCommandBodiesUseBashPrefix:
    """Shell commands the agent runs must carry the project-root prefix."""

    def test_search_body_uses_prefix(self, initted_project: Path) -> None:
        body = (initted_project / ".opencode" / "commands" / "search.md").read_text()
        assert BASH_PROJECT_ROOT_PREFIX in body, (
            "search.md emits smak commands; without the env-var prefix "
            "they only work when the agent's cwd is the project root."
        )

    def test_remember_body_uses_prefix(self, initted_project: Path) -> None:
        body = (initted_project / ".opencode" / "commands" / "remember.md").read_text()
        assert BASH_PROJECT_ROOT_PREFIX in body, (
            "remember.md emits file paths; without the env-var prefix "
            "they only resolve when the agent's cwd is the project root."
        )

    def test_routing_preamble_documents_prefix(self) -> None:
        from allmight.core.routing import ROUTING_PREAMBLE
        assert "ALLMIGHT_PROJECT_ROOT" in ROUTING_PREAMBLE, (
            "ROUTING_PREAMBLE must teach the agent the env-var convention "
            "so it can use the prefix in any new ad-hoc commands too."
        )


class TestPyResolveSnippet:
    """The Python snippet's text shape is what hook templates substitute."""

    def test_snippet_mentions_both_env_vars(self) -> None:
        assert 'os.environ.get("ALLMIGHT_PROJECT_ROOT")' in PY_RESOLVE_CWD_SNIPPET
        assert 'os.environ.get("CLAUDE_PROJECT_DIR")' in PY_RESOLVE_CWD_SNIPPET
        assert "os.getcwd()" in PY_RESOLVE_CWD_SNIPPET
