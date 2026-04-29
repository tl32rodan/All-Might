"""Tests for `allmight clone` — read-only clone with symlinked workspaces.

Clone creates a new All-Might project where knowledge_graph/ workspaces
are symlinks to the source. The clone is always read-only.
"""

import os

import pytest

from allmight.clone.cloner import ProjectCloner
from allmight.personalities.corpus_keeper.initializer import ProjectInitializer
from allmight.personalities.corpus_keeper.scanner import ProjectScanner
from allmight.memory.initializer import MemoryInitializer


@pytest.fixture
def source_project(tmp_path):
    """A fully initialized All-Might project to clone from."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "src").mkdir()
    (source / "src" / "main.py").write_text("def hello(): pass\n")
    (source / "pyproject.toml").write_text("[project]\nname = 'source'\n")

    manifest = ProjectScanner().scan(source)
    ProjectInitializer().initialize(manifest, writable=True)
    MemoryInitializer().initialize(source)

    # Create a fake workspace with config.yaml
    ws = source / "knowledge_graph" / "rtl"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "config.yaml").write_text("indices:\n  - name: rtl\n")
    (ws / "store").mkdir()

    return source


@pytest.fixture
def target_dir(tmp_path):
    """Empty directory to clone into."""
    target = tmp_path / "target"
    target.mkdir()
    return target


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------


class TestCloneValidation:

    def test_rejects_non_allmight_source(self, tmp_path, target_dir):
        """Source must be an All-Might project."""
        not_allmight = tmp_path / "not_allmight"
        not_allmight.mkdir()
        with pytest.raises(ValueError, match="not an All-Might project"):
            ProjectCloner().clone(not_allmight, target_dir)

    def test_accepts_valid_source(self, source_project, target_dir):
        """Valid All-Might project is accepted."""
        report = ProjectCloner().clone(source_project, target_dir)
        assert report is not None


# ------------------------------------------------------------------
# Workspace Symlinks
# ------------------------------------------------------------------


class TestCloneWorkspaces:

    def test_creates_symlinks(self, source_project, target_dir):
        """Workspaces in target are symlinks."""
        ProjectCloner().clone(source_project, target_dir)
        ws = target_dir / "knowledge_graph" / "rtl"
        assert ws.is_symlink()

    def test_symlinks_point_to_source(self, source_project, target_dir):
        """Symlinks resolve to the source workspace directories."""
        ProjectCloner().clone(source_project, target_dir)
        ws = target_dir / "knowledge_graph" / "rtl"
        assert ws.resolve() == (source_project / "knowledge_graph" / "rtl").resolve()

    def test_config_yaml_accessible(self, source_project, target_dir):
        """config.yaml in symlinked workspace is readable."""
        ProjectCloner().clone(source_project, target_dir)
        config = target_dir / "knowledge_graph" / "rtl" / "config.yaml"
        assert config.exists()
        assert "rtl" in config.read_text()

    def test_report_lists_linked_workspaces(self, source_project, target_dir):
        """CloneReport lists the workspaces that were linked."""
        report = ProjectCloner().clone(source_project, target_dir)
        assert "rtl" in report.workspaces_linked

    def test_empty_knowledge_graph(self, tmp_path, target_dir):
        """Source with empty knowledge_graph/ clones successfully."""
        source = tmp_path / "empty_src"
        source.mkdir()
        (source / "knowledge_graph").mkdir()
        (source / ".allmight").mkdir()

        report = ProjectCloner().clone(source, target_dir)
        assert report.workspaces_linked == []


# ------------------------------------------------------------------
# Read-only Mode
# ------------------------------------------------------------------


class TestCloneIsReadOnly:

    def test_mode_is_readonly(self, source_project, target_dir):
        """Cloned project is always read-only."""
        ProjectCloner().clone(source_project, target_dir)
        mode_file = target_dir / ".allmight" / "mode"
        assert mode_file.exists()
        assert mode_file.read_text().strip() == "read-only"

    def test_no_ingest_command(self, source_project, target_dir):
        """Clone does NOT have ingest.md command."""
        ProjectCloner().clone(source_project, target_dir)
        assert not (target_dir / ".opencode" / "commands" / "ingest.md").exists()

    def test_no_enrich_command(self, source_project, target_dir):
        """Clone does NOT have enrich.md command."""
        ProjectCloner().clone(source_project, target_dir)
        assert not (target_dir / ".opencode" / "commands" / "enrich.md").exists()

    def test_has_search_command(self, source_project, target_dir):
        """Clone still has search.md command."""
        ProjectCloner().clone(source_project, target_dir)
        assert (target_dir / ".opencode" / "commands" / "search.md").exists()

    def test_agents_md_emphasizes_readonly(self, source_project, target_dir):
        """AGENTS.md in clone emphasizes read-only access."""
        ProjectCloner().clone(source_project, target_dir)
        content = (target_dir / "AGENTS.md").read_text()
        assert "read-only" in content.lower()


# ------------------------------------------------------------------
# Memory (fresh, not copied from source)
# ------------------------------------------------------------------


class TestCloneMemory:

    def test_creates_fresh_memory_md(self, source_project, target_dir):
        """Clone creates a new MEMORY.md, not copied from source."""
        # Write something to source memory
        (source_project / "MEMORY.md").write_text("# Source Memory\nSource-specific content.\n")
        ProjectCloner().clone(source_project, target_dir)

        content = (target_dir / "MEMORY.md").read_text()
        assert "Source-specific content" not in content

    def test_creates_l2_dir(self, source_project, target_dir):
        """Clone creates memory/understanding/ (L2)."""
        ProjectCloner().clone(source_project, target_dir)
        assert (target_dir / "memory" / "understanding").is_dir()

    def test_creates_l3_dir(self, source_project, target_dir):
        """Clone creates memory/journal/ (L3)."""
        ProjectCloner().clone(source_project, target_dir)
        assert (target_dir / "memory" / "journal").is_dir()

    def test_does_not_copy_source_memory(self, source_project, target_dir):
        """Clone does NOT copy source's memory/understanding/ content."""
        (source_project / "memory" / "understanding" / "rtl.md").write_text("# RTL notes\n")
        ProjectCloner().clone(source_project, target_dir)

        # Target should have empty understanding dir
        files = list((target_dir / "memory" / "understanding").iterdir())
        assert len(files) == 0


# ------------------------------------------------------------------
# Provenance
# ------------------------------------------------------------------


class TestCloneProvenance:

    def test_records_source_path(self, source_project, target_dir):
        """Clone records the source path in .allmight/clone-source."""
        ProjectCloner().clone(source_project, target_dir)
        provenance = target_dir / ".allmight" / "clone-source"
        assert provenance.exists()
        assert str(source_project) in provenance.read_text()

    def test_creates_allmight_dir(self, source_project, target_dir):
        """Clone creates .allmight/ marker directory."""
        ProjectCloner().clone(source_project, target_dir)
        assert (target_dir / ".allmight").is_dir()
