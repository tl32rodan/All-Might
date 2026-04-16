"""Test Group 5: Skill and Command Content — SRP layering.

CLAUDE.md = WHAT (high-level, no smak details)
Skills = HOW (low-level, teaches smak CLI)
Commands = HOW (operational guides with smak commands)
"""

import pytest

from allmight.detroit_smak.initializer import ProjectInitializer
from allmight.detroit_smak.scanner import ProjectScanner


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    manifest = ProjectScanner().scan(tmp_path)
    ProjectInitializer().initialize(manifest)
    return tmp_path


class TestCommandContent:

    def test_commands_are_thick_guides(self, project_root):
        """Each command has 'How to execute' and 'What to expect'."""
        cmds = project_root / ".claude" / "commands"
        for cmd_name in ("search.md", "enrich.md", "ingest.md"):
            content = (cmds / cmd_name).read_text()
            assert "How to execute" in content or "## How" in content, f"{cmd_name} missing HOW section"
            assert "What to expect" in content or "## What" in content, f"{cmd_name} missing WHAT section"

    def test_search_command_has_smak_cli(self, project_root):
        """search.md contains actual smak search command."""
        content = (project_root / ".claude" / "commands" / "search.md").read_text()
        assert "smak search" in content

    def test_enrich_command_has_smak_cli(self, project_root):
        """enrich.md contains actual smak enrich command."""
        content = (project_root / ".claude" / "commands" / "enrich.md").read_text()
        assert "smak enrich" in content

    def test_ingest_command_has_smak_cli(self, project_root):
        """ingest.md contains actual smak ingest command."""
        content = (project_root / ".claude" / "commands" / "ingest.md").read_text()
        assert "smak ingest" in content


class TestClaudeMdContent:

    def test_claude_md_no_smak_details(self, project_root):
        """CLAUDE.md does not contain smak CLI details."""
        content = (project_root / "CLAUDE.md").read_text()
        assert "smak search" not in content
        assert "smak enrich" not in content
        assert "smak ingest" not in content

    def test_claude_md_lists_commands(self, project_root):
        """CLAUDE.md lists the slash commands."""
        content = (project_root / "CLAUDE.md").read_text()
        assert "/search" in content
        assert "/enrich" in content
        assert "/ingest" in content
