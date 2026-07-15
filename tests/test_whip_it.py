"""Tests for the /whip-it working-discipline skill.

These pin four things:
  1. ``write_init_scaffold`` installs the skill, the command, and an
     AGENTS.md primer section pointing at the rule sheet.
  2. The emitted files carry the All-Might marker (refreshable on
     re-init) and the command body carries ``ROUTING_PREAMBLE``.
  3. The rule sheet covers every discipline the skill exists to
     enforce — RED-first TDD, native Unix search, recorded
     agreements, post-compaction re-anchoring, no scope shortcuts.
     Content sanity checks: if they fail, someone gutted the whip
     without updating the agent-facing contract.
  4. The markdown-as-data contract: the body ships as a plain ``.md``
     next to the module so a wheel install carries it.
"""

from __future__ import annotations

import pytest

from allmight.core.markers import ALLMIGHT_MARKER_MD
from allmight.core.personalities import write_init_scaffold
from allmight.core.routing import ROUTING_PREAMBLE
from allmight.core.whip_it import (
    _DATA_DIR,
    _SKILL_BODY_FILE,
    WHIP_IT_SKILL_DESCRIPTION,
    build_whip_it_command_body,
    build_whip_it_skill_body,
    write_whip_it,
)


@pytest.fixture
def project_root(tmp_path):
    return tmp_path


class TestWriteWhipIt:
    """The direct writer — called by ``write_init_scaffold``."""

    def test_writes_skill_md(self, project_root):
        write_whip_it(project_root)
        skill = project_root / ".opencode" / "skills" / "whip-it" / "SKILL.md"
        assert skill.is_file()

    def test_writes_command_md(self, project_root):
        write_whip_it(project_root)
        command = project_root / ".opencode" / "commands" / "whip-it.md"
        assert command.is_file()

    def test_skill_has_marker_and_frontmatter(self, project_root):
        write_whip_it(project_root)
        body = (
            project_root / ".opencode" / "skills" / "whip-it" / "SKILL.md"
        ).read_text()
        assert ALLMIGHT_MARKER_MD in body
        assert "name: whip-it" in body
        # The description is the auto-load trigger — compaction and
        # development-work wording is what makes the model pick it up
        # at the right moments.
        assert "description:" in body
        assert "compaction" in body

    def test_command_has_marker_and_routing_preamble(self, project_root):
        write_whip_it(project_root)
        body = (
            project_root / ".opencode" / "commands" / "whip-it.md"
        ).read_text()
        assert ALLMIGHT_MARKER_MD in body
        # The command re-reads personalities/<active>/... paths, so it
        # must teach <active> resolution like every routed command.
        assert ROUTING_PREAMBLE in body

    def test_bodies_use_active_placeholder_not_literal_names(self, project_root):
        """Same invariant as test_command_body_generic — no baked
        personality name; ``<active>`` is resolved at runtime."""
        write_whip_it(project_root)
        for rel in (
            ".opencode/skills/whip-it/SKILL.md",
            ".opencode/commands/whip-it.md",
        ):
            body = (project_root / rel).read_text()
            assert "personalities/<active>/" in body, rel


