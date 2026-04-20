"""Tests for F1.5 — L1 as portable-only memory (audit + passive nudge).

MEMORY.md is loaded every turn via hook. The cap is a forcing function
for essence extraction — when exceeded, the agent is *nudged* to triage
(migrate corpus-specific content to L2, open TODOs to per-corpus state).
The cap never silently evicts anything.
"""

from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path

import yaml

from allmight.cli import main
from click.testing import CliRunner

from allmight.memory.cap_audit import audit_and_update_sentinel
from allmight.memory.initializer import MemoryInitializer
from allmight.memory.l1_rewriter import (
    DEFAULT_MAX_BYTES,
    SENTINEL_MARKER,
    AuditResult,
    L1Auditor,
)


def _big_memory_md() -> str:
    """A MEMORY.md several times over the default cap."""
    sections = ["Project Map", "User Preferences", "Active Goals", "Key Facts"]
    out = [f"<!-- {SENTINEL_MARKER}=4096 -->", "", "# Project Memory", ""]
    for sec in sections:
        out.append(f"## {sec}")
        out.append("")
        for i in range(80):
            out.append(f"- {sec} item {i:03d}: " + ("x" * 40))
        out.append("")
    return "\n".join(out) + "\n"


class TestL1Auditor:

    def test_audit_under_cap_reports_ok(self):
        md = "# Project Memory\n\n## Project Map\n\n- one bullet\n"
        result = L1Auditor().audit(md)
        assert isinstance(result, AuditResult)
        assert result.over is False
        assert result.overflow_bytes == 0
        assert result.cap == DEFAULT_MAX_BYTES
        assert result.body_bytes > 0

    def test_audit_over_cap_reports_overflow(self):
        result = L1Auditor().audit(_big_memory_md())
        assert result.over is True
        assert result.overflow_bytes > 0
        assert result.body_bytes > DEFAULT_MAX_BYTES

    def test_body_of_strips_sentinel(self):
        md = f"<!-- {SENTINEL_MARKER}=4096 -->\n\n# body\n\ntext\n"
        body = L1Auditor().body_of(md)
        assert SENTINEL_MARKER not in body
        assert "# body" in body


class TestAuditAndUpdateSentinel:
    """The single entry point used by the Stop hook: audit + write/remove sentinel.

    Must NEVER modify MEMORY.md itself.
    """

    def test_audit_never_modifies_memory_md(self, tmp_path):
        memory_md = tmp_path / "MEMORY.md"
        original = _big_memory_md()
        memory_md.write_text(original)
        (tmp_path / "memory").mkdir()

        audit_and_update_sentinel(tmp_path)

        # Byte-level comparison — NOTHING rewrote the file.
        assert memory_md.read_text() == original

    def test_audit_writes_nudge_when_over(self, tmp_path):
        (tmp_path / "MEMORY.md").write_text(_big_memory_md())
        (tmp_path / "memory").mkdir()

        audit_and_update_sentinel(tmp_path)

        sentinel = tmp_path / "memory" / ".l1-over-cap"
        assert sentinel.exists()

        payload = yaml.safe_load(sentinel.read_text())
        assert payload["cap"] == DEFAULT_MAX_BYTES
        assert payload["overflow_bytes"] > 0
        assert payload["body_bytes"] > DEFAULT_MAX_BYTES
        assert "timestamp" in payload

    def test_audit_removes_nudge_when_under(self, tmp_path):
        (tmp_path / "MEMORY.md").write_text("# tiny\n\n## Project Map\n\n- one\n")
        (tmp_path / "memory").mkdir()
        sentinel = tmp_path / "memory" / ".l1-over-cap"
        sentinel.write_text("overflow_bytes: 10\n")  # pre-seed

        audit_and_update_sentinel(tmp_path)

        assert not sentinel.exists()

    def test_audit_noop_when_no_memory_md(self, tmp_path):
        # Should not crash if MEMORY.md is missing (hook fires on fresh init).
        (tmp_path / "memory").mkdir()
        audit_and_update_sentinel(tmp_path)
        assert not (tmp_path / "memory" / ".l1-over-cap").exists()


