"""Tests for version-update staging and /sync skill generation.

Feature 1: when ``allmight init`` is run on a project that was already
initialized (``.allmight/`` exists), templates are staged to
``.allmight/templates/`` instead of overwriting working files.
The agent then runs ``/sync`` to merge staged templates with
user-customized files.
"""

import os
import stat

import pytest

from allmight.personalities.corpus_keeper.scanner import ProjectScanner
from allmight.personalities.corpus_keeper.initializer import ProjectInitializer
from allmight.personalities.memory_keeper.initializer import MemoryInitializer


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


def _full_init(root, force=False, writable=False):
    """Run the full init sequence: ProjectInitializer + MemoryInitializer.

    Mirrors the logic in ``cli.py``: detect re-init before calling
    initializers so the staging flag is consistent.
    """
    scanner = ProjectScanner()
    manifest = scanner.scan(root)
    is_reinit = (root / ".allmight").is_dir() and not force
    ProjectInitializer().initialize(manifest, force=force, writable=writable)
    MemoryInitializer().initialize(root, staging=is_reinit)
    return manifest


# ======================================================================
# First Init — current behavior + .allmight/ marker
# ======================================================================


class TestFirstInit:
    """First-time init (no .allmight/) — current behavior + creates .allmight/ marker."""

    def test_first_init_creates_allmight_dir(self, sample_project):
        _full_init(sample_project)
        assert (sample_project / ".allmight").is_dir()

    def test_first_init_no_staging(self, sample_project):
        _full_init(sample_project)
        # No staging on first init
        assert not (sample_project / ".allmight" / "templates").exists()

    def test_first_init_writes_commands_directly(self, sample_project):
        _full_init(sample_project, writable=True)
        commands = sample_project / ".opencode" / "commands"
        assert (commands / "search.md").exists()
        assert (commands / "enrich.md").exists()
        assert (commands / "ingest.md").exists()

    def test_no_claude_hooks_generated(self, sample_project):
        """No .claude/hooks/ generated — TS plugins handle memory in OpenCode."""
        _full_init(sample_project)
        assert not (sample_project / ".claude" / "hooks").exists()

    def test_first_init_writes_agents_md(self, sample_project):
        _full_init(sample_project)
        content = (sample_project / "AGENTS.md").read_text()
        assert "<!-- ALL-MIGHT -->" in content

    def test_first_init_writes_memory_commands(self, sample_project):
        _full_init(sample_project)
        commands = sample_project / ".opencode" / "commands"
        assert (commands / "remember.md").exists()
        assert (commands / "recall.md").exists()
        assert (commands / "reflect.md").exists()

    def test_first_init_no_sync_command(self, sample_project):
        """First init does NOT create /sync — it's only needed on re-init."""
        _full_init(sample_project)
        assert not (sample_project / ".opencode" / "commands" / "sync.md").exists()


# ======================================================================
# Re-Init — stages templates, doesn't overwrite working files
# ======================================================================


