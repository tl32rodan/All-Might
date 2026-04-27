"""Test Group 1: Project Init — what `allmight init` produces.

TDD: these tests define the TARGET architecture.
One All-Might project with shared enrichment/memory/panorama
and multiple SMAK workspaces under knowledge_graph/.
"""

import pytest

from allmight.detroit_smak.initializer import ProjectInitializer
from allmight.detroit_smak.scanner import ProjectScanner


@pytest.fixture
def project_root(tmp_path):
    """Bare directory to init as an All-Might project."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    return tmp_path


def _init(root, writable=False):
    scanner = ProjectScanner()
    manifest = scanner.scan(root)
    ProjectInitializer().initialize(manifest, writable=writable)


def _init_with_memory(root, writable=False):
    """Mirrors what `allmight init` does: project init + memory init."""
    from allmight.memory.initializer import MemoryInitializer

    _init(root, writable=writable)
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

    def test_creates_core_commands_writable(self, project_root):
        """Writable: 3 core commands: search.md, enrich.md, ingest.md."""
        _init(project_root, writable=True)
        cmds = project_root / ".opencode" / "commands"
        assert (cmds / "search.md").exists()
        assert (cmds / "enrich.md").exists()
        assert (cmds / "ingest.md").exists()
        assert not (cmds / "status.md").exists()

    def test_creates_knowledge_graph_dir(self, project_root):
        """knowledge_graph/ directory created."""
        _init(project_root)
        assert (project_root / "knowledge_graph").is_dir()

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
        """AGENTS.md explains that corpus = workspace, linked to knowledge_graph/."""
        _init(project_root)
        content = (project_root / "AGENTS.md").read_text()
        assert "Corpus" in content or "corpus" in content
        assert "workspace" in content
        assert "knowledge_graph/" in content

    def test_init_idempotent(self, project_root):
        """Running init twice doesn't break anything."""
        _init(project_root)
        _init(project_root)
        assert (project_root / "AGENTS.md").exists()
        assert (project_root / "knowledge_graph").is_dir()


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

    def test_memory_not_inside_knowledge_graph(self, project_root):
        """memory/ lives at project root, NOT inside knowledge_graph/."""
        _init_with_memory(project_root)
        assert (project_root / "memory").is_dir()
        for ws_dir in (project_root / "knowledge_graph").iterdir():
            assert not (ws_dir / "memory").exists()


# ------------------------------------------------------------------
# Access Mode: read-only (default) vs writable
# ------------------------------------------------------------------


class TestReadOnlyMode:
    """Default init is read-only: no ingest/enrich, AGENTS.md emphasizes read-only."""

    def test_default_is_readonly(self, project_root):
        """allmight init without --writable produces read-only project."""
        _init(project_root)
        mode_file = project_root / ".allmight" / "mode"
        assert mode_file.exists()
        assert mode_file.read_text().strip() == "read-only"

    def test_readonly_no_ingest_command(self, project_root):
        """read-only mode does NOT generate ingest.md."""
        _init(project_root)
        assert not (project_root / ".opencode" / "commands" / "ingest.md").exists()

    def test_readonly_no_enrich_command(self, project_root):
        """read-only mode does NOT generate enrich.md."""
        _init(project_root)
        assert not (project_root / ".opencode" / "commands" / "enrich.md").exists()

    def test_readonly_has_search_command(self, project_root):
        """read-only mode still has search.md."""
        _init(project_root)
        assert (project_root / ".opencode" / "commands" / "search.md").exists()

    def test_readonly_agents_md_no_ingest(self, project_root):
        """AGENTS.md in read-only mode does NOT mention /ingest."""
        _init(project_root)
        content = (project_root / "AGENTS.md").read_text()
        assert "/ingest" not in content

    def test_readonly_agents_md_no_enrich(self, project_root):
        """AGENTS.md in read-only mode does NOT mention /enrich."""
        _init(project_root)
        content = (project_root / "AGENTS.md").read_text()
        assert "/enrich" not in content

    def test_readonly_agents_md_emphasizes_readonly(self, project_root):
        """AGENTS.md in read-only mode explicitly states read-only access."""
        _init(project_root)
        content = (project_root / "AGENTS.md").read_text()
        assert "read-only" in content.lower() or "read only" in content.lower()

    def test_readonly_agents_md_no_annotation(self, project_root):
        """AGENTS.md in read-only mode does NOT mention annotation."""
        _init(project_root)
        content = (project_root / "AGENTS.md").read_text()
        assert "Annotation" not in content and "annotate" not in content.lower()


class TestWritableMode:
    """--writable flag preserves current (full) behavior."""

    def test_writable_mode_persisted(self, project_root):
        """--writable stores 'writable' in .allmight/mode."""
        _init(project_root, writable=True)
        mode_file = project_root / ".allmight" / "mode"
        assert mode_file.exists()
        assert mode_file.read_text().strip() == "writable"

    def test_writable_has_all_commands(self, project_root):
        """Writable mode has search, enrich, and ingest commands."""
        _init(project_root, writable=True)
        cmds = project_root / ".opencode" / "commands"
        assert (cmds / "search.md").exists()
        assert (cmds / "enrich.md").exists()
        assert (cmds / "ingest.md").exists()

    def test_writable_agents_md_has_ingest(self, project_root):
        """AGENTS.md in writable mode mentions /ingest."""
        _init(project_root, writable=True)
        content = (project_root / "AGENTS.md").read_text()
        assert "/ingest" in content

    def test_writable_agents_md_has_enrich(self, project_root):
        """AGENTS.md in writable mode mentions /enrich."""
        _init(project_root, writable=True)
        content = (project_root / "AGENTS.md").read_text()
        assert "/enrich" in content


class TestOverwriteGuard:
    """init must not silently clobber user-owned files at the same paths."""

    def test_init_emits_marker_on_commands(self, project_root):
        """Every generated command file carries the All-Might marker."""
        _init(project_root, writable=True)
        cmds = project_root / ".opencode" / "commands"
        for name in ("search.md", "enrich.md", "ingest.md"):
            assert "<!-- all-might generated -->" in (cmds / name).read_text(), name

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
