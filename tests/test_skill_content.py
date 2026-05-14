"""Test Group 5: Skill and Command Content — SRP layering.

CLAUDE.md = WHAT (high-level, no smak details)
Skills = HOW (low-level, teaches smak CLI)
Commands = HOW (operational guides with smak commands)
"""

import pytest

from allmight.capabilities.database.initializer import ProjectInitializer
from allmight.capabilities.database.scanner import ProjectScanner


@pytest.fixture
def project_root(tmp_path):
    """All-Might project (search-only agent surface)."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    manifest = ProjectScanner().scan(tmp_path)
    ProjectInitializer().initialize(manifest)
    return tmp_path


class TestCommandContent:

    def test_search_command_is_thick_guide(self, project_root):
        """search.md has 'How to execute' and 'What to expect'."""
        content = (project_root / ".opencode" / "commands" / "search.md").read_text()
        assert "How to execute" in content or "## How" in content
        assert "What to expect" in content or "## What" in content

    def test_search_command_has_smak_cli(self, project_root):
        """search.md contains actual smak search command."""
        content = (project_root / ".opencode" / "commands" / "search.md").read_text()
        assert "smak search" in content


class TestDeprecatedCommandsRemoved:
    """``/enrich`` and ``/ingest`` were retired — assert they no longer ship."""

    def test_no_enrich_command(self, project_root):
        assert not (project_root / ".opencode" / "commands" / "enrich.md").exists()

    def test_no_ingest_command(self, project_root):
        assert not (project_root / ".opencode" / "commands" / "ingest.md").exists()


class TestAgentsMdContent:

    def test_agents_md_no_smak_details(self, project_root):
        """AGENTS.md does not contain smak CLI details."""
        content = (project_root / "AGENTS.md").read_text()
        assert "smak search" not in content
        assert "smak enrich" not in content
        assert "smak ingest" not in content

    def test_agents_md_lists_search_command(self, project_root):
        """AGENTS.md lists the surviving slash commands."""
        content = (project_root / "AGENTS.md").read_text()
        assert "/search" in content

    def test_agents_md_no_deprecated_commands(self, project_root):
        """AGENTS.md must not advertise the retired slash commands."""
        content = (project_root / "AGENTS.md").read_text()
        assert "/enrich" not in content
        assert "/ingest" not in content
