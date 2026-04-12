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
        initializer.initialize(manifest, smak_path=None)

        assert (sample_project / "all-might").is_dir()
        assert (sample_project / "all-might" / "config.yaml").exists()
        assert (sample_project / "all-might" / "enrichment" / "tracker.yaml").exists()
        assert (sample_project / "all-might" / "panorama").is_dir()

    def test_creates_workspace_config(self, sample_project):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        assert (sample_project / "workspace_config.yaml").exists()

    def test_creates_skills(self, sample_project):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        skills_dir = sample_project / ".claude" / "skills"
        assert (skills_dir / "detroit-smak" / "SKILL.md").exists()
        assert (skills_dir / "one-for-all" / "SKILL.md").exists()
        assert (skills_dir / "enrichment" / "SKILL.md").exists()

    def test_does_not_install_smak_skill(self, sample_project):
        """Phase 7: agents use All-Might commands, not SMAK MCP tools directly."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        # SMAK skill should NOT be installed (agents go through All-Might)
        smak_skill = sample_project / ".claude" / "skills" / "smak" / "SKILL.md"
        assert not smak_skill.exists()

    def test_creates_commands(self, sample_project):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

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

    def test_updates_claude_md(self, sample_project):
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        claude_md = sample_project / ".claude" / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert "ALL-MIGHT" in content
        assert "/power-level" in content

    def test_one_for_all_uses_allmight_commands(self, sample_project):
        """Phase 7: One For All references All-Might commands, not SMAK MCP."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        one_for_all = (sample_project / ".claude" / "skills" / "one-for-all" / "SKILL.md").read_text()
        # Should reference All-Might commands
        assert "/search" in one_for_all
        assert "/enrich" in one_for_all
        assert "/explain" in one_for_all
        # Should NOT reference SMAK MCP tools directly
        assert "enrich_symbol(" not in one_for_all
        assert "describe_workspace(" not in one_for_all

    def test_workspace_config_has_uri(self, sample_project):
        """Test that generated workspace_config.yaml includes uri for each index."""
        import yaml

        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        with open(sample_project / "workspace_config.yaml") as f:
            config = yaml.safe_load(f)

        for idx in config["indices"]:
            assert "uri" in idx, f"Index '{idx['name']}' missing uri"
            assert idx["uri"].startswith("./smak/")

    def test_sos_skill_bundled(self, sample_project):
        """Test that SOS skill is generated from bundled content (no smak_path needed)."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        manifest.has_path_env = True  # Simulate SOS environment

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        sos_skill = sample_project / ".claude" / "skills" / "sos-smak" / "SKILL.md"
        assert sos_skill.exists()
        content = sos_skill.read_text()
        assert "CliosoftSOS" in content
        assert "DDI_ROOT_PATH" in content

    def test_claude_md_has_guardrails(self, sample_project):
        """Test that CLAUDE.md contains guardrails against hand-editing."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        claude_md = sample_project / ".claude" / "CLAUDE.md"
        content = claude_md.read_text()
        assert "NEVER" in content
        assert "sidecar" in content.lower()
        assert "workspace_config" in content

    def test_claude_md_explains_smak(self, sample_project):
        """Test that CLAUDE.md explains what SMAK is."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        claude_md = sample_project / ".claude" / "CLAUDE.md"
        content = claude_md.read_text()
        assert "What is SMAK" in content
        assert "semantic search" in content.lower() or "vector store" in content.lower()

    def test_sos_skill_enrichment_crossref(self, sample_project):
        """Test that SOS skill cross-references the enrichment protocol."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        manifest.has_path_env = True  # Simulate SOS environment

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        sos_skill = (sample_project / ".claude" / "skills" / "sos-smak" / "SKILL.md").read_text()
        assert "/enrich" in sos_skill
        assert "enrichment-protocol" in sos_skill

    def test_claude_md_has_standalone_hub_architecture(self, sample_project):
        """Test that CLAUDE.md describes the standalone hub architecture."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        claude_md = sample_project / ".claude" / "CLAUDE.md"
        content = claude_md.read_text()
        assert "standalone" in content.lower()
        assert "workspace_config.yaml" in content
        assert "smak/" in content or "FAISS" in content

    def test_sos_skill_has_standalone_hub_and_config_management(self, sample_project):
        """Test that SOS skill includes standalone hub and workspace_config guidance."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        manifest.has_path_env = True

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        sos_skill = (sample_project / ".claude" / "skills" / "sos-smak" / "SKILL.md").read_text()
        assert "STANDALONE HUB" in sos_skill
        assert "WORKSPACE_CONFIG" in sos_skill
        assert "add-index" in sos_skill
        assert "frozen" in sos_skill.lower() or "snapshot" in sos_skill.lower()

    def test_claude_md_has_online_vs_vc_awareness(self, sample_project):
        """Test that CLAUDE.md explains online-only indexing and VC log verification."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        claude_md = sample_project / ".claude" / "CLAUDE.md"
        content = claude_md.read_text()
        assert "online" in content.lower()
        assert "sos log" in content.lower() or "revision log" in content.lower()

    def test_sos_skill_has_online_first_workflow(self, sample_project):
        """Test that SOS skill documents the online-first + log verification pattern."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        manifest.has_path_env = True

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)

        sos_skill = (sample_project / ".claude" / "skills" / "sos-smak" / "SKILL.md").read_text()
        assert "online" in sos_skill.lower()
        assert "sos log" in sos_skill.lower()
        assert "revision log" in sos_skill.lower()
        assert "ONLINE-FIRST" in sos_skill

    def test_idempotent(self, sample_project):
        """Running init twice should not break anything."""
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)

        initializer = ProjectInitializer()
        initializer.initialize(manifest, smak_path=None)
        initializer.initialize(manifest, smak_path=None)

        # Should still work — no errors, files still exist
        assert (sample_project / "all-might" / "config.yaml").exists()
        assert (sample_project / ".claude" / "skills" / "one-for-all" / "SKILL.md").exists()
