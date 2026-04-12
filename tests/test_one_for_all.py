"""Tests for One For All — SKILL.md generator."""

from pathlib import Path

import yaml
import pytest

from allmight.detroit_smak.scanner import ProjectScanner
from allmight.detroit_smak.initializer import ProjectInitializer
from allmight.one_for_all.generator import OneForAllGenerator
from allmight.one_for_all.quirks import get_quirk, get_agent_notes


@pytest.fixture
def initialized_project(tmp_path):
    """Create a project that has been initialized by Detroit SMAK."""
    # Create project structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\nclass App: pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

    # Scan and initialize
    scanner = ProjectScanner()
    manifest = scanner.scan(tmp_path)
    initializer = ProjectInitializer()

    initializer.initialize(manifest, smak_path=None)

    return tmp_path


@pytest.fixture
def project_with_sidecars(initialized_project):
    """Add some sidecar files to simulate enrichment."""
    src = initialized_project / "src"

    sidecar_data = {
        "symbols": [
            {
                "name": "hello",
                "intent": "Greets the user with a friendly message",
                "relations": ["./tests/test_main.py::test_hello"],
            },
            {
                "name": "App",
                "intent": "Main application class",
                "relations": [],
            },
        ]
    }

    sidecar_path = src / ".main.py.sidecar.yaml"
    with open(sidecar_path, "w") as f:
        yaml.dump(sidecar_data, f)

    return initialized_project


class TestOneForAllGenerator:
    def test_generate_fresh_project(self, initialized_project):
        """Test generating SKILL.md for a project with no enrichment."""
        config_path = initialized_project / "all-might" / "config.yaml"
        generator = OneForAllGenerator()
        content = generator.generate(config_path)

        assert "One For All" in content
        assert "source_code" in content
        assert "No symbols have been enriched yet" in content
        assert "0.0%" in content

    def test_generate_with_sidecars(self, project_with_sidecars):
        """Test that enriched symbols appear in generated SKILL.md."""
        config_path = project_with_sidecars / "all-might" / "config.yaml"
        generator = OneForAllGenerator()
        content = generator.generate(config_path)

        assert "hello" in content
        assert "Greets the user" in content
        assert "App" in content

    def test_generate_updates_skill_file(self, initialized_project):
        """Test that the generator writes the SKILL.md file."""
        config_path = initialized_project / "all-might" / "config.yaml"
        generator = OneForAllGenerator()
        generator.generate(config_path)

        skill_path = initialized_project / ".claude" / "skills" / "one-for-all" / "SKILL.md"
        assert skill_path.exists()
        content = skill_path.read_text()
        assert "one-for-all" in content

    def test_generate_updates_enrichment_skill(self, initialized_project):
        """Test that enrichment protocol is also regenerated."""
        config_path = initialized_project / "all-might" / "config.yaml"
        generator = OneForAllGenerator()
        generator.generate(config_path)

        skill_path = initialized_project / ".claude" / "skills" / "enrichment" / "SKILL.md"
        assert skill_path.exists()
        content = skill_path.read_text()
        assert "enrichment-protocol" in content

    def test_generate_updates_commands(self, initialized_project):
        """Test that command files are regenerated."""
        config_path = initialized_project / "all-might" / "config.yaml"
        generator = OneForAllGenerator()
        generator.generate(config_path)

        commands_dir = initialized_project / ".claude" / "commands"
        assert (commands_dir / "power-level.md").exists()
        assert (commands_dir / "regenerate.md").exists()
        assert (commands_dir / "panorama.md").exists()

    def test_power_level_calculation(self, project_with_sidecars):
        """Test that power level is correctly calculated from sidecars."""
        config_path = project_with_sidecars / "all-might" / "config.yaml"
        generator = OneForAllGenerator()
        content = generator.generate(config_path)

        # 2 symbols total, 2 with intent = 100%
        assert "100.0%" in content

    def test_uses_allmight_commands(self, initialized_project):
        """Test that One For All references All-Might commands, not SMAK MCP."""
        config_path = initialized_project / "all-might" / "config.yaml"
        generator = OneForAllGenerator()
        content = generator.generate(config_path)

        # Should reference All-Might commands
        assert "/search" in content
        assert "/enrich" in content
        assert "/explain" in content
        # Should NOT reference SMAK MCP tools directly
        assert "enrich_symbol(" not in content
        assert "describe_workspace(" not in content

    def test_idempotent_regeneration(self, initialized_project):
        """Test that regenerating twice produces consistent results."""
        config_path = initialized_project / "all-might" / "config.yaml"
        generator = OneForAllGenerator()
        content1 = generator.generate(config_path)
        content2 = generator.generate(config_path)

        # Should be structurally similar (timestamps may differ)
        assert "One For All" in content1
        assert "One For All" in content2

    def test_enrichment_skill_has_schema_reference(self, initialized_project):
        """Test that enrichment skill contains sidecar schema docs and anti-edit warning."""
        config_path = initialized_project / "all-might" / "config.yaml"
        generator = OneForAllGenerator()
        generator.generate(config_path)

        skill_path = initialized_project / ".claude" / "skills" / "enrichment" / "SKILL.md"
        content = skill_path.read_text()
        assert "Sidecar File Schema" in content
        assert "Do NOT edit" in content
        assert "UID Format" in content

    def test_one_for_all_explains_smak(self, initialized_project):
        """Test that one-for-all skill explains SMAK philosophy."""
        config_path = initialized_project / "all-might" / "config.yaml"
        generator = OneForAllGenerator()
        content = generator.generate(config_path)

        assert "Semantic Mesh Augmented Kernel" in content
        assert "hand-edit" in content.lower() or "hand-edit sidecar" in content.lower()

    def test_one_for_all_has_standalone_hub_note(self, initialized_project):
        """Test that one-for-all notes the standalone hub architecture."""
        config_path = initialized_project / "all-might" / "config.yaml"
        generator = OneForAllGenerator()
        content = generator.generate(config_path)

        assert "standalone hub" in content.lower()
        assert "Sidecar files live beside the source files" in content


class TestQuirks:
    def test_get_known_quirk(self):
        quirk = get_quirk("claude-code")
        assert quirk is not None
        assert quirk.supports_skills is True
        assert quirk.context_window == 200_000

    def test_get_unknown_quirk(self):
        quirk = get_quirk("unknown-agent")
        assert quirk is None

    def test_agent_notes(self):
        notes = get_agent_notes("claude-code")
        assert len(notes) > 0
        assert any("skill" in n.lower() for n in notes)

    def test_agent_notes_unknown(self):
        notes = get_agent_notes("unknown")
        assert len(notes) == 1
        assert "Unknown" in notes[0]
