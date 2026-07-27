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

from allmight.capabilities.database.scanner import ProjectScanner
from allmight.capabilities.database.initializer import ProjectInitializer
from allmight.capabilities.memory.initializer import MemoryInitializer
from allmight.core.personalities import write_init_scaffold


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


def _full_init(root, force=False):
    """Run the full init sequence: scaffold + ProjectInitializer + MemoryInitializer.

    Mirrors the logic in ``cli.py``: detect re-init before calling
    initializers so the staging flag is consistent. ``write_init_scaffold``
    sets up project-level files that don't belong to any template
    (``.opencode/{opencode.json,package.json}``, role-load plugin, and
    the Claude Code bridge).
    """
    scanner = ProjectScanner()
    manifest = scanner.scan(root)
    is_reinit = (root / ".allmight").is_dir() and not force
    write_init_scaffold(root)
    ProjectInitializer().initialize(manifest, force=force)
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
        _full_init(sample_project)
        commands = sample_project / ".opencode" / "commands"
        # /search is the only database-capability slash command.
        # /enrich and /ingest were retired.
        assert (commands / "search.md").exists()
        assert not (commands / "enrich.md").exists()
        assert not (commands / "ingest.md").exists()

    def test_full_init_writes_claude_bridge(self, sample_project):
        """Full init writes the Claude Code bridge alongside .opencode/.

        Mirrors what the OpenCode side gets:
        - root CLAUDE.md is the @-import shim Claude Code reads
        - .claude/{commands,skills} are dir symlinks into .opencode/
        - .claude/hooks/{memory_load,role_load}.py mirror the
          memory-load.ts and role-load.ts plugins
        - .claude/settings.json registers both hooks for SessionStart
          and PreCompact
        """
        _full_init(sample_project)
        assert (sample_project / "CLAUDE.md").exists()
        commands_link = sample_project / ".claude" / "commands"
        skills_link = sample_project / ".claude" / "skills"
        assert commands_link.is_symlink()
        assert skills_link.is_symlink()
        assert (sample_project / ".claude" / "hooks" / "memory_load.py").exists()
        assert (sample_project / ".claude" / "hooks" / "role_load.py").exists()
        assert (sample_project / ".claude" / "settings.json").exists()

    def test_first_init_writes_agents_md(self, sample_project):
        _full_init(sample_project)
        content = (sample_project / "AGENTS.md").read_text()
        assert "<!-- ALL-MIGHT -->" in content

    def test_first_init_writes_memory_commands(self, sample_project):
        _full_init(sample_project)
        commands = sample_project / ".opencode" / "commands"
        assert (commands / "remember.md").exists()
        assert (commands / "recall.md").exists()
        # Wave 2 of the design-review refactor split ``/reflect`` back
        # out of ``/remember``; both bodies now ship.
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
        kg = sample_project / "database"
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

    def test_sync_command_references_skill(self, sample_project):
        _full_init(sample_project)
        _full_init(sample_project)

        content = (sample_project / ".opencode" / "commands" / "sync.md").read_text()
        assert "sync" in content.lower()

    def test_sync_skill_mentions_deprecated_cleanup(self, sample_project):
        """Sync skill instructs the agent to remove the retired
        ``/enrich`` and ``/ingest`` slash commands if they linger."""
        _full_init(sample_project)
        _full_init(sample_project)

        content = (sample_project / ".opencode" / "skills" / "sync" / "SKILL.md").read_text()
        assert "enrich.md" in content
        assert "ingest.md" in content

    def test_sync_skill_treats_claude_dir_as_generated_not_legacy(
        self, sample_project,
    ):
        """`.claude/` is a generated bridge, not leftover cruft.

        The body used to end with "any legacy `.claude/` directory can
        be deleted manually once sync is complete" — following that
        removes settings.json, the hook scripts and the dir symlinks,
        i.e. the entire Claude Code surface. It must instead teach the
        clash case (user owns a real `.claude/commands/`).
        """
        from allmight.capabilities.database.sync_skill_content import SYNC_SKILL_BODY
        assert ".opencode/commands" in SYNC_SKILL_BODY
        assert "legacy `.claude/`" not in SYNC_SKILL_BODY
        assert "`.claude/commands`" in SYNC_SKILL_BODY
        assert "Do not delete it." in SYNC_SKILL_BODY

    def test_sync_skill_covers_attic_recovery(self, sample_project):
        """Retired files land in `.allmight/attic/`; the agent has to be
        able to tell the user how to get one back."""
        from allmight.capabilities.database.sync_skill_content import SYNC_SKILL_BODY
        assert ".allmight/attic/" in SYNC_SKILL_BODY
        assert "never deletes" in SYNC_SKILL_BODY

    def test_sync_skill_teaches_agents_md_fence(self, sample_project):
        """AGENTS.md is shared: the agent must know only the fenced
        region is ours, and that `.prev` is a recoverable backup."""
        from allmight.capabilities.database.sync_skill_content import SYNC_SKILL_BODY
        assert "<!-- ALL-MIGHT:BEGIN -->" in SYNC_SKILL_BODY
        assert "<!-- ALL-MIGHT:END -->" in SYNC_SKILL_BODY
        assert "AGENTS.md.prev" in SYNC_SKILL_BODY

    def test_sync_skill_marker_gates_command_removal(self, sample_project):
        """`remove.txt` must never be applied blind — the same filename
        may be a command the user wrote."""
        from allmight.capabilities.database.sync_skill_content import SYNC_SKILL_BODY
        idx = SYNC_SKILL_BODY.index("remove.txt")
        section = " ".join(SYNC_SKILL_BODY[idx:idx + 600].split()).replace("*", "")
        assert "only if it carries our marker" in section