class TestReInit:
    """Re-init (.allmight/ exists) — stages templates, doesn't overwrite working files."""

    def test_reinit_detects_allmight_dir(self, sample_project):
        _full_init(sample_project)
        # Second init should stage
        _full_init(sample_project)
        assert (sample_project / ".allmight" / "templates").is_dir()

    def test_reinit_does_not_overwrite_commands(self, sample_project):
        _full_init(sample_project)
        search_cmd = sample_project / ".opencode" / "commands" / "search.md"
        search_cmd.write_text("MY CUSTOM SEARCH GUIDE")

        _full_init(sample_project)

        assert search_cmd.read_text() == "MY CUSTOM SEARCH GUIDE"
        staged = sample_project / ".allmight" / "templates" / "commands" / "search.md"
        assert staged.exists()
        assert "MY CUSTOM" not in staged.read_text()

    def test_no_hooks_staged_on_reinit(self, sample_project):
        """Hooks are no longer generated, so nothing to stage on re-init."""
        _full_init(sample_project)
        _full_init(sample_project)
        staged_hooks = sample_project / ".allmight" / "templates" / "hooks"
        assert not staged_hooks.exists()

    def test_reinit_does_not_overwrite_agents_md(self, sample_project):
        _full_init(sample_project)
        agents_md = sample_project / "AGENTS.md"
        original = agents_md.read_text()
        agents_md.write_text(original + "\n\n## My Custom Section\nUser stuff here.\n")

        _full_init(sample_project)

        content = agents_md.read_text()
        assert "My Custom Section" in content
        assert "User stuff here" in content
        # Section content staged
        staged = sample_project / ".allmight" / "templates" / "claude-md-section.md"
        assert staged.exists()
        assert "<!-- ALL-MIGHT -->" in staged.read_text()

    def test_reinit_does_not_overwrite_memory_md(self, sample_project):
        _full_init(sample_project)
        memory_md = sample_project / "MEMORY.md"
        memory_md.write_text("# My Custom Memory\nUser preferences here.\n")

        _full_init(sample_project)

        assert "My Custom Memory" in memory_md.read_text()

    def test_reinit_stages_memory_commands(self, sample_project):
        _full_init(sample_project)
        remember_cmd = sample_project / ".opencode" / "commands" / "remember.md"
        remember_cmd.write_text("CUSTOM REMEMBER")

        _full_init(sample_project)

        assert remember_cmd.read_text() == "CUSTOM REMEMBER"
        staged = sample_project / ".allmight" / "templates" / "commands" / "remember.md"
        assert staged.exists()
        assert "CUSTOM REMEMBER" not in staged.read_text()

    def test_reinit_stages_opencode_config(self, sample_project):
        _full_init(sample_project)
        _full_init(sample_project)

        templates = sample_project / ".allmight" / "templates"
        assert (templates / "opencode.json").exists()
        assert (templates / "memory-load.ts").exists()

    def test_reinit_stages_claude_md_sections(self, sample_project):
        _full_init(sample_project)
        _full_init(sample_project)

        templates = sample_project / ".allmight" / "templates"
        assert (templates / "claude-md-section.md").exists()
        assert "<!-- ALL-MIGHT -->" in (templates / "claude-md-section.md").read_text()
        assert (templates / "memory-md-section.md").exists()
        assert "<!-- ALL-MIGHT-MEMORY -->" in (templates / "memory-md-section.md").read_text()

    def test_reinit_still_creates_new_directories(self, sample_project):
        _full_init(sample_project)
        # Simulate missing directory
        import shutil
        kg = sample_project / "knowledge_graph"
        if kg.exists():
            shutil.rmtree(kg)

        _full_init(sample_project)

        assert kg.is_dir()

    def test_reinit_creates_sync_command(self, sample_project):
        _full_init(sample_project)
        _full_init(sample_project)

        assert (sample_project / ".opencode" / "commands" / "sync.md").exists()
        assert (sample_project / ".opencode" / "skills" / "sync" / "SKILL.md").exists()

    def test_reinit_agents_md_is_real_file(self, sample_project):
        _full_init(sample_project)
        _full_init(sample_project)

        agents_md = sample_project / "AGENTS.md"
        assert agents_md.is_file()
        assert not agents_md.is_symlink()


# ======================================================================
# Force Init — overwrites everything like first-time
# ======================================================================


class TestForceInit:
    """Force init (--force) — overwrites everything like first-time."""

    def test_force_overwrites_modified_commands(self, sample_project):
        _full_init(sample_project)
        search_cmd = sample_project / ".opencode" / "commands" / "search.md"
        search_cmd.write_text("MY CUSTOM SEARCH GUIDE")

        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        ProjectInitializer().initialize(manifest, force=True)

        assert "MY CUSTOM" not in search_cmd.read_text()

    def test_force_does_not_overwrite_memory_md(self, sample_project):
        _full_init(sample_project)
        memory_md = sample_project / "MEMORY.md"
        memory_md.write_text("# My Custom Memory")

        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        ProjectInitializer().initialize(manifest, force=True)
        MemoryInitializer().initialize(sample_project, staging=False)

        # MEMORY.md is NEVER overwritten
        assert "My Custom Memory" in memory_md.read_text()


# ======================================================================
# Sync Skill Content
# ======================================================================


