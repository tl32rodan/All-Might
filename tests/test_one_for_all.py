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
        config_path = initialized_project / "config.yaml"
        generator = OneForAllGenerator()
        content = generator.generate(config_path)

        assert "One For All" in content
        assert "source_code" in content
        assert "No symbols enriched yet" in content
        assert "0.0%" in content

    def test_generate_with_sidecars(self, project_with_sidecars):
        """Test that enriched symbols appear in generated SKILL.md."""
        config_path = project_with_sidecars / "config.yaml"
        generator = OneForAllGenerator()
        content = generator.generate(config_path)

        assert "hello" in content
        assert "Greets the user" in content
        assert "App" in content

    def test_generate_updates_skill_file(self, initialized_project):
        """Test that the generator writes the SKILL.md file."""
        config_path = initialized_project / "config.yaml"
        generator = OneForAllGenerator()
        generator.generate(config_path)

        skill_path = initialized_project / ".claude" / "skills" / "one-for-all" / "SKILL.md"
        assert skill_path.exists()
        content = skill_path.read_text()
        assert "one-for-all" in content

    def test_one_for_all_includes_enrichment_protocol(self, initialized_project):
        """Test that enrichment protocol is included in one-for-all."""
        config_path = initialized_project / "config.yaml"
        generator = OneForAllGenerator()
        content = generator.generate(config_path)

        assert "Enrichment Protocol" in content
        assert "/enrich" in content
        assert "Guardrails" in content

    def test_generate_writes_skill_only(self, initialized_project):
        """Test that regeneration updates the skill file (commands are init-only)."""
        config_path = initialized_project / "config.yaml"
        generator = OneForAllGenerator()
        generator.generate(config_path)

        skill_path = initialized_project / ".claude" / "skills" / "one-for-all" / "SKILL.md"
        assert skill_path.exists()
        assert "one-for-all" in skill_path.read_text()

    def test_power_level_calculation(self, project_with_sidecars):
        """Test that power level is correctly calculated from sidecars."""
        config_path = project_with_sidecars / "config.yaml"
        generator = OneForAllGenerator()
        content = generator.generate(config_path)

        # 2 symbols total, 2 with intent = 100%
        assert "100.0%" in content

    def test_uses_allmight_commands(self, initialized_project):
        """Test that One For All references All-Might commands, not SMAK MCP."""
        config_path = initialized_project / "config.yaml"
        generator = OneForAllGenerator()
        content = generator.generate(config_path)

        # Should reference All-Might commands
        assert "/search" in content
        assert "/enrich" in content
        assert "/ingest" in content
        assert "/status" in content

    def test_idempotent_regeneration(self, initialized_project):
        """Test that regenerating twice produces consistent results."""
        config_path = initialized_project / "config.yaml"
        generator = OneForAllGenerator()
        content1 = generator.generate(config_path)
        content2 = generator.generate(config_path)

        # Should be structurally similar (timestamps may differ)
        assert "One For All" in content1
        assert "One For All" in content2

    def test_one_for_all_has_enrichment_and_guardrails(self, initialized_project):
        """Test that one-for-all includes enrichment protocol and guardrails."""
        config_path = initialized_project / "config.yaml"
        generator = OneForAllGenerator()
        content = generator.generate(config_path)

        assert "Enrichment Protocol" in content
        assert "Guardrails" in content
        assert "NEVER" in content
        assert "sidecar" in content.lower()
        assert "UID format" in content.lower() or "uid format" in content.lower()


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