# ======================================================================
# Deprecated /enrich and /ingest cleanup
# ======================================================================


class TestDeprecatedCommandCleanup:
    """The retired ``/enrich`` and ``/ingest`` slash commands must not
    survive a re-init **when they are ours** — a marker-carrying
    leftover from an older writable-mode install. A hand-authored file
    at the same path belongs to the user and is preserved."""

    def test_mode_is_always_read_only(self, sample_project):
        """All-Might no longer has a writable mode — ``.allmight/mode``
        is pinned to ``read-only``."""
        _full_init(sample_project)
        assert (sample_project / ".allmight" / "mode").read_text().strip() == "read-only"

    def test_reinit_stages_removal_list(self, sample_project):
        """Re-init always stages a ``remove.txt`` for the retired
        commands so ``/sync`` can purge any stragglers."""
        _full_init(sample_project)
        _full_init(sample_project)
        remove_file = sample_project / ".allmight" / "templates" / "remove.txt"
        assert remove_file.exists()
        content = remove_file.read_text()
        assert "enrich.md" in content
        assert "ingest.md" in content

    def test_first_init_cleans_legacy_enrich(self, sample_project):
        """A marker'd ``enrich.md`` left by an older install is retired."""
        _full_init(sample_project)
        commands = sample_project / ".opencode" / "commands"
        legacy = commands / "enrich.md"
        legacy.write_text("<!-- all-might generated -->\nlegacy content")
        # Re-run with --force so we hit the non-staging path.
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        ProjectInitializer().initialize(manifest, force=True)
        assert not legacy.exists()
        attic = (
            sample_project / ".allmight" / "attic"
            / ".opencode" / "commands" / "enrich.md"
        )
        assert attic.is_file(), "retired command must be recoverable"

    def test_first_init_cleans_legacy_ingest(self, sample_project):
        """A marker'd ``ingest.md`` left by an older install is retired."""
        _full_init(sample_project)
        commands = sample_project / ".opencode" / "commands"
        legacy = commands / "ingest.md"
        legacy.write_text("<!-- all-might generated -->\nlegacy content")
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        ProjectInitializer().initialize(manifest, force=True)
        assert not legacy.exists()

    @pytest.mark.parametrize("name", ["enrich.md", "ingest.md"])
    def test_user_authored_retired_name_is_never_removed(
        self, sample_project, name,
    ):
        """A user's own ``enrich.md`` / ``ingest.md`` is not ours to delete.

        The retirement sweep used to ``unlink()`` these names
        unconditionally, with no marker check — so a first-time
        ``allmight init`` inside a project that already had
        ``.opencode/commands/enrich.md`` destroyed it.
        """
        _full_init(sample_project)
        commands = sample_project / ".opencode" / "commands"
        mine = commands / name
        body = f"# my own {name}, nothing to do with All-Might\n"
        mine.write_text(body)
        scanner = ProjectScanner()
        manifest = scanner.scan(sample_project)
        ProjectInitializer().initialize(manifest, force=True)
        assert mine.is_file()
        assert mine.read_text() == body
