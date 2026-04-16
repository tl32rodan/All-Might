"""Tests for reusable corpus linking.

Linked workspaces are symlinks inside ``knowledge_graph/`` that point to
external corpus directories.  Metadata is tracked in ``.links.yaml``.
"""

import os

import yaml
import pytest

from allmight.core.domain import LinkedWorkspace, LinksManifest
from allmight.detroit_smak.linker import WorkspaceLinker
from allmight.utils.links import (
    add_link,
    is_linked_workspace,
    load_links_manifest,
    remove_link,
    save_links_manifest,
)


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def kg_dir(tmp_path):
    """An empty knowledge_graph/ directory."""
    d = tmp_path / "knowledge_graph"
    d.mkdir()
    return d


@pytest.fixture
def external_corpus(tmp_path):
    """A valid external SMAK workspace with config.yaml."""
    corpus = tmp_path / "external" / "stdcell"
    corpus.mkdir(parents=True)
    (corpus / "store").mkdir()
    (corpus / "config.yaml").write_text(yaml.dump({
        "indices": [
            {"name": "rtl", "uri": "./store/rtl", "paths": ["./src/rtl"]},
        ]
    }))
    return corpus


@pytest.fixture
def linker():
    return WorkspaceLinker()


# ======================================================================
# LinksManifest I/O
# ======================================================================


class TestLinksManifestIO:

    def test_load_empty_manifest(self, kg_dir):
        manifest = load_links_manifest(kg_dir)
        assert manifest.links == []

    def test_load_nonexistent_dir(self, tmp_path):
        manifest = load_links_manifest(tmp_path / "nonexistent")
        assert manifest.links == []

    def test_save_and_load_roundtrip(self, kg_dir):
        original = LinksManifest(links=[
            LinkedWorkspace(name="stdcell", source="/shared/stdcell", readonly=True, description="test"),
            LinkedWorkspace(name="pll", source="/shared/pll", readonly=False, description=""),
        ])
        save_links_manifest(kg_dir, original)
        loaded = load_links_manifest(kg_dir)

        assert len(loaded.links) == 2
        assert loaded.links[0].name == "stdcell"
        assert loaded.links[0].source == "/shared/stdcell"
        assert loaded.links[0].readonly is True
        assert loaded.links[0].description == "test"
        assert loaded.links[1].name == "pll"
        assert loaded.links[1].readonly is False

    def test_add_link_to_empty_manifest(self, kg_dir):
        lw = LinkedWorkspace(name="corpus1", source="/tmp/corpus1")
        add_link(kg_dir, lw)

        manifest = load_links_manifest(kg_dir)
        assert len(manifest.links) == 1
        assert manifest.links[0].name == "corpus1"

    def test_add_link_replaces_existing(self, kg_dir):
        lw1 = LinkedWorkspace(name="corpus1", source="/path/a")
        lw2 = LinkedWorkspace(name="corpus1", source="/path/b")
        add_link(kg_dir, lw1)
        add_link(kg_dir, lw2)

        manifest = load_links_manifest(kg_dir)
        assert len(manifest.links) == 1
        assert manifest.links[0].source == "/path/b"

    def test_add_link_to_existing_manifest(self, kg_dir):
        add_link(kg_dir, LinkedWorkspace(name="a", source="/a"))
        add_link(kg_dir, LinkedWorkspace(name="b", source="/b"))

        manifest = load_links_manifest(kg_dir)
        assert len(manifest.links) == 2

    def test_remove_link(self, kg_dir):
        add_link(kg_dir, LinkedWorkspace(name="a", source="/a"))
        add_link(kg_dir, LinkedWorkspace(name="b", source="/b"))
        remove_link(kg_dir, "a")

        manifest = load_links_manifest(kg_dir)
        assert len(manifest.links) == 1
        assert manifest.links[0].name == "b"

    def test_remove_nonexistent_is_noop(self, kg_dir):
        add_link(kg_dir, LinkedWorkspace(name="a", source="/a"))
        remove_link(kg_dir, "missing")

        manifest = load_links_manifest(kg_dir)
        assert len(manifest.links) == 1

    def test_is_linked_workspace(self, kg_dir):
        add_link(kg_dir, LinkedWorkspace(name="a", source="/a"))
        assert is_linked_workspace(kg_dir, "a") is True
        assert is_linked_workspace(kg_dir, "b") is False

    def test_manifest_is_valid_yaml(self, kg_dir):
        add_link(kg_dir, LinkedWorkspace(name="x", source="/x", description="desc"))
        data = yaml.safe_load((kg_dir / ".links.yaml").read_text())
        assert "links" in data
        assert data["links"][0]["name"] == "x"


