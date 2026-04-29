"""Tests for F5 — structured journal entry schema (v1).

Frontmatter-based YAML wraps the existing freeform body. Entries
without the ``allmight_journal: v1`` sentinel are treated as legacy
freeform — parse returns ``None`` rather than raising, keeping the
migration opt-in.
"""

from __future__ import annotations

import pytest

from allmight.personalities.memory_keeper.journal_schema import (
    JournalEntry,
    ToolCallRecord,
    dump_frontmatter,
    parse_frontmatter,
)


def _sample_entry(**overrides) -> JournalEntry:
    base = dict(
        id="2026-04-18T10:32-a7f3",
        type="trajectory",
        workspace="stdcell",
        trigger="slash_remember",
        input="why does ingest fail on /scratch",
        tool_calls=[
            ToolCallRecord(tool="Bash", args={"cmd": "smak ingest"}, verdict="drift"),
        ],
        output="indexed: 0",
        outcome_label="failure",
        tags=["ingest", "stdcell"],
        supersedes=None,
        created_at="2026-04-18T10:32:00Z",
        body="# 2026-04-18 — ingest on /scratch failed silently\n\nExit 0 but nothing indexed.\n",
    )
    base.update(overrides)
    return JournalEntry(**base)


class TestFrontmatterRoundTrip:

    def test_round_trip_preserves_fields(self):
        entry = _sample_entry()
        parsed = parse_frontmatter(dump_frontmatter(entry))
        assert parsed is not None
        assert parsed.id == entry.id
        assert parsed.type == entry.type
        assert parsed.workspace == entry.workspace
        assert parsed.trigger == entry.trigger
        assert parsed.input == entry.input
        assert parsed.output == entry.output
        assert parsed.outcome_label == entry.outcome_label
        assert parsed.tags == entry.tags
        assert parsed.supersedes is None
        assert parsed.body == entry.body

    def test_round_trip_preserves_tool_calls(self):
        entry = _sample_entry()
        parsed = parse_frontmatter(dump_frontmatter(entry))
        assert parsed is not None
        assert len(parsed.tool_calls) == 1
        call = parsed.tool_calls[0]
        assert call.tool == "Bash"
        assert call.args == {"cmd": "smak ingest"}
        assert call.verdict == "drift"

    def test_dump_starts_with_yaml_delimiter(self):
        out = dump_frontmatter(_sample_entry())
        assert out.startswith("---\n")

    def test_dump_contains_v1_sentinel(self):
        out = dump_frontmatter(_sample_entry())
        assert "allmight_journal: v1" in out

    def test_body_preserved_below_frontmatter(self):
        out = dump_frontmatter(_sample_entry(body="# heading\n\nparagraph\n"))
        assert out.endswith("# heading\n\nparagraph\n")
        # Negative: the body must come AFTER the closing frontmatter fence.
        closing = out.rindex("\n---\n")
        assert out.index("# heading") > closing


class TestLegacyHandling:

    def test_legacy_freeform_returns_none(self):
        legacy = "# 2026-01-01 — an old entry\n\nfreeform text, no frontmatter.\n"
        assert parse_frontmatter(legacy) is None

    def test_frontmatter_without_sentinel_returns_none(self):
        no_sentinel = (
            "---\n"
            "id: some-id\n"
            "type: trajectory\n"
            "---\n"
            "# body\n"
        )
        assert parse_frontmatter(no_sentinel) is None

    def test_corrupt_yaml_returns_none(self):
        corrupt = "---\n:::not yaml:::\n---\n# body\n"
        assert parse_frontmatter(corrupt) is None


class TestValidation:

    def test_rejects_invalid_type_field(self):
        with pytest.raises(ValueError, match="type"):
            JournalEntry(
                id="x", type="not-a-valid-type", workspace="w",
                trigger="slash_remember", input="", tool_calls=[],
                output="", outcome_label="success", tags=[],
                supersedes=None, created_at="2026-01-01T00:00:00Z", body="",
            )

    def test_rejects_invalid_outcome_label(self):
        with pytest.raises(ValueError, match="outcome_label"):
            JournalEntry(
                id="x", type="trajectory", workspace="w",
                trigger="slash_remember", input="", tool_calls=[],
                output="", outcome_label="bogus", tags=[],
                supersedes=None, created_at="2026-01-01T00:00:00Z", body="",
            )

    def test_rejects_invalid_verdict(self):
        with pytest.raises(ValueError, match="verdict"):
            ToolCallRecord(tool="Bash", args={}, verdict="not-a-verdict")
