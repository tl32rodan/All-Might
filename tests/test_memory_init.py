"""Tests for MemoryInitializer — L1/L2/L3 architecture.

L1: MEMORY.md at project root (hook-loaded, agent-writable)
L2: memory/understanding/ per-corpus knowledge (agent reads/writes)
L3: memory/journal/ + store/ (text files + SMAK vector index)
"""

import pytest
import yaml

from allmight.memory.config import MemoryConfigManager
from allmight.memory.initializer import MemoryInitializer


@pytest.fixture
def project_root(tmp_path):
    """A minimal project root with one-for-all SKILL.md."""
    skill_dir = tmp_path / ".claude" / "skills" / "one-for-all"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: one-for-all\n---\n\n# One For All\n")
    return tmp_path


class TestMemoryInitializer:

    # -- L1: MEMORY.md at project root ---------------------------------

    def test_creates_memory_md_at_root(self, project_root):
        """L1: MEMORY.md at project root (not inside memory/)."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / "MEMORY.md").exists()

    def test_memory_md_has_project_map(self, project_root):
        """L1: MEMORY.md contains a project map section."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / "MEMORY.md").read_text()
        assert "Project Map" in content

    def test_memory_md_has_user_preferences(self, project_root):
        """L1: MEMORY.md has user preferences section."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / "MEMORY.md").read_text()
        assert "User Preferences" in content or "Preferences" in content

    # -- L2: understanding/ per-corpus ---------------------------------

    def test_creates_understanding_dir(self, project_root):
        """L2: memory/understanding/ directory created."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / "memory" / "understanding").is_dir()

    # -- L3: journal/ + store/ -----------------------------------------

    def test_creates_journal_dir(self, project_root):
        """L3: memory/journal/ directory created."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / "memory" / "journal").is_dir()

    def test_creates_store_dir(self, project_root):
        """L3: memory/store/ for SMAK vector index."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / "memory" / "store").is_dir()

    def test_creates_smak_config(self, project_root):
        """SMAK config generated for journal index."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / "memory" / "smak_config.yaml").exists()

    def test_smak_config_indexes_journal(self, project_root):
        """SMAK config points to journal/ directory."""
        MemoryInitializer().initialize(project_root)
        with open(project_root / "memory" / "smak_config.yaml") as f:
            cfg = yaml.safe_load(f)
        index_names = [idx["name"] for idx in cfg.get("indices", [])]
        assert "journal" in index_names
        journal_idx = next(i for i in cfg["indices"] if i["name"] == "journal")
        assert "journal" in journal_idx["paths"][0]

    # -- Old architecture should NOT exist -----------------------------

    def test_no_episodes_dir(self, project_root):
        """Old episodes/ should not be created."""
        MemoryInitializer().initialize(project_root)
        assert not (project_root / "memory" / "episodes").exists()

    def test_no_semantic_dir(self, project_root):
        """Old semantic/ should not be created."""
        MemoryInitializer().initialize(project_root)
        assert not (project_root / "memory" / "semantic").exists()

    def test_no_working_dir(self, project_root):
        """Old working/ should not be created (MEMORY.md is at root)."""
        MemoryInitializer().initialize(project_root)
        assert not (project_root / "memory" / "working").exists()

    # -- Commands ------------------------------------------------------

    def test_generates_remember_command(self, project_root):
        MemoryInitializer().initialize(project_root)
        assert (project_root / ".claude" / "commands" / "remember.md").exists()

    def test_generates_recall_command(self, project_root):
        MemoryInitializer().initialize(project_root)
        assert (project_root / ".claude" / "commands" / "recall.md").exists()

    def test_no_consolidate_command(self, project_root):
        """consolidate removed — no more episode-to-semantic pipeline."""
        MemoryInitializer().initialize(project_root)
        assert not (project_root / ".claude" / "commands" / "consolidate.md").exists()

    def test_remember_command_mentions_journal(self, project_root):
        """remember.md should reference journal/ (L3)."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".claude" / "commands" / "remember.md").read_text()
        assert "journal" in content

    def test_remember_command_mentions_understanding(self, project_root):
        """remember.md should reference understanding/ (L2)."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".claude" / "commands" / "remember.md").read_text()
        assert "understanding" in content

    def test_recall_command_mentions_smak(self, project_root):
        """recall.md should use smak search against journal."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".claude" / "commands" / "recall.md").read_text()
        assert "smak search" in content

    # -- Skill section -------------------------------------------------

    def test_appends_memory_to_skill(self, project_root):
        """Memory section appended to one-for-all SKILL.md."""
        MemoryInitializer().initialize(project_root)
        skill = (project_root / ".claude" / "skills" / "one-for-all" / "SKILL.md").read_text()
        assert "Memory" in skill
        assert "/remember" in skill
        assert "/recall" in skill

    def test_skill_describes_hierarchy(self, project_root):
        """Skill describes MEMORY.md, understanding/, journal/."""
        MemoryInitializer().initialize(project_root)
        skill = (project_root / ".claude" / "skills" / "one-for-all" / "SKILL.md").read_text()
        assert "MEMORY.md" in skill
        assert "understanding" in skill
        assert "journal" in skill

    def test_skill_no_consolidate(self, project_root):
        """Skill should not reference /consolidate."""
        MemoryInitializer().initialize(project_root)
        skill = (project_root / ".claude" / "skills" / "one-for-all" / "SKILL.md").read_text()
        assert "/consolidate" not in skill

    # -- CLAUDE.md update ----------------------------------------------

    def test_updates_claude_md(self, project_root):
        (project_root / "CLAUDE.md").write_text("# Test Project\n\nExisting content.\n")
        MemoryInitializer().initialize(project_root)
        content = (project_root / "CLAUDE.md").read_text()
        assert "Memory" in content
        assert "Existing content." in content

    def test_creates_claude_md_if_missing(self, project_root):
        MemoryInitializer().initialize(project_root)
        assert (project_root / "CLAUDE.md").exists()
        content = (project_root / "CLAUDE.md").read_text()
        assert "Memory" in content

    # -- Idempotency ---------------------------------------------------

    def test_idempotent(self, project_root):
        """Running init twice doesn't break anything."""
        init = MemoryInitializer()
        init.initialize(project_root)
        init.initialize(project_root)
        assert (project_root / "MEMORY.md").exists()
        assert (project_root / "memory" / "understanding").is_dir()
        assert (project_root / "memory" / "journal").is_dir()

    def test_opencode_agents_md_symlink(self, project_root):
        """AGENTS.md -> CLAUDE.md symlink created."""
        MemoryInitializer().initialize(project_root)
        agents_md = project_root / "AGENTS.md"
        claude_md = project_root / "CLAUDE.md"
        assert claude_md.exists()
        assert agents_md.is_symlink()
        assert agents_md.resolve() == claude_md.resolve()

    def test_opencode_dotdir_created(self, project_root):
        """.opencode/ directory created with symlinks into .claude/."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / ".opencode").is_dir()
        assert (project_root / ".opencode" / "skills").is_symlink()
        assert (project_root / ".opencode" / "commands").is_symlink()

    def test_opencode_compat_idempotent(self, project_root):
        init = MemoryInitializer()
        init.initialize(project_root)
        init.initialize(project_root)
        assert (project_root / "AGENTS.md").is_symlink()
        assert (project_root / ".opencode").is_dir()


class TestMemoryConfigManager:

    def test_initialize_creates_config(self, tmp_path):
        mgr = MemoryConfigManager(tmp_path)
        cfg = mgr.initialize()
        assert (tmp_path / "memory" / "config.yaml").exists()

    def test_config_has_journal_store(self, tmp_path):
        """Config should define a journal store, not episodes/semantic."""
        mgr = MemoryConfigManager(tmp_path)
        cfg = mgr.initialize()
        assert "journal" in cfg.stores
        assert "episodes" not in cfg.stores
        assert "semantic_facts" not in cfg.stores

    def test_round_trip(self, tmp_path):
        mgr = MemoryConfigManager(tmp_path)
        cfg = mgr.initialize()
        mgr.save(cfg)
        loaded = mgr.load()
        assert "journal" in loaded.stores


class TestMemoryNudgeHook:
    """Memory Nudge — Stop hook that reminds agent to update memory."""

    def test_creates_hooks_dir(self, project_root):
        """memory init creates .claude/hooks/ directory."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / ".claude" / "hooks").is_dir()

    def test_creates_nudge_script(self, project_root):
        """memory-nudge.sh created in hooks directory."""
        MemoryInitializer().initialize(project_root)
        script = project_root / ".claude" / "hooks" / "memory-nudge.sh"
        assert script.exists()

    def test_nudge_script_is_executable(self, project_root):
        """Hook script has executable permission."""
        MemoryInitializer().initialize(project_root)
        import os
        script = project_root / ".claude" / "hooks" / "memory-nudge.sh"
        assert os.access(script, os.X_OK)

    def test_nudge_script_references_memory(self, project_root):
        """Hook script mentions MEMORY.md and understanding."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".claude" / "hooks" / "memory-nudge.sh").read_text()
        assert "MEMORY.md" in content
        assert "understanding" in content

    def test_creates_l1_loader_script(self, project_root):
        """memory-load.sh created — injects MEMORY.md into context."""
        MemoryInitializer().initialize(project_root)
        script = project_root / ".claude" / "hooks" / "memory-load.sh"
        assert script.exists()

    def test_l1_loader_reads_memory_md(self, project_root):
        """Loader script cats MEMORY.md content."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".claude" / "hooks" / "memory-load.sh").read_text()
        assert "MEMORY.md" in content


class TestReflectCommand:
    """/reflect — structured self-reflection to maintain memory quality."""

    def test_creates_reflect_command(self, project_root):
        MemoryInitializer().initialize(project_root)
        assert (project_root / ".claude" / "commands" / "reflect.md").exists()

    def test_reflect_mentions_all_tiers(self, project_root):
        """reflect.md references L1, L2, and L3."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".claude" / "commands" / "reflect.md").read_text()
        assert "MEMORY.md" in content
        assert "understanding" in content
        assert "journal" in content

    def test_reflect_has_checklist(self, project_root):
        """reflect.md has a structured checklist for the agent."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".claude" / "commands" / "reflect.md").read_text()
        assert "## How" in content or "## Checklist" in content or "## Steps" in content

    def test_skill_mentions_reflect(self, project_root):
        """Skill section references /reflect command."""
        MemoryInitializer().initialize(project_root)
        skill = (project_root / ".claude" / "skills" / "one-for-all" / "SKILL.md").read_text()
        assert "/reflect" in skill