# ======================================================================
# WorkspaceLinker — link
# ======================================================================


class TestWorkspaceLinkerLink:

    def test_link_creates_symlink(self, kg_dir, external_corpus, linker):
        linker.link(kg_dir, external_corpus)
        link_path = kg_dir / "stdcell"
        assert link_path.is_symlink()
        assert link_path.is_dir()
        assert (link_path / "config.yaml").exists()

    def test_link_creates_manifest_entry(self, kg_dir, external_corpus, linker):
        linker.link(kg_dir, external_corpus)
        manifest = load_links_manifest(kg_dir)
        assert len(manifest.links) == 1
        assert manifest.links[0].name == "stdcell"
        assert manifest.links[0].source == str(external_corpus.resolve())

    def test_link_default_name_from_directory(self, kg_dir, external_corpus, linker):
        lw = linker.link(kg_dir, external_corpus)
        assert lw.name == "stdcell"

    def test_link_custom_name(self, kg_dir, external_corpus, linker):
        lw = linker.link(kg_dir, external_corpus, name="my-alias")
        assert lw.name == "my-alias"
        assert (kg_dir / "my-alias").is_symlink()
        assert not (kg_dir / "stdcell").exists()

    def test_link_readonly_default(self, kg_dir, external_corpus, linker):
        lw = linker.link(kg_dir, external_corpus)
        assert lw.readonly is True

    def test_link_writable(self, kg_dir, external_corpus, linker):
        lw = linker.link(kg_dir, external_corpus, readonly=False)
        assert lw.readonly is False

    def test_link_with_description(self, kg_dir, external_corpus, linker):
        lw = linker.link(kg_dir, external_corpus, description="Shared RTL corpus")
        assert lw.description == "Shared RTL corpus"

    def test_link_validates_source_has_config_yaml(self, kg_dir, tmp_path, linker):
        no_config = tmp_path / "no_config_dir"
        no_config.mkdir()
        with pytest.raises(ValueError, match="config.yaml"):
            linker.link(kg_dir, no_config)

    def test_link_rejects_nonexistent_source(self, kg_dir, tmp_path, linker):
        with pytest.raises(FileNotFoundError, match="not a directory"):
            linker.link(kg_dir, tmp_path / "does_not_exist")

    def test_link_rejects_conflict_with_existing_workspace(self, kg_dir, external_corpus, linker):
        # Create a real directory with the same name
        (kg_dir / "stdcell").mkdir()
        (kg_dir / "stdcell" / "config.yaml").write_text("indices: []")

        with pytest.raises(ValueError, match="already exists"):
            linker.link(kg_dir, external_corpus)

    def test_link_rejects_conflict_with_existing_symlink(self, kg_dir, external_corpus, linker):
        linker.link(kg_dir, external_corpus)
        with pytest.raises(ValueError, match="already exists"):
            linker.link(kg_dir, external_corpus)

    def test_link_creates_kg_dir_if_missing(self, tmp_path, external_corpus, linker):
        kg_dir = tmp_path / "project" / "knowledge_graph"
        linker.link(kg_dir, external_corpus)
        assert kg_dir.is_dir()
        assert (kg_dir / "stdcell").is_symlink()


# ======================================================================
# WorkspaceLinker — unlink
# ======================================================================


