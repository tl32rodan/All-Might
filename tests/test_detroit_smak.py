"""Tests for Detroit SMAK — scanner and initializer."""

import pytest

from allmight.detroit_smak.scanner import ProjectScanner
from allmight.detroit_smak.initializer import ProjectInitializer


@pytest.fixture
def sample_project(tmp_path):
    """Create a minimal Python project structure for testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "src" / "utils.py").write_text("class Helper: pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_hello(): pass\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("# Project\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    return tmp_path


class TestProjectScanner:
    def test_scan_detects_languages(self, sample_project):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        assert "Python" in manifest.languages

    def test_scan_detects_frameworks(self, sample_project):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        assert "Python" in manifest.frameworks

    def test_scan_detects_directories(self, sample_project):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        assert "src" in manifest.directory_map
        assert "tests" in manifest.directory_map
        assert "docs" in manifest.directory_map

    def test_scan_proposes_indices(self, sample_project):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        index_names = [idx.name for idx in manifest.indices]
        assert "source_code" in index_names
        assert "tests" in index_names
        assert "documentation" in index_names

    def test_scan_proposes_uri(self, sample_project):
        """Test that scanner proposes uri for each index."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        for idx in manifest.indices:
            assert idx.uri is not None
            assert idx.uri.startswith("./smak/")


class TestProjectInitializer:
    def test_creates_workspace_dir(self, sample_project):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest)

        assert (sample_project / "knowledge_graph").is_dir()

    def test_creates_knowledge_graph_dir(self, sample_project):
        """knowledge_graph/ is created — SMAK workspaces live here."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest)

        assert (sample_project / "knowledge_graph").is_dir()
        # config.yaml lives per-workspace, NOT at project root
        assert not (sample_project / "config.yaml").exists()

    def test_does_not_install_smak_skill(self, sample_project):
        """Phase 7: agents use All-Might commands, not SMAK MCP tools directly."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest)

        # SMAK skill should NOT be installed (agents go through All-Might)
        smak_skill = sample_project / ".claude" / "skills" / "smak" / "SKILL.md"
        assert not smak_skill.exists()

    def test_creates_commands(self, sample_project):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, writable=True)

        commands_dir = sample_project / ".claude" / "commands"
        # Core commands: search, enrich, ingest (writable mode)
        assert (commands_dir / "search.md").exists()
        assert (commands_dir / "enrich.md").exists()
        assert (commands_dir / "ingest.md").exists()
        assert not (commands_dir / "status.md").exists()
        # Old commands should NOT exist
        assert not (commands_dir / "explain.md").exists()
        assert not (commands_dir / "power-level.md").exists()
        assert not (commands_dir / "regenerate.md").exists()

    def test_updates_claude_md(self, sample_project):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest)

        claude_md = sample_project / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert "ALL-MIGHT" in content
        assert "/search" in content

    def test_claude_md_is_what_not_how(self, sample_project):
        """CLAUDE.md should say WHAT you can do, not HOW (that's in commands)."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest)

        claude_md = sample_project / "CLAUDE.md"
        content = claude_md.read_text()
        # Should NOT contain SMAK implementation details
        assert "smak search" not in content
        assert "smak enrich" not in content

    def test_claude_md_has_getting_started(self, sample_project):
        """Test that CLAUDE.md has getting started steps (writable mode)."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, writable=True)

        claude_md = sample_project / "CLAUDE.md"
        content = claude_md.read_text()
        assert "Getting Started" in content
        assert "/ingest" in content

    def test_claude_md_has_online_vs_vc_awareness(self, sample_project):
        """Test that CLAUDE.md lists all commands (writable mode)."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, writable=True)

        claude_md = sample_project / "CLAUDE.md"
        content = claude_md.read_text()
        assert "/search" in content
        assert "/enrich" in content

    def test_idempotent(self, sample_project):
        """Running init twice should not break anything."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest)
        initializer.initialize(manifest)

        # Should still work — no errors, files still exist
        assert (sample_project / "knowledge_graph").is_dir()

    def test_opencode_agents_md_symlink(self, sample_project):
        """AGENTS.md symlink should be created pointing to CLAUDE.md."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        ProjectInitializer().initialize(manifest)

        agents_md = sample_project / "AGENTS.md"
        claude_md = sample_project / "CLAUDE.md"
        assert claude_md.exists()
        assert agents_md.is_symlink()
        assert agents_md.resolve() == claude_md.resolve()

    def test_opencode_dotdir_created(self, sample_project):
        """.opencode/ directory created with symlinks into .claude/."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        ProjectInitializer().initialize(manifest)

        assert (sample_project / ".opencode").is_dir()

    def test_opencode_skills_symlink(self, sample_project):
        """.opencode/skills/ symlinks to .claude/skills/."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        ProjectInitializer().initialize(manifest)

        target = sample_project / ".opencode" / "skills"
        source = sample_project / ".claude" / "skills"
        assert target.is_symlink()
        assert target.resolve() == source.resolve()

    def test_opencode_commands_symlink(self, sample_project):
        """.opencode/commands/ symlinks to .claude/commands/."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        ProjectInitializer().initialize(manifest)

        target = sample_project / ".opencode" / "commands"
        source = sample_project / ".claude" / "commands"
        assert target.is_symlink()
        assert target.resolve() == source.resolve()

    def test_opencode_compat_idempotent(self, sample_project):
        """Running init twice should not duplicate or break symlinks."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        init = ProjectInitializer()
        init.initialize(manifest)
        init.initialize(manifest)

        assert (sample_project / "AGENTS.md").is_symlink()

    def test_enrich_command_sos_has_dry_run(self, sample_project):
        """SOS enrich.md references --dry-run and cliosoft-sos MCP tools."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        manifest.has_path_env = True

        ProjectInitializer().initialize(manifest, writable=True)

        content = (sample_project / ".claude" / "commands" / "enrich.md").read_text()
        assert "--dry-run" in content
        assert "sos_checkout" in content
        assert "sos_checkin" in content

    def test_enrich_command_non_sos_unchanged(self, sample_project):
        """Non-SOS enrich.md does NOT reference --dry-run or cliosoft-sos."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        manifest.has_path_env = False

        ProjectInitializer().initialize(manifest, writable=True)

        content = (sample_project / ".claude" / "commands" / "enrich.md").read_text()
        assert "--dry-run" not in content
        assert "sos_checkout" not in content
        assert "smak enrich" in content

