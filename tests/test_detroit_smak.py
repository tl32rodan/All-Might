"""Tests for Detroit SMAK — scanner and initializer."""

from pathlib import Path
import tempfile
import shutil

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


@pytest.fixture
def smak_path():
    """Return the path to the SMAK submodule."""
    p = Path(__file__).parent.parent / "deps" / "smak"
    if p.exists():
        return p
    return None


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

    def test_scan_smak_demo(self, smak_path):
        """Test scanning SMAK's own demo workspace."""
        if smak_path is None:
            pytest.skip("SMAK submodule not available")
        demo = smak_path / "demo" / "workspace_a"
        if not demo.exists():
            pytest.skip("SMAK demo workspace not found")

        scanner = ProjectScanner()
        manifest = scanner.scan(demo)
        # Name comes from git remote or directory — both are valid
        assert manifest.name in ("workspace_a", "smak")
        assert len(manifest.indices) > 0


class TestProjectInitializer:
    def test_creates_workspace_dir(self, sample_project, smak_path):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=smak_path)

        assert (sample_project / "all-might").is_dir()
        assert (sample_project / "all-might" / "config.yaml").exists()
        assert (sample_project / "all-might" / "enrichment" / "tracker.yaml").exists()
        assert (sample_project / "all-might" / "panorama").is_dir()

    def test_creates_workspace_config(self, sample_project, smak_path):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=smak_path)

        assert (sample_project / "workspace_config.yaml").exists()

    def test_creates_skills(self, sample_project, smak_path):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=smak_path)

        skills_dir = sample_project / ".claude" / "skills"
        assert (skills_dir / "detroit-smak" / "SKILL.md").exists()
        assert (skills_dir / "one-for-all" / "SKILL.md").exists()
        assert (skills_dir / "enrichment" / "SKILL.md").exists()

    def test_does_not_install_smak_skill(self, sample_project, smak_path):
        """Phase 7: agents use All-Might commands, not SMAK MCP tools directly."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=smak_path)

        # SMAK skill should NOT be installed (agents go through All-Might)
        smak_skill = sample_project / ".claude" / "skills" / "smak" / "SKILL.md"
        assert not smak_skill.exists()

    def test_creates_commands(self, sample_project, smak_path):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=smak_path)

        commands_dir = sample_project / ".claude" / "commands"
        # Original commands
        assert (commands_dir / "power-level.md").exists()
        assert (commands_dir / "regenerate.md").exists()
        assert (commands_dir / "panorama.md").exists()
        # Phase 7 new commands
        assert (commands_dir / "search.md").exists()
        assert (commands_dir / "enrich.md").exists()
        assert (commands_dir / "ingest.md").exists()
        assert (commands_dir / "explain.md").exists()
        assert (commands_dir / "graph-report.md").exists()
        assert (commands_dir / "add-index.md").exists()
        assert (commands_dir / "remove-index.md").exists()
        assert (commands_dir / "list-indices.md").exists()

    def test_updates_claude_md(self, sample_project, smak_path):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=smak_path)

        claude_md = sample_project / ".claude" / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert "ALL-MIGHT" in content
        assert "/power-level" in content

    def test_one_for_all_uses_allmight_commands(self, sample_project, smak_path):
        """Phase 7: One For All references All-Might commands, not SMAK MCP."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=smak_path)

        one_for_all = (sample_project / ".claude" / "skills" / "one-for-all" / "SKILL.md").read_text()
        # Should reference All-Might commands
        assert "/search" in one_for_all
        assert "/enrich" in one_for_all
        assert "/explain" in one_for_all
        # Should NOT reference SMAK MCP tools directly
        assert "enrich_symbol(" not in one_for_all
        assert "describe_workspace(" not in one_for_all

    def test_idempotent(self, sample_project, smak_path):
        """Running init twice should not break anything."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=smak_path)
        initializer.initialize(manifest, smak_path=smak_path)

        # Should still work — no errors, files still exist
        assert (sample_project / "all-might" / "config.yaml").exists()
        assert (sample_project / ".claude" / "skills" / "one-for-all" / "SKILL.md").exists()