class TestWorkspaceLinkerUnlink:

    def test_unlink_removes_symlink(self, kg_dir, external_corpus, linker):
        linker.link(kg_dir, external_corpus)
        linker.unlink(kg_dir, "stdcell")
        assert not (kg_dir / "stdcell").exists()

    def test_unlink_updates_manifest(self, kg_dir, external_corpus, linker):
        linker.link(kg_dir, external_corpus)
        linker.unlink(kg_dir, "stdcell")
        manifest = load_links_manifest(kg_dir)
        assert len(manifest.links) == 0

    def test_unlink_refuses_real_directory(self, kg_dir, linker):
        real_ws = kg_dir / "real_workspace"
        real_ws.mkdir()
        (real_ws / "config.yaml").write_text("indices: []")

        with pytest.raises(ValueError, match="real directory"):
            linker.unlink(kg_dir, "real_workspace")

    def test_unlink_nonexistent_raises(self, kg_dir, linker):
        with pytest.raises(FileNotFoundError, match="No workspace"):
            linker.unlink(kg_dir, "missing")

    def test_unlink_does_not_touch_source(self, kg_dir, external_corpus, linker):
        linker.link(kg_dir, external_corpus)
        linker.unlink(kg_dir, "stdcell")
        # External corpus still intact
        assert external_corpus.is_dir()
        assert (external_corpus / "config.yaml").exists()


# ======================================================================
# WorkspaceLinker — validate
# ======================================================================


class TestWorkspaceLinkerValidate:

    def test_validate_healthy_links(self, kg_dir, external_corpus, linker):
        linker.link(kg_dir, external_corpus)
        warnings = linker.validate_links(kg_dir)
        assert warnings == []

    def test_validate_detects_broken_symlink(self, kg_dir, tmp_path, linker):
        # Create a corpus, link it, then delete the target
        corpus = tmp_path / "temp_corpus"
        corpus.mkdir()
        (corpus / "config.yaml").write_text("indices: []")
        linker.link(kg_dir, corpus)

        # Remove the target
        (corpus / "config.yaml").unlink()
        corpus.rmdir()

        warnings = linker.validate_links(kg_dir)
        assert len(warnings) == 1
        assert "broken" in warnings[0]

    def test_validate_detects_missing_symlink(self, kg_dir, external_corpus, linker):
        linker.link(kg_dir, external_corpus)
        # Remove the symlink but keep the manifest entry
        (kg_dir / "stdcell").unlink()

        warnings = linker.validate_links(kg_dir)
        assert len(warnings) == 1
        assert "missing" in warnings[0]

    def test_validate_detects_missing_config_yaml(self, kg_dir, tmp_path, linker):
        corpus = tmp_path / "no_config"
        corpus.mkdir()
        (corpus / "config.yaml").write_text("indices: []")
        linker.link(kg_dir, corpus)

        # Remove config.yaml from target
        (corpus / "config.yaml").unlink()

        warnings = linker.validate_links(kg_dir)
        assert len(warnings) == 1
        assert "config.yaml" in warnings[0]

    def test_validate_empty_manifest(self, kg_dir, linker):
        warnings = linker.validate_links(kg_dir)
        assert warnings == []


# ======================================================================
# WorkspaceLinker — list
# ======================================================================


class TestWorkspaceLinkerList:

    def test_list_empty(self, kg_dir, linker):
        assert linker.list_links(kg_dir) == []

    def test_list_returns_all_links(self, kg_dir, external_corpus, tmp_path, linker):
        # Create a second corpus
        corpus2 = tmp_path / "external" / "pll"
        corpus2.mkdir(parents=True)
        (corpus2 / "config.yaml").write_text("indices: []")

        linker.link(kg_dir, external_corpus, name="stdcell")
        linker.link(kg_dir, corpus2, name="pll")

        links = linker.list_links(kg_dir)
        names = [lw.name for lw in links]
        assert "stdcell" in names
        assert "pll" in names


# ======================================================================
# Workspace Discovery with Linked Workspaces
# ======================================================================