class TestModuleRunnableAsScript:

    def test_cap_audit_module_runnable_as_script(self, tmp_path):
        (tmp_path / "MEMORY.md").write_text(_big_memory_md())
        (tmp_path / "memory").mkdir()

        src_path = Path(__file__).parent.parent / "src"
        env = {"PYTHONPATH": str(src_path), "PATH": ""}
        result = subprocess.run(
            [sys.executable, "-m", "allmight.memory.cap_audit", str(tmp_path)],
            capture_output=True,
            text=True,
            env={**env, "PATH": "/usr/bin:/bin"},
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (tmp_path / "memory" / ".l1-over-cap").exists()


class TestMemoryMdTemplate:

    def test_memory_md_has_sentinel_comment(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        content = (tmp_path / "MEMORY.md").read_text()
        assert SENTINEL_MARKER in content

    def test_memory_md_has_no_next_session_section(self, tmp_path):
        """Negative: the Wave 1 handoff section is gone."""
        MemoryInitializer().initialize(tmp_path)
        content = (tmp_path / "MEMORY.md").read_text()
        assert "Next Session Start Here" not in content

    def test_memory_md_template_states_portable_only_rule(self, tmp_path):
        """MEMORY.md must explain L1's portable-to-all-corpora scope."""
        MemoryInitializer().initialize(tmp_path)
        content = (tmp_path / "MEMORY.md").read_text()
        assert "portable" in content.lower()
        # Points readers toward L2 + per-corpus state for non-portable content.
        assert "memory/understanding" in content


class TestStopHookCap:

    def test_memory_cap_hook_script_exists(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        script = tmp_path / ".claude" / "hooks" / "memory-cap.sh"
        assert script.exists()

    def test_memory_cap_hook_is_executable(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        script = tmp_path / ".claude" / "hooks" / "memory-cap.sh"
        mode = script.stat().st_mode
        assert mode & stat.S_IXUSR
        assert mode & stat.S_IXGRP

    def test_memory_cap_hook_invokes_python_module(self, tmp_path):
        """Hook must call the module directly, not a CLI subcommand."""
        MemoryInitializer().initialize(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "memory-cap.sh").read_text()
        assert "python3 -m allmight.memory.cap_audit" in content
        # Negative: old CLI call is gone.
        assert "allmight memory cap" not in content

    def test_memory_cap_hook_tolerates_failure(self, tmp_path):
        """Must never block Stop — errors swallowed."""
        MemoryInitializer().initialize(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "memory-cap.sh").read_text()
        assert "|| true" in content


class TestMemoryLoadHookWarning:

    def test_memory_load_injects_over_cap_warning_when_nudge_present(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        (tmp_path / "MEMORY.md").write_text("# tiny\n")
        sentinel = tmp_path / "memory" / ".l1-over-cap"
        sentinel.write_text(
            "overflow_bytes: 1234\ncap: 4096\nbody_bytes: 5330\n"
            "timestamp: 2026-04-20T10:15:00Z\n"
        )

        script = tmp_path / ".claude" / "hooks" / "memory-load.sh"
        stdin = f'{{"cwd":"{tmp_path}"}}'
        result = subprocess.run(
            ["bash", str(script)],
            input=stdin,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "L1 over cap" in result.stdout
        # Warning must precede MEMORY.md content.
        assert result.stdout.index("L1 over cap") < result.stdout.index("# tiny")

    def test_memory_load_no_warning_when_nudge_absent(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        (tmp_path / "MEMORY.md").write_text("# tiny\n")

        script = tmp_path / ".claude" / "hooks" / "memory-load.sh"
        stdin = f'{{"cwd":"{tmp_path}"}}'
        result = subprocess.run(
            ["bash", str(script)],
            input=stdin,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "L1 over cap" not in result.stdout


class TestCommandBodies:

    def test_remember_command_states_portable_only_rule(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        body = (tmp_path / ".claude" / "commands" / "remember.md").read_text()
        # The portable-only test: "no matter which corpus"
        assert "portable" in body.lower() or "no matter which corpus" in body.lower()

    def test_reflect_has_cap_triage_step(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        body = (tmp_path / ".claude" / "commands" / "reflect.md").read_text()
        assert "cap triage" in body.lower() or "L1 cap" in body
        # References the sentinel file so the agent knows what clears the nudge.
        assert ".l1-over-cap" in body


class TestHandoffRemoved:
    """Wave 1 F1 artifacts must be gone."""

    def test_no_handoff_writer_plugin(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        assert not (tmp_path / ".opencode" / "plugins" / "handoff-writer.ts").exists()

    def test_opencode_plugin_map_excludes_handoff_writer(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        plugin_dir = tmp_path / ".opencode" / "plugins"
        filenames = {p.name for p in plugin_dir.glob("*.ts")}
        assert "handoff-writer.ts" not in filenames


class TestCliMemoryCapRemoved:
    """The user-facing CLI subcommand is gone — hook uses the module directly."""

    def test_memory_cap_cli_subcommand_not_registered(self):
        runner = CliRunner()
        result = runner.invoke(main, ["memory", "cap", "--help"])
        # Click emits a non-zero exit code and a "No such command" message.
        assert result.exit_code != 0
        assert "cap" in result.output.lower()  # error mentions the missing command

    def test_memory_cap_not_in_memory_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["memory", "--help"])
        assert result.exit_code == 0
        assert "cap" not in result.output.lower()
