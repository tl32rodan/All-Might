"""Tests for F1.5 — L1 as portable-only memory (audit + passive nudge).

MEMORY.md is loaded every turn via hook. The cap is a forcing function
for essence extraction — when exceeded, the agent is *nudged* to triage
(migrate corpus-specific content to L2, open TODOs to per-corpus state).
The cap never silently evicts anything.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from allmight.cli import main
from click.testing import CliRunner

from allmight.personalities.memory_keeper.cap_audit import audit_and_update_sentinel
from allmight.personalities.memory_keeper.initializer import MemoryInitializer
from allmight.personalities.memory_keeper.l1_rewriter import (
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
            [sys.executable, "-m", "allmight.personalities.memory_keeper.cap_audit", str(tmp_path)],
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
    """The cap audit module must be importable and runnable as a script.

    The Claude-Code Stop hook (``.claude/hooks/memory-cap.sh``) was
    removed when All-Might moved to an OpenCode-only runtime — its
    behaviour is now expected to be triggered externally (e.g. by an
    OpenCode plugin or a user-configured hook) via the same module
    entry point that ``TestModuleRunnableAsScript`` exercises.
    """

    def test_cap_audit_exposes_entry_point(self):
        from allmight.personalities.memory_keeper import cap_audit

        assert hasattr(cap_audit, "audit_and_update_sentinel")
        assert callable(cap_audit.audit_and_update_sentinel)


class TestMemoryLoadHookWarning:
    """L1-over-cap nudge surfaces through MEMORY.md content, not a shell hook.

    The TS plugin ``memory-load.ts`` injects MEMORY.md every session,
    and the agent reads ``memory/.l1-over-cap`` directly during
    /reflect's cap-triage step. There is no longer a ``.claude/`` hook
    that prefixes a warning to stdout, so the only contract left to
    test here is the sentinel file itself, covered by
    ``TestAuditAndUpdateSentinel``.
    """

    def test_memory_load_plugin_replaces_shell_hook(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        # Plugin exists; legacy shell hook does not.
        assert (tmp_path / ".opencode" / "plugins" / "memory-load.ts").exists()
        assert not (tmp_path / ".claude").exists()


class TestCommandBodies:

    def test_remember_command_states_portable_only_rule(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        body = (tmp_path / ".opencode" / "commands" / "remember.md").read_text()
        # The portable-only test: "no matter which corpus"
        assert "portable" in body.lower() or "no matter which corpus" in body.lower()

    def test_reflect_has_cap_triage_step(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        body = (tmp_path / ".opencode" / "commands" / "remember.md").read_text()
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
