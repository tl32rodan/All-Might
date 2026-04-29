"""Tests for F5 — ``allmight memory export`` CLI + JSONL export.

Structured entries (v1 frontmatter) are exported as one JSON object
per line. Legacy freeform entries are skipped with a stderr warning.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from allmight.cli import main
from allmight.personalities.memory_keeper.journal_schema import (
    JournalEntry,
    ToolCallRecord,
    dump_frontmatter,
)
from allmight.personalities.memory_keeper.trajectory_export import export_to_jsonl


def _seed_entry(journal_dir, workspace, entry_id, outcome="success"):
    entry = JournalEntry(
        id=entry_id,
        type="trajectory",
        workspace=workspace,
        trigger="auto",
        input=f"task for {entry_id}",
        tool_calls=[ToolCallRecord(tool="Bash", args={"cmd": "ls"}, verdict="ok")],
        output="done",
        outcome_label=outcome,
        tags=[workspace],
        supersedes=None,
        created_at="2026-04-18T10:00:00Z",
        body=f"# body for {entry_id}\n",
    )
    path = journal_dir / workspace
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{entry_id}.md").write_text(dump_frontmatter(entry))


def _seed_legacy(journal_dir, workspace, name):
    path = journal_dir / workspace
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{name}.md").write_text(f"# {name}\n\nlegacy freeform, no frontmatter.\n")


class TestExportToJsonl:

    def test_emits_one_line_per_structured_entry(self, tmp_path):
        journal = tmp_path / "memory" / "journal"
        _seed_entry(journal, "stdcell", "a")
        _seed_entry(journal, "stdcell", "b")
        _seed_entry(journal, "io_phy", "c")
        out = tmp_path / "out.jsonl"

        skipped = export_to_jsonl(journal, out)

        lines = out.read_text().strip().split("\n")
        assert len(lines) == 3
        ids = {json.loads(line)["id"] for line in lines}
        assert ids == {"a", "b", "c"}
        assert skipped == 0

    def test_skips_legacy_entries(self, tmp_path):
        journal = tmp_path / "memory" / "journal"
        _seed_entry(journal, "stdcell", "a")
        _seed_legacy(journal, "stdcell", "old-freeform")
        out = tmp_path / "out.jsonl"

        skipped = export_to_jsonl(journal, out)

        lines = [line for line in out.read_text().split("\n") if line]
        assert len(lines) == 1
        assert json.loads(lines[0])["id"] == "a"
        assert skipped == 1

    def test_exported_json_has_required_fields(self, tmp_path):
        journal = tmp_path / "memory" / "journal"
        _seed_entry(journal, "stdcell", "a", outcome="failure")
        out = tmp_path / "out.jsonl"

        export_to_jsonl(journal, out)

        record = json.loads(out.read_text().strip())
        for field in (
            "id", "type", "workspace", "trigger", "input",
            "tool_calls", "output", "outcome_label", "tags", "created_at",
        ):
            assert field in record, f"missing field: {field}"
        assert record["outcome_label"] == "failure"
        assert record["tool_calls"][0]["tool"] == "Bash"

    def test_empty_journal_produces_empty_file(self, tmp_path):
        journal = tmp_path / "memory" / "journal"
        journal.mkdir(parents=True)
        out = tmp_path / "out.jsonl"

        skipped = export_to_jsonl(journal, out)

        assert out.read_text() == ""
        assert skipped == 0


class TestCliMemoryExport:

    def test_cli_memory_export_produces_jsonl(self, tmp_path):
        journal = tmp_path / "memory" / "journal"
        _seed_entry(journal, "stdcell", "a")
        out = tmp_path / "out.jsonl"

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["memory", "export", "--format", "jsonl",
             "--root", str(tmp_path), "--out", str(out)],
        )

        assert result.exit_code == 0, result.output
        assert out.exists()
        assert json.loads(out.read_text().strip())["id"] == "a"

    def test_cli_rejects_unsupported_format(self, tmp_path):
        (tmp_path / "memory" / "journal").mkdir(parents=True)
        out = tmp_path / "out.csv"

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["memory", "export", "--format", "csv",
             "--root", str(tmp_path), "--out", str(out)],
        )

        assert result.exit_code != 0
