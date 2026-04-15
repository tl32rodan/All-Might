"""Tests for MemoryInitializer and MemoryConfigManager."""

import pytest
import yaml

from allmight.memory.config import MemoryConfigManager
from allmight.memory.initializer import MemoryInitializer


@pytest.fixture
def project_root(tmp_path):
    """A minimal project root with config.yaml and one-for-all SKILL.md."""
    config = {
        "project": {"name": "test-project", "root": str(tmp_path)},
        "indices": [
            {"name": "source_code", "description": "Source", "paths": ["./src"]},
        ],
    }
    with open(tmp_path / "config.yaml", "w") as f:
        yaml.dump(config, f)
    # Create the one-for-all SKILL.md that memory init appends to
    skill_dir = tmp_path / ".claude" / "skills" / "one-for-all"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: one-for-all\n---\n\n# One For All\n")
    return tmp_path


class TestMemoryInitializer:
    def test_creates_directory_structure(self, project_root):
        MemoryInitializer().initialize(project_root)

        assert (project_root / "memory" / "config.yaml").exists()
        assert (project_root / "memory" / "working" / "MEMORY.md").exists()
        assert (project_root / "memory" / "episodes").is_dir()
        assert (project_root / "memory" / "semantic").is_dir()

    def test_stores_in_memory_config(self, project_root):
        """Memory stores should be in memory/config.yaml, NOT in workspace config.yaml."""
        MemoryInitializer().initialize(project_root)

        # Memory stores must be in memory/config.yaml
        with open(project_root / "memory" / "config.yaml") as f:
            mem_config = yaml.safe_load(f)
        assert "episodes" in mem_config.get("stores", {})
        assert "semantic_facts" in mem_config.get("stores", {})

        # Memory stores must NOT be in workspace config.yaml
        with open(project_root / "config.yaml") as f:
            ws_config = yaml.safe_load(f)
        index_names = [idx["name"] for idx in ws_config.get("indices", [])]
        assert "episodes" not in index_names
        assert "semantic_facts" not in index_names

    def test_smak_config_generated(self, project_root):
        """Internal smak_config.yaml should be generated for search engine."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / "memory" / "smak_config.yaml").exists()

    def test_memory_store_directory_created(self, project_root):
        """The memory/store/ directory should be created."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / "memory" / "store").is_dir()

    def test_memory_appended_to_one_for_all(self, project_root):
        """Memory section should be appended to one-for-all SKILL.md."""
        MemoryInitializer().initialize(project_root)
        skill_path = project_root / ".claude" / "skills" / "one-for-all" / "SKILL.md"
        assert skill_path.exists()
        content = skill_path.read_text()
        assert "Agent Memory" in content
        assert "/remember" in content
        assert "/recall" in content
        assert "/consolidate" in content

    def test_generates_commands(self, project_root):
        MemoryInitializer().initialize(project_root)
        commands_dir = project_root / ".claude" / "commands"
        assert (commands_dir / "remember.md").exists()
        assert (commands_dir / "recall.md").exists()
        assert (commands_dir / "consolidate.md").exists()

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

    def test_idempotent_stores(self, project_root):
        """Running init twice should not duplicate store definitions."""
        init = MemoryInitializer()
        init.initialize(project_root)
        init.initialize(project_root)

        with open(project_root / "memory" / "config.yaml") as f:
            mem_config = yaml.safe_load(f)

        stores = mem_config.get("stores", {})
        assert "episodes" in stores
        assert "semantic_facts" in stores

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
