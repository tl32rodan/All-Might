"""Tests for the Capability Manifest (work item A' — see docs/plan.md).

The manifest is the declarative replacement for the hand-maintained
plugin↔hook mirror table. Each plugin declares which platform
capabilities it needs; the manifest decides whether a Claude Code
mirror is structurally possible.

Three invariants the tests enforce:

1. Every plugin in ``KNOWN_OPENCODE_PLUGINS`` is declared in
   ``PLUGIN_MANIFEST``; every capability in ``requires:`` is declared
   in ``PLATFORM_CAPABILITIES``.
2. A plugin with ``claude_code_mirror: <name>`` produces a Python
   hook file on init; a plugin with ``claude_code_mirror: None``
   does **not** produce a Python hook file (no no-op stubs).
3. ``allmight plugin status`` distinguishes "never fired" from
   "structurally unavailable" — surfacing the reason instead of
   silently lying about parity.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from allmight.capabilities.memory.initializer import MemoryInitializer
from allmight.cli import main
from allmight.core.plugin_telemetry import (
    KNOWN_CLAUDE_HOOKS,
    KNOWN_OPENCODE_PLUGINS,
    PLATFORM_CAPABILITIES,
    PLUGIN_MANIFEST,
    cc_unavailable_reasons,
    format_compatibility_matrix,
    is_cc_mirrored,
)


def _invoke_in(root: Path, args: list[str]):
    runner = CliRunner()
    cwd = os.getcwd()
    try:
        os.chdir(root)
        return runner.invoke(main, args, catch_exceptions=False)
    finally:
        os.chdir(cwd)


# ===========================================================================
# Manifest shape — invariants
# ===========================================================================

class TestManifestShape:
    def test_every_known_plugin_in_manifest(self):
        missing = set(KNOWN_OPENCODE_PLUGINS) - set(PLUGIN_MANIFEST)
        assert not missing, f"plugins missing from manifest: {missing}"

    def test_manifest_has_no_orphan_entries(self):
        """Manifest should not declare plugins that nothing generates."""
        orphans = set(PLUGIN_MANIFEST) - set(KNOWN_OPENCODE_PLUGINS)
        assert not orphans, f"orphan manifest entries: {orphans}"

    def test_every_requires_capability_is_declared(self):
        undeclared = set()
        for plugin, entry in PLUGIN_MANIFEST.items():
            for cap in entry["requires"]:
                if cap not in PLATFORM_CAPABILITIES:
                    undeclared.add((plugin, cap))
        assert not undeclared, f"undeclared capabilities: {undeclared}"

    def test_each_capability_declares_both_platforms(self):
        for cap, support in PLATFORM_CAPABILITIES.items():
            assert "opencode" in support, f"{cap} missing opencode flag"
            assert "claude_code" in support, f"{cap} missing claude_code flag"

    def test_every_manifest_entry_has_purpose(self):
        """Each plugin entry must explain WHAT it does. The matrix
        renders this; without it the README is unhelpful."""
        for plugin, entry in PLUGIN_MANIFEST.items():
            assert entry.get("purpose"), f"{plugin} missing purpose"


# ===========================================================================
# Capability ↔ mirror coherence
# ===========================================================================

class TestMirrorCoherence:
    """`claude_code_mirror` value must be consistent with whether all
    required capabilities are available on Claude Code."""

    def test_oc_only_plugins_have_at_least_one_cc_blocker(self):
        """A plugin with ``claude_code_mirror: None`` must have at
        least one ``requires:`` capability that is unavailable on
        Claude Code. Otherwise marking it None is hiding a TODO, not
        a structural impossibility."""
        for plugin, entry in PLUGIN_MANIFEST.items():
            if entry["claude_code_mirror"] is not None:
                continue
            blockers = cc_unavailable_reasons(plugin)
            assert blockers, (
                f"{plugin} is claude_code_mirror=None but every "
                f"required capability is available on Claude Code "
                f"— this is a TODO, not OC-only. Either mirror it or "
                f"declare an OC-only requires capability."
            )

    def test_mirrored_plugins_have_all_caps_available_on_cc(self):
        """Symmetric check: a plugin with ``claude_code_mirror: <name>``
        must have every ``requires:`` capability available on Claude
        Code. Otherwise we are claiming a mirror we cannot honour."""
        for plugin, entry in PLUGIN_MANIFEST.items():
            mirror = entry["claude_code_mirror"]
            if mirror is None:
                continue
            blockers = cc_unavailable_reasons(plugin)
            assert not blockers, (
                f"{plugin} claims claude_code_mirror={mirror!r} but "
                f"requires unavailable Claude Code capabilities: "
                f"{blockers}"
            )

    def test_derived_known_claude_hooks_matches_mirrors(self):
        """KNOWN_CLAUDE_HOOKS is derived from manifest entries with a
        non-null mirror. Pinning both directions catches drift if
        somebody hand-edits the tuple."""
        derived = {
            entry["claude_code_mirror"].removesuffix(".py")
            for entry in PLUGIN_MANIFEST.values()
            if entry["claude_code_mirror"]
        }
        assert set(KNOWN_CLAUDE_HOOKS) == derived


# ===========================================================================
# Helpers
# ===========================================================================

class TestHelpers:
    def test_is_cc_mirrored_true_for_memory_load(self):
        assert is_cc_mirrored("memory-load") is True

    def test_is_cc_mirrored_false_for_remember_trigger(self):
        assert is_cc_mirrored("remember-trigger") is False

    def test_is_cc_mirrored_false_for_unknown_plugin(self):
        assert is_cc_mirrored("not-a-real-plugin") is False

    def test_cc_unavailable_reasons_lists_blockers(self):
        reasons = cc_unavailable_reasons("remember-trigger")
        assert reasons, "remember-trigger must have at least one blocker"
        # Every reason must be a real capability
        for r in reasons:
            assert r in PLATFORM_CAPABILITIES

    def test_cc_unavailable_reasons_empty_for_mirrored(self):
        assert cc_unavailable_reasons("memory-load") == []


# ===========================================================================
# Filesystem — mirror declaration matches what init writes
# ===========================================================================

@pytest.fixture
def initted_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--yes", str(tmp_path)])
    assert result.exit_code == 0, result.output
    return tmp_path


class TestMirrorFilesOnDisk:
    def test_mirrored_plugins_produce_python_hook(self, initted_project: Path):
        hooks_dir = initted_project / ".claude" / "hooks"
        for plugin, entry in PLUGIN_MANIFEST.items():
            mirror = entry["claude_code_mirror"]
            if mirror is None:
                continue
            assert (hooks_dir / mirror).exists(), (
                f"{plugin} declares mirror={mirror!r} but file is missing"
            )

    def test_oc_only_plugins_do_not_produce_python_hook(self, initted_project: Path):
        """No no-op stubs. If a plugin is OC-only, there must be NO
        Python file in .claude/hooks/ with a name matching the plugin
        (with - / _ normalised). The point of A' was to stop pretending
        parity exists where it does not."""
        hooks_dir = initted_project / ".claude" / "hooks"
        for plugin, entry in PLUGIN_MANIFEST.items():
            if entry["claude_code_mirror"] is not None:
                continue
            normalised = plugin.replace("-", "_") + ".py"
            assert not (hooks_dir / normalised).exists(), (
                f"{plugin} is OC-only but {normalised} exists as a "
                f"no-op stub — that contradicts the A' protocol"
            )


# ===========================================================================
# `allmight plugin status` surfaces unavailability with a reason
# ===========================================================================

class TestPluginStatusReason:
    def test_status_distinguishes_unavailable_from_never_fired(
        self, initted_project: Path
    ):
        result = _invoke_in(initted_project, ["plugin", "status"])
        assert result.exit_code == 0, result.output
        # Pick one OC-only plugin and assert the output explains why
        # CC cannot mirror it (capability name in the line).
        for plugin, entry in PLUGIN_MANIFEST.items():
            if entry["claude_code_mirror"] is not None:
                continue
            blockers = cc_unavailable_reasons(plugin)
            if not blockers:
                continue
            # The status output should mention the plugin AND at least
            # one of its blocking capabilities.
            assert plugin in result.output, (
                f"plugin {plugin!r} missing from status output"
            )
            assert any(b in result.output for b in blockers), (
                f"none of {plugin!r}'s blockers {blockers} appeared "
                f"in status output"
            )
            break  # one example is enough

    def test_status_does_not_say_never_fired_for_unavailable(
        self, initted_project: Path,
    ):
        """An OC-only plugin under the Claude Code column must NOT
        say "never fired" — that is the bug A' fixes."""
        result = _invoke_in(initted_project, ["plugin", "status"])
        # Heuristic: find lines that mention a known OC-only plugin
        # AND happen to be in the Claude Code block.
        cc_marker = "Claude Code"
        cc_idx = result.output.find(cc_marker)
        assert cc_idx != -1, "Claude Code section header missing"
        cc_block = result.output[cc_idx:]
        for plugin, entry in PLUGIN_MANIFEST.items():
            if entry["claude_code_mirror"] is not None:
                continue
            if not cc_unavailable_reasons(plugin):
                continue
            # Lines that mention this plugin name inside CC block
            for line in cc_block.splitlines():
                if plugin in line:
                    assert "never fired" not in line, (
                        f"CC block falsely says {plugin!r} 'never "
                        f"fired' when it is structurally unavailable"
                    )


