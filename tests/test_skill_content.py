"""Test Group 5: Skill and Command Content — SRP layering.

CLAUDE.md = WHAT (high-level, no smak details)
Skills = HOW (low-level, teaches smak CLI)
Commands = HOW (operational guides with smak commands)
"""

import pytest

from allmight.detroit_smak.initializer import ProjectInitializer
from allmight.detroit_smak.scanner import ProjectScanner


@pytest.fixture
def project_root_writable(tmp_path):
    """Writable-mode project for testing full command set."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    manifest = ProjectScanner().scan(tmp_path)
    ProjectInitializer().initialize(manifest, writable=True)
    return tmp_path


@pytest.fixture
def project_root_readonly(tmp_path):
    """Read-only-mode project for testing restricted command set."""
    root = tmp_path / "ro"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("def hello(): pass\n")
    (root / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    manifest = ProjectScanner().scan(root)
    ProjectInitializer().initialize(manifest, writable=False)
    return root


class TestCommandContent:

    def test_commands_are_thick_guides(self, project_root_writable):
        """Each command has 'How to execute' and 'What to expect'."""
        cmds = project_root_writable / ".claude" / "commands"
        for cmd_name in ("search.md", "enrich.md", "ingest.md"):
            content = (cmds / cmd_name).read_text()
            assert "How to execute" in content or "## How" in content, f"{cmd_name} missing HOW section"
            assert "What to expect" in content or "## What" in content, f"{cmd_name} missing WHAT section"

    def test_search_command_has_smak_cli(self, project_root_writable):
        """search.md contains actual smak search command."""
        content = (project_root_writable / ".claude" / "commands" / "search.md").read_text()
        assert "smak search" in content

    def test_enrich_command_has_smak_cli(self, project_root_writable):
        """enrich.md contains actual smak enrich command."""
        content = (project_root_writable / ".claude" / "commands" / "enrich.md").read_text()
        assert "smak enrich" in content

    def test_ingest_command_has_smak_cli(self, project_root_writable):
        """ingest.md contains actual smak ingest command."""
        content = (project_root_writable / ".claude" / "commands" / "ingest.md").read_text()
        assert "smak ingest" in content


class TestCommandContentReadOnly:
    """Read-only mode: only search command is generated."""

    def test_readonly_only_search(self, project_root_readonly):
        """Read-only mode generates only search.md."""
        cmds = project_root_readonly / ".claude" / "commands"
        assert (cmds / "search.md").exists()
        assert not (cmds / "enrich.md").exists()
        assert not (cmds / "ingest.md").exists()

    def test_readonly_search_is_thick_guide(self, project_root_readonly):
        """search.md in read-only mode is still a thick operational guide."""
        content = (project_root_readonly / ".claude" / "commands" / "search.md").read_text()
        assert "How to execute" in content or "## How" in content
        assert "smak search" in content


class TestAgentsMdContent:

    def test_agents_md_no_smak_details(self, project_root_writable):
        """AGENTS.md does not contain smak CLI details."""
        content = (project_root_writable / "AGENTS.md").read_text()
        assert "smak search" not in content
        assert "smak enrich" not in content
        assert "smak ingest" not in content

    def test_agents_md_lists_commands(self, project_root_writable):
        """AGENTS.md lists the slash commands (writable mode)."""
        content = (project_root_writable / "AGENTS.md").read_text()
        assert "/search" in content
        assert "/enrich" in content
        assert "/ingest" in content
