"""Test Group 1: Project Init — what `allmight init` produces.

TDD: these tests define the TARGET architecture.
One All-Might project with shared enrichment/memory/panorama
and multiple SMAK workspaces under knowledge_graph/.
"""

import pytest

from allmight.detroit_smak.initializer import ProjectInitializer
from allmight.detroit_smak.scanner import ProjectScanner


@pytest.fixture
def project_root(tmp_path):
    """Bare directory to init as an All-Might project."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    return tmp_path


def _init(root):
    scanner = ProjectScanner()
    manifest = scanner.scan(root)
    ProjectInitializer().initialize(manifest)


def _init_with_memory(root):
    """Mirrors what `allmight init` does: project init + memory init."""
    from allmight.memory.initializer import MemoryInitializer

    _init(root)
    MemoryInitializer().initialize(root)


class TestProjectInit:

    def test_creates_claude_md(self, project_root):
        """CLAUDE.md created at project root."""
        _init(project_root)
        assert (project_root / "CLAUDE.md").exists()

    def test_creates_agents_md_symlink(self, project_root):
        """AGENTS.md → CLAUDE.md symlink for OpenCode."""
        _init(project_root)
        agents = project_root / "AGENTS.md"
        assert agents.is_symlink()
        assert agents.resolve() == (project_root / "CLAUDE.md").resolve()

    def test_creates_skill(self, project_root):
        """.claude/skills/one-for-all/SKILL.md created."""
        _init(project_root)
        assert (project_root / ".claude" / "skills" / "one-for-all" / "SKILL.md").exists()

    def test_creates_core_commands(self, project_root):
        """3 core commands: search.md, enrich.md, ingest.md."""
        _init(project_root)
        cmds = project_root / ".claude" / "commands"
        assert (cmds / "search.md").exists()
        assert (cmds / "enrich.md").exists()
        assert (cmds / "ingest.md").exists()
        assert not (cmds / "status.md").exists()

    def test_creates_knowledge_graph_dir(self, project_root):
        """knowledge_graph/ directory created."""
        _init(project_root)
        assert (project_root / "knowledge_graph").is_dir()

    def test_no_config_yaml_at_root(self, project_root):
        """No config.yaml at project root — config.yaml is SMAK's concern."""
        _init(project_root)
        assert not (project_root / "config.yaml").exists()

    def test_claude_md_is_what_not_how(self, project_root):
        """CLAUDE.md references commands but not smak CLI details."""
        _init(project_root)
        content = (project_root / "CLAUDE.md").read_text()
        assert "/search" in content
        assert "/enrich" in content
        # Should NOT contain low-level smak commands
        assert "smak search" not in content
        assert "smak enrich" not in content

    def test_skill_teaches_smak(self, project_root):
        """one-for-all SKILL.md contains smak CLI commands."""
        _init(project_root)
        skill = (project_root / ".claude" / "skills" / "one-for-all" / "SKILL.md").read_text()
        assert "smak search" in skill
        assert "smak enrich" in skill
        assert "smak ingest" in skill

    def test_init_idempotent(self, project_root):
        """Running init twice doesn't break anything."""
        _init(project_root)
        _init(project_root)
        assert (project_root / "CLAUDE.md").exists()
        assert (project_root / ".claude" / "skills" / "one-for-all" / "SKILL.md").exists()
        assert (project_root / "knowledge_graph").is_dir()


class TestProjectInitIncludesMemory:
    """Memory is always initialized as part of `allmight init`."""

    def test_creates_memory_dir(self, project_root):
        """init creates memory/ at project level."""
        _init_with_memory(project_root)
        assert (project_root / "memory").is_dir()
        assert (project_root / "MEMORY.md").exists()

    def test_creates_memory_commands(self, project_root):
        """init adds remember.md and recall.md."""
        _init_with_memory(project_root)
        cmds = project_root / ".claude" / "commands"
        assert (cmds / "remember.md").exists()
        assert (cmds / "recall.md").exists()

    def test_appends_memory_to_skill(self, project_root):
        """init appends memory section to one-for-all SKILL.md."""
        _init_with_memory(project_root)
        skill = (project_root / ".claude" / "skills" / "one-for-all" / "SKILL.md").read_text()
        assert "Memory" in skill
        assert "/remember" in skill
        assert "/recall" in skill

    def test_memory_not_inside_knowledge_graph(self, project_root):
        """memory/ lives at project root, NOT inside knowledge_graph/."""
        _init_with_memory(project_root)
        assert (project_root / "memory").is_dir()
        # Should NOT be per-workspace
        for ws_dir in (project_root / "knowledge_graph").iterdir():
            assert not (ws_dir / "memory").exists()
