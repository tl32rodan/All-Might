"""Tests for F1 — L1 handoff-ability.

MEMORY.md is a session-handoff note, not a dump. Hard byte cap, FIFO
bullet spillover, and a dedicated "Next Session Start Here" section
the handoff plugin writes before compaction.
"""

from __future__ import annotations

import stat

from click.testing import CliRunner

from allmight.cli import main
from allmight.memory.initializer import MemoryInitializer
from allmight.memory.l1_rewriter import (
    DEFAULT_MAX_BYTES,
    SENTINEL_MARKER,
    HandoffRewriter,
)


def _big_memory_md() -> str:
    """A MEMORY.md several times over the default cap."""
    sections = ["Project Map", "User Preferences", "Active Goals", "Key Facts"]
    out = [f"<!-- {SENTINEL_MARKER}=4096 -->", "", "# Project Memory", ""]
    for sec in sections:
        out.append(f"## {sec}")
        out.append("")
        for i in range(80):
            # ~64 bytes per bullet × 80 × 4 sections ≈ 20 KB
            out.append(f"- {sec} item {i:03d}: " + ("x" * 40))
        out.append("")
    out.append("## Next Session Start Here")
    out.append("")
    out.append("- resume the ingest investigation")
    return "\n".join(out) + "\n"


class TestHandoffRewriter:

    def test_under_cap_is_unchanged(self):
        md = "# Project Memory\n\n## Project Map\n\n- one bullet\n"
        rewriter = HandoffRewriter()
        trimmed, overflow = rewriter.enforce_cap(md)
        assert trimmed == md
        assert overflow == ""

    def test_cap_enforces_byte_limit(self):
        rewriter = HandoffRewriter()
        trimmed, _overflow = rewriter.enforce_cap(_big_memory_md())
        # The body (excluding the sentinel comment) must fit the cap.
        body = rewriter.body_of(trimmed)
        assert len(body.encode("utf-8")) <= DEFAULT_MAX_BYTES

    def test_cap_preserves_section_headers(self):
        rewriter = HandoffRewriter()
        trimmed, _ = rewriter.enforce_cap(_big_memory_md())
        for sec in ("Project Map", "User Preferences", "Active Goals",
                    "Key Facts", "Next Session Start Here"):
            assert f"## {sec}" in trimmed, f"missing section: {sec}"

    def test_cap_spillover_is_ordered_fifo(self):
        """Oldest bullets (top of each section) go into overflow first."""
        rewriter = HandoffRewriter()
        _trimmed, overflow = rewriter.enforce_cap(_big_memory_md())
        # Overflow carries the earliest bullets — at minimum, the
        # zero-indexed ones from some section.
        assert "item 000" in overflow or "item 001" in overflow

    def test_cap_preserves_next_session_content(self):
        """Next Session Start Here must never be evicted by the cap —
        it's the handoff payload, which is exactly the point."""
        rewriter = HandoffRewriter()
        trimmed, _ = rewriter.enforce_cap(_big_memory_md())
        assert "resume the ingest investigation" in trimmed

    def test_prepend_handoff_replaces_section(self):
        md = (
            "# Project Memory\n\n"
            "## Project Map\n\nfoo\n\n"
            "## Next Session Start Here\n\n- old handoff\n"
        )
        rewriter = HandoffRewriter()
        out = rewriter.prepend_handoff(md, ["new task", "another task"])
        assert "- new task" in out
        assert "- another task" in out
        assert "- old handoff" not in out
        # Other sections are untouched.
        assert "## Project Map" in out
        assert "foo" in out

    def test_prepend_handoff_creates_section_if_missing(self):
        md = "# Project Memory\n\n## Project Map\n\nfoo\n"
        rewriter = HandoffRewriter()
        out = rewriter.prepend_handoff(md, ["bootstrap"])
        assert "## Next Session Start Here" in out
        assert "- bootstrap" in out

    def test_body_of_strips_sentinel(self):
        md = f"<!-- {SENTINEL_MARKER}=4096 -->\n\n# body\n\ntext\n"
        rewriter = HandoffRewriter()
        body = rewriter.body_of(md)
        assert SENTINEL_MARKER not in body
        assert "# body" in body


class TestMemoryMdTemplate:

    def test_memory_md_has_next_session_section(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        content = (tmp_path / "MEMORY.md").read_text()
        assert "## Next Session Start Here" in content

    def test_memory_md_has_sentinel_comment(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        content = (tmp_path / "MEMORY.md").read_text()
        assert SENTINEL_MARKER in content


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

    def test_memory_cap_hook_invokes_allmight_cap(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "memory-cap.sh").read_text()
        assert "allmight memory cap" in content


class TestHandoffWriterPlugin:

    def test_handoff_writer_plugin_exists(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        assert (tmp_path / ".opencode" / "plugins" / "handoff-writer.ts").exists()

    def test_handoff_writer_subscribes_to_compacting(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        content = (
            tmp_path / ".opencode" / "plugins" / "handoff-writer.ts"
        ).read_text()
        # Top-level hook key with correct two-arg signature.
        assert (
            '"experimental.session.compacting":' in content
            and "async (input: any, output: any)" in content
        )

    def test_handoff_writer_observes_tool_outcomes(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        content = (
            tmp_path / ".opencode" / "plugins" / "handoff-writer.ts"
        ).read_text()
        assert "tool.execute.after" in content

    def test_handoff_writer_writes_to_memory_md(self, tmp_path):
        MemoryInitializer().initialize(tmp_path)
        content = (
            tmp_path / ".opencode" / "plugins" / "handoff-writer.ts"
        ).read_text()
        assert "MEMORY.md" in content
        # Must not pollute the live chat — handoff is a disk write only.
        assert "output.parts.unshift" not in content
        # Negative: no stale msg.content mutations.
        assert "msg.content =" not in content


class TestCliMemoryCap:

    def test_cli_cap_trims_in_place(self, tmp_path):
        memory_md = tmp_path / "MEMORY.md"
        memory_md.write_text(_big_memory_md())

        runner = CliRunner()
        result = runner.invoke(main, ["memory", "cap", str(memory_md)])

        assert result.exit_code == 0, result.output
        trimmed = memory_md.read_text()
        rewriter = HandoffRewriter()
        body = rewriter.body_of(trimmed)
        assert len(body.encode("utf-8")) <= DEFAULT_MAX_BYTES

    def test_cli_cap_spills_overflow_to_journal(self, tmp_path):
        memory_md = tmp_path / "MEMORY.md"
        memory_md.write_text(_big_memory_md())
        (tmp_path / "memory" / "journal" / "general").mkdir(parents=True)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["memory", "cap", str(memory_md),
             "--spill-to", str(tmp_path / "memory" / "journal" / "general")],
        )

        assert result.exit_code == 0, result.output
        spills = list((tmp_path / "memory" / "journal" / "general").glob("*l1-spill*.md"))
        assert len(spills) == 1
        assert "item 000" in spills[0].read_text() or "item 001" in spills[0].read_text()

    def test_cli_cap_no_spill_when_under_cap(self, tmp_path):
        memory_md = tmp_path / "MEMORY.md"
        memory_md.write_text("# tiny\n\n## Project Map\n\n- one\n")
        (tmp_path / "memory" / "journal" / "general").mkdir(parents=True)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["memory", "cap", str(memory_md),
             "--spill-to", str(tmp_path / "memory" / "journal" / "general")],
        )

        assert result.exit_code == 0
        spills = list((tmp_path / "memory" / "journal" / "general").glob("*l1-spill*.md"))
        assert spills == []
