"""Tests for MemoryInitializer and MemoryConfigManager."""

import pytest
import yaml

from allmight.memory.config import MemoryConfigManager
from allmight.memory.initializer import MemoryInitializer


@pytest.fixture
def project_root(tmp_path):
    """A minimal project root with config.yaml."""
    config = {
        "project": {"name": "test-project", "root": str(tmp_path)},
        "indices": [
            {"name": "source_code", "description": "Source", "paths": ["./src"]},
        ],
    }
    with open(tmp_path / "config.yaml", "w") as f:
        yaml.dump(config, f)
    return tmp_path


class TestMemoryInitializer:
    def test_creates_directory_structure(self, project_root):
        MemoryInitializer().initialize(project_root)

        assert (project_root / "memory" / "config.yaml").exists()
        assert (project_root / "memory" / "working" / "MEMORY.md").exists()
        assert (project_root / "memory" / "episodes").is_dir()
        assert (project_root / "memory" / "semantic").is_dir()

    def test_adds_smak_indices(self, project_root):
        MemoryInitializer().initialize(project_root)

        with open(project_root / "config.yaml") as f:
            config = yaml.safe_load(f)

        index_names = [idx["name"] for idx in config["indices"]]
        assert "episodes" in index_names
        assert "semantic_facts" in index_names

    def test_generates_memory_skill(self, project_root):
        MemoryInitializer().initialize(project_root)
        skill_path = project_root / ".claude" / "skills" / "memory" / "SKILL.md"
        assert skill_path.exists()
        content = skill_path.read_text()
        assert "agent-memory" in content
        assert "Working Memory" in content
        assert "Episodic Memory" in content
        assert "Semantic Memory" in content

    def test_generates_commands(self, project_root):
        MemoryInitializer().initialize(project_root)
        commands_dir = project_root / ".claude" / "commands"
        assert (commands_dir / "memory-observe.md").exists()
        assert (commands_dir / "memory-recall.md").exists()
        assert (commands_dir / "memory-update.md").exists()
        assert (commands_dir / "memory-consolidate.md").exists()
        assert (commands_dir / "memory-status.md").exists()

    def test_updates_claude_md(self, project_root):
        # Create existing CLAUDE.md
        (project_root / "CLAUDE.md").write_text("# Test Project\n\nExisting content.\n")

        MemoryInitializer().initialize(project_root)

        content = (project_root / "CLAUDE.md").read_text()
        assert "Agent Memory System" in content
        assert "Existing content." in content  # Preserved

    def test_creates_claude_md_if_missing(self, project_root):
        MemoryInitializer().initialize(project_root)
        assert (project_root / "CLAUDE.md").exists()
        content = (project_root / "CLAUDE.md").read_text()
        assert "Agent Memory System" in content

    def test_idempotent_indices(self, project_root):
        """Running init twice should not duplicate indices."""
        init = MemoryInitializer()
        init.initialize(project_root)
        init.initialize(project_root)

        with open(project_root / "config.yaml") as f:
            config = yaml.safe_load(f)

        episode_indices = [i for i in config["indices"] if i["name"] == "episodes"]
        assert len(episode_indices) == 1

    def test_opencode_agents_md_symlink(self, project_root):
        """Memory init should create AGENTS.md → CLAUDE.md symlink."""
        MemoryInitializer().initialize(project_root)

        agents_md = project_root / "AGENTS.md"
        claude_md = project_root / "CLAUDE.md"
        assert claude_md.exists()
        assert agents_md.is_symlink()
        assert agents_md.resolve() == claude_md.resolve()

    def test_opencode_compat_idempotent(self, project_root):
        """Running memory init twice should not break symlinks."""
        init = MemoryInitializer()
        init.initialize(project_root)
        init.initialize(project_root)

        assert (project_root / "AGENTS.md").is_symlink()


class TestMemoryConfigManager:
    def test_initialize_creates_config(self, tmp_path):
        mgr = MemoryConfigManager(tmp_path)
        cfg = mgr.initialize()
        assert cfg.working_memory_budget == 4000
        assert cfg.decay_rate == 0.05
        assert (tmp_path / "memory" / "config.yaml").exists()

    def test_load_returns_defaults_when_missing(self, tmp_path):
        mgr = MemoryConfigManager(tmp_path)
        cfg = mgr.load()
        assert cfg.working_memory_budget == 4000

    def test_round_trip(self, tmp_path):
        mgr = MemoryConfigManager(tmp_path)
        cfg = mgr.initialize()
        cfg.working_memory_budget = 8000
        cfg.decay_rate = 0.1
        mgr.save(cfg)

        loaded = mgr.load()
        assert loaded.working_memory_budget == 8000
        assert loaded.decay_rate == 0.1