# ===========================================================================
# `allmight plugin matrix` — generates the compatibility table
# ===========================================================================

class TestPluginMatrixCommand:
    def test_matrix_command_exists_and_succeeds(self, initted_project: Path):
        result = _invoke_in(initted_project, ["plugin", "matrix"])
        assert result.exit_code == 0, result.output

    def test_matrix_output_is_markdown_table(self, initted_project: Path):
        result = _invoke_in(initted_project, ["plugin", "matrix"])
        # Header row + separator row + ≥ N plugin rows
        lines = [ln for ln in result.output.splitlines() if ln.startswith("|")]
        assert len(lines) >= 2 + len(PLUGIN_MANIFEST)
        # Separator row of the form |---|---|...
        assert re.match(r"^\|[-:|\s]+\|$", lines[1])

    def test_matrix_lists_every_plugin(self, initted_project: Path):
        result = _invoke_in(initted_project, ["plugin", "matrix"])
        for plugin in PLUGIN_MANIFEST:
            assert plugin in result.output, f"{plugin} missing from matrix"


# ===========================================================================
# README compatibility matrix block is in sync with the manifest
# ===========================================================================

class TestReadmeCompatibilityMatrix:
    """The README has a marker-bounded matrix block. Its content must
    match ``format_compatibility_matrix()`` so users see a current
    truth, not a stale snapshot."""

    @staticmethod
    def _extract_matrix_block(readme: str) -> str:
        start = readme.find("<!-- ALLMIGHT_COMPAT_MATRIX_START -->")
        end = readme.find("<!-- ALLMIGHT_COMPAT_MATRIX_END -->")
        assert start != -1, "README missing ALLMIGHT_COMPAT_MATRIX_START marker"
        assert end != -1, "README missing ALLMIGHT_COMPAT_MATRIX_END marker"
        return readme[start:end]

    def test_readme_has_matrix_markers(self):
        readme = Path(__file__).resolve().parent.parent / "README.md"
        body = readme.read_text()
        self._extract_matrix_block(body)  # raises if markers missing

    def test_readme_matrix_matches_manifest(self):
        readme = Path(__file__).resolve().parent.parent / "README.md"
        block = self._extract_matrix_block(readme.read_text())
        # Every plugin name should appear in the matrix block.
        for plugin in PLUGIN_MANIFEST:
            assert plugin in block, (
                f"README matrix block missing plugin {plugin!r}. "
                f"Regenerate via `allmight plugin matrix`."
            )
        # Each OC-only plugin's at-least-one blocker name appears in
        # the block too (so users see the WHY).
        for plugin, entry in PLUGIN_MANIFEST.items():
            if entry["claude_code_mirror"] is not None:
                continue
            blockers = cc_unavailable_reasons(plugin)
            if not blockers:
                continue
            assert any(b in block for b in blockers), (
                f"README block does not surface a blocker for "
                f"{plugin!r}; expected one of {blockers}"
            )