class TestSyncSkillContent:
    """The /sync skill and command are valid and complete."""

    def test_sync_skill_installed_on_reinit(self, sample_project):
        _full_init(sample_project)
        _full_init(sample_project)

        skill = sample_project / ".opencode" / "skills" / "sync" / "SKILL.md"
        assert skill.exists()
        content = skill.read_text()
        # Valid frontmatter
        assert content.startswith("---")
        assert "name:" in content

    def test_sync_skill_references_templates_dir(self, sample_project):
        _full_init(sample_project)
        _full_init(sample_project)

        content = (sample_project / ".opencode" / "skills" / "sync" / "SKILL.md").read_text()
        assert ".allmight/templates/" in content

    def test_sync_skill_references_merge_report(self, sample_project):
        _full_init(sample_project)
        _full_init(sample_project)

        content = (sample_project / ".opencode" / "skills" / "sync" / "SKILL.md").read_text()
        assert "merge-report" in content

    def test_sync_command_references_skill(self, sample_project):
        _full_init(sample_project)
        _full_init(sample_project)

        content = (sample_project / ".opencode" / "commands" / "sync.md").read_text()
        assert "sync" in content.lower()

    def test_sync_skill_mentions_mode_cleanup(self, sample_project):
        """Sync skill instructs agent to check .allmight/mode and remove
        commands that don't belong to the current mode."""
        _full_init(sample_project)
        _full_init(sample_project)

        content = (sample_project / ".opencode" / "skills" / "sync" / "SKILL.md").read_text()
        assert ".allmight/mode" in content

    def test_sync_skill_references_opencode_paths(self, sample_project):
        """Sync skill only references .opencode paths, not .claude paths."""
        from allmight.personalities.corpus_keeper.sync_skill_content import SYNC_SKILL_BODY
        assert ".opencode/commands" in SYNC_SKILL_BODY
        assert ".claude/commands" not in SYNC_SKILL_BODY
        assert ".claude/hooks" not in SYNC_SKILL_BODY


# ======================================================================
# Mode Transitions — re-init with different mode
# ======================================================================


class TestModeTransitions:
    """Mode transition rules on re-init.

    Legal:   writable → read-only, same → same
    Illegal: read-only → writable
    """

    # -- Legal: same mode --

    def test_reinit_readonly_to_readonly(self, sample_project):
        """Re-init read-only → read-only is fine."""
        _full_init(sample_project, writable=False)
        _full_init(sample_project, writable=False)
        assert (sample_project / ".allmight" / "mode").read_text().strip() == "read-only"

    def test_reinit_writable_to_writable(self, sample_project):
        """Re-init writable → writable is fine."""
        _full_init(sample_project, writable=True)
        _full_init(sample_project, writable=True)
        assert (sample_project / ".allmight" / "mode").read_text().strip() == "writable"

    # -- Legal: writable → read-only (downgrade) --

    def test_writable_to_readonly_allowed(self, sample_project):
        """Re-init writable → read-only is allowed (downgrade)."""
        _full_init(sample_project, writable=True)
        _full_init(sample_project, writable=False)  # should not raise

    def test_writable_to_readonly_updates_mode(self, sample_project):
        """Downgrade updates .allmight/mode to read-only."""
        _full_init(sample_project, writable=True)
        _full_init(sample_project, writable=False)
        assert (sample_project / ".allmight" / "mode").read_text().strip() == "read-only"

    def test_writable_to_readonly_stages_readonly_templates(self, sample_project):
        """Downgrade stages read-only templates (no enrich/ingest)."""
        _full_init(sample_project, writable=True)
        _full_init(sample_project, writable=False)
        tpl = sample_project / ".allmight" / "templates" / "commands"
        assert (tpl / "search.md").exists()
        assert not (tpl / "enrich.md").exists()
        assert not (tpl / "ingest.md").exists()

    def test_writable_to_readonly_stages_removal_list(self, sample_project):
        """Downgrade stages a remove.txt listing commands to delete."""
        _full_init(sample_project, writable=True)
        _full_init(sample_project, writable=False)
        remove_file = sample_project / ".allmight" / "templates" / "remove.txt"
        assert remove_file.exists()
        content = remove_file.read_text()
        assert "enrich.md" in content
        assert "ingest.md" in content

    # -- Illegal: read-only → writable (upgrade) --

    def test_readonly_to_writable_rejected(self, sample_project):
        """Re-init read-only → writable is rejected."""
        _full_init(sample_project, writable=False)
        with pytest.raises(ValueError, match="read-only.*writable"):
            scanner = ProjectScanner()
            manifest = scanner.scan(sample_project)
            ProjectInitializer().initialize(manifest, writable=True)

    def test_force_readonly_to_writable_also_rejected(self, sample_project):
        """Even --force cannot upgrade read-only → writable."""
        _full_init(sample_project, writable=False)
        with pytest.raises(ValueError, match="read-only.*writable"):
            scanner = ProjectScanner()
            manifest = scanner.scan(sample_project)
            ProjectInitializer().initialize(manifest, force=True, writable=True)