class TestLinkedWorkspaceDiscovery:

    def test_symlinked_workspace_discovered_by_scanning(self, kg_dir, external_corpus, linker):
        """The standard discovery pattern finds symlinked workspaces."""
        linker.link(kg_dir, external_corpus)

        workspaces = [
            d.name for d in sorted(kg_dir.iterdir())
            if d.is_dir() and (d / "config.yaml").exists()
            and not d.name.startswith(".")
        ]
        assert "stdcell" in workspaces

    def test_broken_symlink_not_discovered(self, kg_dir, tmp_path, linker):
        """Broken symlinks are skipped by the discovery pattern."""
        corpus = tmp_path / "temp_corpus"
        corpus.mkdir()
        (corpus / "config.yaml").write_text("indices: []")
        linker.link(kg_dir, corpus)

        # Break the symlink
        (corpus / "config.yaml").unlink()
        corpus.rmdir()

        workspaces = [
            d.name for d in sorted(kg_dir.iterdir())
            if d.is_dir() and (d / "config.yaml").exists()
            and not d.name.startswith(".")
        ]
        assert workspaces == []

    def test_mixed_real_and_linked_workspaces(self, kg_dir, external_corpus, linker):
        """Both real and linked workspaces are discovered together."""
        # Real workspace
        real_ws = kg_dir / "pll"
        real_ws.mkdir()
        (real_ws / "config.yaml").write_text("indices: []")

        # Linked workspace
        linker.link(kg_dir, external_corpus)

        workspaces = [
            d.name for d in sorted(kg_dir.iterdir())
            if d.is_dir() and (d / "config.yaml").exists()
            and not d.name.startswith(".")
        ]
        assert workspaces == ["pll", "stdcell"]

    def test_links_yaml_not_discovered_as_workspace(self, kg_dir, external_corpus, linker):
        """The .links.yaml file does not interfere with discovery."""
        linker.link(kg_dir, external_corpus)

        entries = [d.name for d in kg_dir.iterdir() if not d.name.startswith(".")]
        assert ".links.yaml" not in entries


# ======================================================================
# Merger with Linked Workspaces
# ======================================================================


class TestMergerWithLinks:

    def _make_project(self, root, workspaces=None):
        (root / ".allmight").mkdir(parents=True, exist_ok=True)
        (root / "knowledge_graph").mkdir(exist_ok=True)
        (root / "memory" / "understanding").mkdir(parents=True, exist_ok=True)
        (root / "memory" / "journal").mkdir(parents=True, exist_ok=True)
        (root / "memory" / "store").mkdir(parents=True, exist_ok=True)

        for ws_name, indices in (workspaces or {}).items():
            ws_dir = root / "knowledge_graph" / ws_name
            ws_dir.mkdir(parents=True, exist_ok=True)
            (ws_dir / "store").mkdir(exist_ok=True)
            config = {"indices": []}
            for idx_name, paths in indices.items():
                config["indices"].append({
                    "name": idx_name,
                    "uri": f"./store/{idx_name}",
                    "paths": paths,
                })
            (ws_dir / "config.yaml").write_text(yaml.dump(config))

    def test_merge_skips_linked_workspace_by_default(self, tmp_path):
        from allmight.merge.merger import ProjectMerger

        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()

        self._make_project(source)
        self._make_project(target)

        # Create external corpus and link it into source
        ext = tmp_path / "external_corpus"
        ext.mkdir()
        (ext / "config.yaml").write_text("indices: []")
        (ext / "store").mkdir()

        linker = WorkspaceLinker()
        linker.link(source / "knowledge_graph", ext)

        merger = ProjectMerger()
        report = merger.merge(source=source, target=target)

        assert "external_corpus" in report.workspaces_linked_skipped

    def test_merge_recreates_symlink_in_target(self, tmp_path):
        from allmight.merge.merger import ProjectMerger

        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()

        self._make_project(source)
        self._make_project(target)

        ext = tmp_path / "external_corpus"
        ext.mkdir()
        (ext / "config.yaml").write_text("indices: []")

        linker = WorkspaceLinker()
        linker.link(source / "knowledge_graph", ext)

        merger = ProjectMerger()
        merger.merge(source=source, target=target)

        target_link = target / "knowledge_graph" / "external_corpus"
        assert target_link.is_symlink()
        assert target_link.is_dir()

    def test_merge_copies_link_manifest_entry(self, tmp_path):
        from allmight.merge.merger import ProjectMerger

        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()

        self._make_project(source)
        self._make_project(target)

        ext = tmp_path / "external_corpus"
        ext.mkdir()
        (ext / "config.yaml").write_text("indices: []")

        linker = WorkspaceLinker()
        linker.link(source / "knowledge_graph", ext, description="shared corpus")

        merger = ProjectMerger()
        merger.merge(source=source, target=target)

        manifest = load_links_manifest(target / "knowledge_graph")
        assert len(manifest.links) == 1
        assert manifest.links[0].name == "external_corpus"

    def test_merge_report_includes_linked_skipped(self, tmp_path):
        from allmight.merge.merger import ProjectMerger

        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()

        self._make_project(source, workspaces={"real_ws": {"rtl": ["./src"]}})
        self._make_project(target)

        ext = tmp_path / "ext"
        ext.mkdir()
        (ext / "config.yaml").write_text("indices: []")

        linker = WorkspaceLinker()
        linker.link(source / "knowledge_graph", ext)

        merger = ProjectMerger()
        report = merger.merge(source=source, target=target)

        assert "ext" in report.workspaces_linked_skipped
        assert "real_ws" in report.workspaces_added


