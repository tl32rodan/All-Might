"""Content tests for the generated ``search-surface.ts`` OpenCode plugin.

These assert *what strings get written* (positive signatures + negative
forbidden shapes). They do not execute the plugin — runtime behaviour on
a live OpenCode host is the prototype step (proposal §7.1, P-6).
``tests/test_plugin_typecheck.py`` separately runs ``tsc --noEmit`` over
the emitted ``.ts``.

See ``docs/retrieval-surfacing-proposal.md``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from allmight.cli import main


@pytest.fixture
def plugin_body(tmp_path: Path) -> str:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--yes", str(tmp_path)])
    assert result.exit_code == 0, result.output
    plugin = tmp_path / ".opencode" / "plugins" / "search-surface.ts"
    assert plugin.is_file(), "init must write search-surface.ts"
    return plugin.read_text()


@pytest.fixture
def initted(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--yes", str(tmp_path)])
    assert result.exit_code == 0, result.output
    return tmp_path


class TestPositiveSignatures:
    def test_marker_present(self, plugin_body: str) -> None:
        assert plugin_body.startswith("// all-might generated")

    def test_tool_execute_after_signature(self, plugin_body: str) -> None:
        # The verified in-repo hook shape (cf. todo-curator).
        assert '"tool.execute.after": async (input: any' in plugin_body

    def test_heartbeats_all_three_tiers(self, plugin_body: str) -> None:
        assert 'emitHeartbeat("search-surface", cwd)' in plugin_body
        assert 'emitHeartbeat("search-surface.injected", cwd)' in plugin_body
        assert 'emitHeartbeat("search-surface.ingest", cwd)' in plugin_body

    def test_smak_search_invocation(self, plugin_body: str) -> None:
        assert "search-all" in plugin_body
        assert "--json" in plugin_body
        assert "--config" in plugin_body

    def test_ingest_kick_invocation(self, plugin_body: str) -> None:
        # Fire-and-forget `allmight database ingest --incremental`.
        assert '"database"' in plugin_body
        assert '"ingest"' in plugin_body
        assert '"--incremental"' in plugin_body
        assert "detached" in plugin_body or "unref" in plugin_body

    def test_active_personality_resolution(self, plugin_body: str) -> None:
        # Reuses the MEMORY.md default-personality callout + database glob.
        assert "Default personality" in plugin_body
        assert "database" in plugin_body

    def test_gates_on_grep_glob(self, plugin_body: str) -> None:
        assert '"grep"' in plugin_body and '"glob"' in plugin_body


class TestNegativeShapes:
    """Augment-only (P-2): never gate/deny/block the tool."""

    def test_no_gating_or_blocking(self, plugin_body: str) -> None:
        assert "permissionDecision" not in plugin_body
        assert '"deny"' not in plugin_body

    def test_surfaces_via_output_append_not_parts_unshift(
        self, plugin_body: str
    ) -> None:
        # This plugin appends to the tool output; it must NOT inject the
        # SMAK block via the chat.message parts path (the other plugins'
        # surface). Same-turn append is the whole point.
        assert "output.output" in plugin_body
        assert "output.parts.unshift" not in plugin_body

    def test_no_stale_msg_content_mutation(self, plugin_body: str) -> None:
        assert "msg.content =" not in plugin_body


class TestOpenCodeOnlyInvariant:
    """No Claude Code mirror this round (proposal P-4 → OC-only first)."""

    def test_no_python_hook_emitted(self, initted: Path) -> None:
        hook = initted / ".claude" / "hooks" / "search_surface.py"
        assert not hook.exists(), (
            "search-surface is claude_code_mirror=None; no .py hook may exist"
        )

    def test_manifest_entry_is_oc_only(self) -> None:
        from allmight.core.plugin_telemetry import (
            PLATFORM_CAPABILITIES, PLUGIN_MANIFEST,
        )
        entry = PLUGIN_MANIFEST["search-surface"]
        assert entry["claude_code_mirror"] is None
        # OC-only ⇒ at least one required capability is cc-unavailable.
        blockers = [
            cap for cap in entry["requires"]
            if not PLATFORM_CAPABILITIES[cap]["claude_code"]
        ]
        assert blockers, "OC-only plugin needs a cc:False blocker capability"


class TestReinitPreservesUserEdits:
    """search-surface.ts is marker-guarded: a user edit (sans marker)
    survives re-init; an owned copy refreshes."""

    def test_user_authored_plugin_preserved_on_reinit(self, initted: Path) -> None:
        plugin = initted / ".opencode" / "plugins" / "search-surface.ts"
        plugin.write_text("// my own plugin, no marker\n")
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--yes", str(initted)])
        assert result.exit_code == 0, result.output
        assert plugin.read_text() == "// my own plugin, no marker\n"