class TestRuleSheetContent:
    """Each discipline the whip exists to enforce must stay in the body."""

    def test_tdd_red_stage_is_first_and_evidenced(self):
        body = build_whip_it_skill_body()
        # Wrapped prose — compare against a whitespace-normalised copy.
        flat = " ".join(body.split())
        assert "RED" in flat
        assert "GREEN" in flat
        assert "REFACTOR" in flat
        # The two whip points: test comes BEFORE production code, and
        # the failing run must be shown, not asserted.
        assert "before any production code" in flat
        assert "fail for the right reason" in flat
        # Back-filled tests are explicitly called out as not-TDD.
        assert "not TDD" in flat

    def test_mandates_native_unix_search(self):
        body = build_whip_it_skill_body()
        assert "grep -rn" in body
        assert "find" in body
        # The broken built-ins are named so the model knows what NOT
        # to trust, and the false-negative trap is spelled out.
        assert "Grep / Glob" in body or "Grep/Glob" in body
        assert "NOT evidence" in body

    def test_recorded_agreements_rule_mentions_git_branches(self):
        body = build_whip_it_skill_body()
        assert "git branch" in body
        assert "MEMORY.md" in body
        assert "do not guess" in body.lower()

    def test_post_compaction_reanchor_lists_all_four_reads(self):
        body = build_whip_it_skill_body()
        assert "AGENTS.md" in body
        assert "MEMORY.md" in body
        assert "personalities/<active>/ROLE.md" in body
        assert "understanding/_index.md" in body

    def test_no_shortcuts_covers_scope_files_reporting_output(self):
        body = build_whip_it_skill_body()
        assert "Full scope" in body
        assert "Whole files" in body
        assert "Per-item reporting" in body
        assert "Real output" in body

    def test_self_check_section_exists(self):
        body = build_whip_it_skill_body()
        assert "Self-check on /whip-it" in body

    def test_command_points_at_skill_and_self_check(self):
        body = build_whip_it_command_body()
        assert ".opencode/skills/whip-it/SKILL.md" in body
        assert "Self-check" in body

    def test_description_names_the_disciplines(self):
        # The description doubles as the auto-load trigger and the
        # one-line summary in skill listings.
        assert "TDD-first" in WHIP_IT_SKILL_DESCRIPTION
        assert "Grep/Glob" in WHIP_IT_SKILL_DESCRIPTION
        assert "compaction" in WHIP_IT_SKILL_DESCRIPTION


class TestReInitPreservesUserEdits:
    """Re-init refreshes our files; user-edited (un-markered) files survive."""

    def test_refreshes_markered_skill(self, project_root):
        write_whip_it(project_root)
        skill = project_root / ".opencode" / "skills" / "whip-it" / "SKILL.md"
        skill.write_text(ALLMIGHT_MARKER_MD + "\nCUSTOM WHIP BELOW MARKER\n")
        write_whip_it(project_root)
        refreshed = skill.read_text()
        assert "CUSTOM WHIP BELOW MARKER" not in refreshed
        assert "RED" in refreshed

    def test_preserves_user_edits_without_marker(self, project_root):
        write_whip_it(project_root)
        command = project_root / ".opencode" / "commands" / "whip-it.md"
        command.write_text("# my private whip rules\n")
        write_whip_it(project_root)
        assert command.read_text() == "# my private whip rules\n"


class TestScaffoldIntegration:
    """``write_init_scaffold`` wires the whip into every init."""

    def test_init_scaffold_writes_skill_and_command(self, project_root):
        write_init_scaffold(project_root)
        assert (
            project_root / ".opencode" / "skills" / "whip-it" / "SKILL.md"
        ).is_file()
        assert (
            project_root / ".opencode" / "commands" / "whip-it.md"
        ).is_file()

    def test_primer_contains_working_discipline_section(self):
        from allmight.core.personalities import _AGENTS_MD_FRAMEWORK_PRIMER

        assert "## Working discipline" in _AGENTS_MD_FRAMEWORK_PRIMER
        # The pointer path is the actionable bit.
        assert ".opencode/skills/whip-it/SKILL.md" in _AGENTS_MD_FRAMEWORK_PRIMER
        # The slash-command table row keeps /whip-it discoverable.
        assert "`/whip-it`" in _AGENTS_MD_FRAMEWORK_PRIMER

    def test_composed_agents_md_includes_pointer(self, project_root):
        """After a full init, the rendered AGENTS.md surfaces the whip."""
        from allmight.core.personalities import compose_agents_md

        write_init_scaffold(project_root)
        compose_agents_md(project_root, [], project_name="demo")
        agents_md = (project_root / "AGENTS.md").read_text()
        assert ".opencode/skills/whip-it/SKILL.md" in agents_md
        assert "Working discipline" in agents_md


class TestMarkdownSource:
    """Pin the markdown-as-data contract for the skill body."""

    def test_data_file_exists_alongside_module(self):
        """If the data dir drifts from ``_DATA_DIR``, an editable
        install still passes every other test while a wheel install
        silently breaks — far from this PR."""
        assert _DATA_DIR.is_dir()
        assert (_DATA_DIR / _SKILL_BODY_FILE).is_file()