# ======================================================================
# SmakBridge Readonly Guard
# ======================================================================


class TestReadonlyGuard:

    def test_readonly_bridge_rejects_ingest(self):
        from allmight.bridge.smak_bridge import SmakBridge, SmakBridgeError

        bridge = SmakBridge(config="/tmp/fake.yaml", readonly=True)
        with pytest.raises(SmakBridgeError, match="read-only"):
            bridge.ingest()

    def test_readonly_bridge_rejects_enrich_symbol(self):
        from allmight.bridge.smak_bridge import SmakBridge, SmakBridgeError

        bridge = SmakBridge(config="/tmp/fake.yaml", readonly=True)
        with pytest.raises(SmakBridgeError, match="read-only"):
            bridge.enrich_symbol(file_path="test.py", symbol="Foo")

    def test_readonly_bridge_rejects_enrich_file(self):
        from allmight.bridge.smak_bridge import SmakBridge, SmakBridgeError

        bridge = SmakBridge(config="/tmp/fake.yaml", readonly=True)
        with pytest.raises(SmakBridgeError, match="read-only"):
            bridge.enrich_file(file_path="test.py")

    def test_writable_bridge_does_not_block(self):
        from allmight.bridge.smak_bridge import SmakBridge, SmakBridgeError

        bridge = SmakBridge(config="/tmp/fake.yaml", readonly=False)
        # These will fail because smak CLI doesn't exist, but NOT
        # with a "read-only" error
        with pytest.raises(SmakBridgeError, match="not found"):
            bridge.ingest()


# ======================================================================
# CLI Commands
# ======================================================================


class TestCorpusCli:

    def test_link_command(self, tmp_path, external_corpus, monkeypatch):
        from click.testing import CliRunner
        from allmight.cli import main

        project = tmp_path / "project"
        project.mkdir()
        (project / "knowledge_graph").mkdir()
        monkeypatch.chdir(project)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["corpus", "link", str(external_corpus)],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.output
        assert "Linked corpus" in result.output

    def test_unlink_command(self, tmp_path, external_corpus, monkeypatch):
        from click.testing import CliRunner
        from allmight.cli import main

        project = tmp_path / "project"
        project.mkdir()
        kg = project / "knowledge_graph"
        kg.mkdir()

        # Link first
        linker = WorkspaceLinker()
        linker.link(kg, external_corpus)

        monkeypatch.chdir(project)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["corpus", "unlink", "stdcell"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.output
        assert "Unlinked" in result.output

    def test_list_command_empty(self, tmp_path, monkeypatch):
        from click.testing import CliRunner
        from allmight.cli import main

        project = tmp_path / "project"
        project.mkdir()
        (project / "knowledge_graph").mkdir()
        monkeypatch.chdir(project)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["corpus", "list"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "No linked corpora" in result.output

    def test_list_command_shows_links(self, tmp_path, external_corpus, monkeypatch):
        from click.testing import CliRunner
        from allmight.cli import main

        project = tmp_path / "project"
        project.mkdir()
        kg = project / "knowledge_graph"
        kg.mkdir()

        linker = WorkspaceLinker()
        linker.link(kg, external_corpus, description="test corpus")

        monkeypatch.chdir(project)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["corpus", "list"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "stdcell" in result.output
