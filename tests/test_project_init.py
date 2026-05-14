"""Test Group 1: Project Init — what `allmight init` produces.

TDD: these tests define the TARGET architecture.
One All-Might project with shared enrichment/memory/panorama
and multiple SMAK workspaces under database/.
"""

import pytest

from allmight.capabilities.database.initializer import ProjectInitializer
from allmight.capabilities.database.scanner import ProjectScanner


@pytest.fixture
def project_root(tmp_path):
    """Bare directory to init as an All-Might project."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    return tmp_path


def _init(root):
    scanner = ProjectScanner()
    manifest = scanner.scan(root)
    ProjectInitializer().initialize(manifest)


def _init_with_memory(root):
    """Mirrors what `allmight init` does: project init + memory init."""
    from allmight.capabilities.memory.initializer import MemoryInitializer

    _init(root)
    MemoryInitializer().initialize(root)


class TestProjectInit:
    """Common init behavior — holds for both modes."""

    def test_no_claude_md_generated(self, project_root):
        """CLAUDE.md must NOT be generated — AGENTS.md is the target."""
        _init(project_root)
        assert not (project_root / "CLAUDE.md").exists()

    def test_creates_agents_md_as_real_file(self, project_root):
        """AGENTS.md created as a real file (not a symlink) for OpenCode."""
        _init(project_root)
        agents = project_root / "AGENTS.md"
        assert agents.is_file()
        assert not agents.is_symlink()

    def test_creates_core_commands(self, project_root):
        """The database capability emits only ``/search``; the legacy
        ``/enrich`` and ``/ingest`` slash commands were retired."""
        _init(project_root)
        cmds = project_root / ".opencode" / "commands"
        assert (cmds / "search.md").exists()
        assert not (cmds / "enrich.md").exists()
        assert not (cmds / "ingest.md").exists()
        assert not (cmds / "status.md").exists()

    def test_creates_database_dir(self, project_root):
        """database/ directory created."""
        _init(project_root)
        assert (project_root / "database").is_dir()

    def test_no_config_yaml_at_root(self, project_root):
        """No config.yaml at project root — config.yaml is SMAK's concern."""
        _init(project_root)
        assert not (project_root / "config.yaml").exists()

    def test_agents_md_is_what_not_how(self, project_root):
        """AGENTS.md references /search but not smak CLI details."""
        _init(project_root)
        content = (project_root / "AGENTS.md").read_text()
        assert "/search" in content
        assert "smak search" not in content
        assert "smak enrich" not in content

    def test_agents_md_defines_corpus_and_workspace(self, project_root):
        """AGENTS.md explains that corpus = workspace, linked to database/."""
        _init(project_root)
        content = (project_root / "AGENTS.md").read_text()
        assert "Corpus" in content or "corpus" in content
        assert "workspace" in content
        assert "database/" in content

    def test_init_idempotent(self, project_root):
        """Running init twice doesn't break anything."""
        _init(project_root)
        _init(project_root)
        assert (project_root / "AGENTS.md").exists()
        assert (project_root / "database").is_dir()


class TestProjectInitIncludesMemory:
    """Memory is always initialized as part of `allmight init`."""

    def test_creates_memory_dir(self, project_root):
        """init creates memory/ at project level."""
        _init_with_memory(project_root)
        assert (project_root / "memory").is_dir()
        assert (project_root / "MEMORY.md").exists()

    def test_creates_memory_commands(self, project_root):
        """init adds remember.md and recall.md."""
        _init_with_memory(project_root)
        cmds = project_root / ".opencode" / "commands"
        assert (cmds / "remember.md").exists()
        assert (cmds / "recall.md").exists()

    def test_memory_not_inside_database(self, project_root):
        """memory/ lives at project root, NOT inside database/."""
        _init_with_memory(project_root)
        assert (project_root / "memory").is_dir()
        for ws_dir in (project_root / "database").iterdir():
            assert not (ws_dir / "memory").exists()


# ------------------------------------------------------------------
# Agent-surface contract: search-only, no retired commands
# ------------------------------------------------------------------


class TestAgentSurfaceIsSearchOnly:
    """The All-Might agent surface against the knowledge graph is
    search-only — ``/enrich`` and ``/ingest`` were retired."""

    def test_mode_marker_is_read_only(self, project_root):
        """``.allmight/mode`` is pinned to ``read-only``."""
        _init(project_root)
        mode_file = project_root / ".allmight" / "mode"
        assert mode_file.exists()
        assert mode_file.read_text().strip() == "read-only"

    def test_no_ingest_command(self, project_root):
        _init(project_root)
        assert not (project_root / ".opencode" / "commands" / "ingest.md").exists()

    def test_no_enrich_command(self, project_root):
        _init(project_root)
        assert not (project_root / ".opencode" / "commands" / "enrich.md").exists()

    def test_has_search_command(self, project_root):
        _init(project_root)
        assert (project_root / ".opencode" / "commands" / "search.md").exists()

    def test_agents_md_no_ingest(self, project_root):
        _init(project_root)
        content = (project_root / "AGENTS.md").read_text()
        assert "/ingest" not in content

    def test_agents_md_no_enrich(self, project_root):
        _init(project_root)
        content = (project_root / "AGENTS.md").read_text()
        assert "/enrich" not in content

    def test_agents_md_emphasizes_readonly(self, project_root):
        _init(project_root)
        content = (project_root / "AGENTS.md").read_text()
        assert "read-only" in content.lower() or "read only" in content.lower()


class TestOverwriteGuard:
    """init must not silently clobber user-owned files at the same paths."""

    def test_init_emits_marker_on_search_command(self, project_root):
        """The generated ``search.md`` carries the All-Might marker."""
        _init(project_root)
        cmds = project_root / ".opencode" / "commands"
        assert "<!-- all-might generated -->" in (cmds / "search.md").read_text()

    def test_reinit_emits_marker_on_sync_skill(self, project_root):
        """Sync SKILL.md (installed on re-init) keeps frontmatter on line 1
        but carries the marker after it."""
        _init(project_root)  # first init creates .allmight/
        _init(project_root)  # re-init triggers sync skill install
        skill = project_root / ".opencode" / "skills" / "sync" / "SKILL.md"
        text = skill.read_text()
        assert text.startswith("---\n"), "SKILL.md frontmatter must be on line 1"
        assert "<!-- all-might generated -->" in text

    def test_init_skips_existing_unmarked_command(
        self, project_root, capsys
    ):
        """A pre-existing user command at the same path is left untouched."""
        cmds = project_root / ".opencode" / "commands"
        cmds.mkdir(parents=True)
        (cmds / "search.md").write_text("MY OWN COMMAND")

        _init(project_root)

        assert (cmds / "search.md").read_text() == "MY OWN COMMAND"
        warn = capsys.readouterr().err
        assert "search.md" in warn and "All-Might marker" in warn

    def test_init_overwrites_existing_marked_file(self, project_root):
        """A pre-existing file we own (has the marker) is overwritten."""
        cmds = project_root / ".opencode" / "commands"
        cmds.mkdir(parents=True)
        (cmds / "search.md").write_text(
            "<!-- all-might generated -->\nstale body from a previous version"
        )

        _init(project_root)

        body = (cmds / "search.md").read_text()
        assert "stale body from a previous version" not in body
        assert "<!-- all-might generated -->" in body
