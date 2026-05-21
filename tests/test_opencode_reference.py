"""Tests for the bundled OpenCode reference + /opencode-ref skill.

These pin three things:
  1. ``write_init_scaffold`` writes the cheat-sheet bundle, the skill,
     and an AGENTS.md primer section pointing at the bundle.
  2. The bundled content carries the All-Might marker (so re-init can
     refresh it) and mentions the pinned OpenCode version.
  3. The cheat-sheets cover the wrong-shape traps the Python suite is
     blind to — events vs hooks, ``output.parts.unshift``, subagent vs
     primary.  These are content sanity checks: if they fail, someone
     gutted the bundle without updating the agent-facing reminder.
"""

from __future__ import annotations

import pytest

from allmight.core.markers import ALLMIGHT_MARKER_MD
from allmight.core.opencode_reference import (
    OPENCODE_VERSION,
    write_opencode_reference,
)
from allmight.core.personalities import write_init_scaffold


@pytest.fixture
def project_root(tmp_path):
    return tmp_path


class TestWriteOpencodeReference:
    """The direct writer — called by ``write_init_scaffold``."""

    def test_creates_reference_directory(self, project_root):
        write_opencode_reference(project_root)
        ref_dir = project_root / ".opencode" / "reference" / "opencode"
        assert ref_dir.is_dir()

    def test_writes_all_cheat_sheets(self, project_root):
        write_opencode_reference(project_root)
        ref_dir = project_root / ".opencode" / "reference" / "opencode"
        for name in (
            "README.md",
            "plugins.md",
            "agents.md",
            "skills-commands.md",
            "config.md",
        ):
            assert (ref_dir / name).is_file(), f"missing {name}"

    def test_all_cheat_sheets_carry_marker(self, project_root):
        write_opencode_reference(project_root)
        ref_dir = project_root / ".opencode" / "reference" / "opencode"
        for path in ref_dir.iterdir():
            assert ALLMIGHT_MARKER_MD in path.read_text(), (
                f"{path.name} missing All-Might marker — re-init "
                "will not refresh it"
            )

    def test_readme_pins_opencode_version(self, project_root):
        write_opencode_reference(project_root)
        readme = (
            project_root / ".opencode" / "reference" / "opencode" / "README.md"
        ).read_text()
        assert OPENCODE_VERSION in readme

    def test_plugins_md_distinguishes_events_from_hooks(self, project_root):
        """The single most frequent runtime regression in our plugins."""
        write_opencode_reference(project_root)
        plugins = (
            project_root / ".opencode" / "reference" / "opencode" / "plugins.md"
        ).read_text()
        assert "chat.message" in plugins
        assert "output.parts.unshift" in plugins
        # The doc must explicitly contrast the two surfaces, not just
        # mention them — that contrast is the whole reason the file
        # exists.
        assert "event" in plugins.lower()
        assert "hook" in plugins.lower()

    def test_agents_md_documents_subagent_vs_primary(self, project_root):
        write_opencode_reference(project_root)
        agents = (
            project_root / ".opencode" / "reference" / "opencode" / "agents.md"
        ).read_text()
        assert "subagent" in agents
        assert "primary" in agents
        # The {file:...} pointer convention is what keeps ROLE.md as
        # source of truth.
        assert "{file:" in agents


class TestOpencodeRefSkill:
    """The /opencode-ref skill — auto-loadable pointer at the bundle."""

    def test_writes_skill_md(self, project_root):
        write_opencode_reference(project_root)
        skill = (
            project_root
            / ".opencode"
            / "skills"
            / "opencode-ref"
            / "SKILL.md"
        )
        assert skill.is_file()

    def test_skill_has_marker_and_frontmatter(self, project_root):
        write_opencode_reference(project_root)
        body = (
            project_root
            / ".opencode"
            / "skills"
            / "opencode-ref"
            / "SKILL.md"
        ).read_text()
        assert ALLMIGHT_MARKER_MD in body
        assert "name: opencode-ref" in body
        # The description is the auto-load trigger — must mention
        # .opencode/ so the model picks it up at the right moments.
        assert "description:" in body
        assert ".opencode/" in body

    def test_skill_points_at_reference_dir(self, project_root):
        write_opencode_reference(project_root)
        body = (
            project_root
            / ".opencode"
            / "skills"
            / "opencode-ref"
            / "SKILL.md"
        ).read_text()
        assert ".opencode/reference/opencode/" in body


class TestReInitPreservesUserEdits:
    """Re-init refreshes our files; user-edited (un-markered) files survive."""

    def test_refreshes_markered_files(self, project_root):
        write_opencode_reference(project_root)
        readme = (
            project_root / ".opencode" / "reference" / "opencode" / "README.md"
        )
        # User leaves the marker in place but appends nothing — re-init
        # should overwrite back to the canonical content.
        readme.write_text(
            ALLMIGHT_MARKER_MD + "\nCUSTOM PARAGRAPH BELOW MARKER\n"
        )
        write_opencode_reference(project_root)
        refreshed = readme.read_text()
        assert "CUSTOM PARAGRAPH BELOW MARKER" not in refreshed
        assert OPENCODE_VERSION in refreshed

    def test_preserves_user_edits_without_marker(self, project_root):
        write_opencode_reference(project_root)
        plugins = (
            project_root / ".opencode" / "reference" / "opencode" / "plugins.md"
        )
        # User deletes the marker (signal: "this is mine now").
        plugins.write_text("# my private plugin notes\n")
        write_opencode_reference(project_root)
        assert plugins.read_text() == "# my private plugin notes\n"


class TestScaffoldIntegration:
    """``write_init_scaffold`` wires the reference into every init."""

    def test_init_scaffold_writes_reference(self, project_root):
        write_init_scaffold(project_root)
        ref_dir = project_root / ".opencode" / "reference" / "opencode"
        assert ref_dir.is_dir()
        assert (ref_dir / "README.md").is_file()
        assert (ref_dir / "plugins.md").is_file()

    def test_init_scaffold_writes_opencode_ref_skill(self, project_root):
        write_init_scaffold(project_root)
        skill = (
            project_root
            / ".opencode"
            / "skills"
            / "opencode-ref"
            / "SKILL.md"
        )
        assert skill.is_file()


class TestAgentsMdPrimerSection:
    """The primer ships the OpenCode pointer so the agent sees it early."""

    def test_primer_contains_opencode_reference_section(self):
        from allmight.core.personalities import _AGENTS_MD_FRAMEWORK_PRIMER

        # Section header — must be present so the agent can navigate to it.
        assert "## OpenCode reference" in _AGENTS_MD_FRAMEWORK_PRIMER
        # The pointer path is the actionable bit — without it the
        # section is just a label.
        assert ".opencode/reference/opencode/" in _AGENTS_MD_FRAMEWORK_PRIMER

    def test_composed_agents_md_includes_pointer(self, project_root):
        """After a full init, the rendered AGENTS.md surfaces the bundle."""
        from allmight.core.personalities import compose_agents_md

        write_init_scaffold(project_root)
        compose_agents_md(project_root, [], project_name="demo")
        agents_md = (project_root / "AGENTS.md").read_text()
        assert ".opencode/reference/opencode/" in agents_md
        assert "OpenCode reference" in agents_md
