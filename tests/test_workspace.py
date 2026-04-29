"""Test Group 2: Workspace Management.

SMAK workspaces live inside knowledge_graph/. Each has its own
config.yaml and store/. All-Might discovers them by scanning.
"""

import yaml
import pytest


@pytest.fixture
def project_root(tmp_path):
    """An initialized All-Might project (post-init)."""
    from allmight.personalities.corpus_keeper.scanner import ProjectScanner
    from allmight.personalities.corpus_keeper.initializer import ProjectInitializer

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

    manifest = ProjectScanner().scan(tmp_path)
    ProjectInitializer().initialize(manifest)
    return tmp_path


@pytest.fixture
def project_with_workspaces(project_root):
    """Project with 3 SMAK workspaces pre-created."""
    kg = project_root / "knowledge_graph"

    # stdcell: EDA workspace
    stdcell = kg / "stdcell"
    stdcell.mkdir(parents=True)
    (stdcell / "store").mkdir()
    with open(stdcell / "config.yaml", "w") as f:
        yaml.dump({
            "indices": [
                {"name": "rtl", "uri": "./store/rtl", "paths": ["$DDI_ROOT_PATH/stdcell/rtl"]},
                {"name": "verif", "uri": "./store/verif", "paths": ["$DDI_ROOT_PATH/stdcell/verif"]},
            ]
        }, f)

    # io_phy: EDA workspace
    io_phy = kg / "io_phy"
    io_phy.mkdir(parents=True)
    (io_phy / "store").mkdir()
    with open(io_phy / "config.yaml", "w") as f:
        yaml.dump({
            "indices": [
                {"name": "rtl", "uri": "./store/rtl", "paths": ["$DDI_ROOT_PATH/io_phy/rtl"]},
            ]
        }, f)

    # pll: software workspace
    pll = kg / "pll"
    pll.mkdir(parents=True)
    (pll / "store").mkdir()
    with open(pll / "config.yaml", "w") as f:
        yaml.dump({
            "indices": [
                {"name": "source_code", "uri": "./store/source_code", "paths": ["./src"]},
            ]
        }, f)

    return project_root


class TestWorkspaceDiscovery:

    def test_discover_workspaces_by_scanning(self, project_with_workspaces):
        """Scanning knowledge_graph/ finds all workspaces with config.yaml."""
        kg = project_with_workspaces / "knowledge_graph"
        workspaces = [
            d.name for d in sorted(kg.iterdir())
            if d.is_dir() and (d / "config.yaml").exists()
        ]
        assert workspaces == ["io_phy", "pll", "stdcell"]

    def test_discover_empty_knowledge_graph(self, project_root):
        """Empty knowledge_graph/ returns no workspaces."""
        kg = project_root / "knowledge_graph"
        workspaces = [
            d.name for d in kg.iterdir()
            if d.is_dir() and (d / "config.yaml").exists()
        ]
        assert workspaces == []

    def test_each_workspace_has_own_config(self, project_with_workspaces):
        """Each workspace has its own SMAK config.yaml with indices."""
        kg = project_with_workspaces / "knowledge_graph"

        stdcell_cfg = yaml.safe_load((kg / "stdcell" / "config.yaml").read_text())
        assert "indices" in stdcell_cfg
        assert any(i["name"] == "rtl" for i in stdcell_cfg["indices"])

        pll_cfg = yaml.safe_load((kg / "pll" / "config.yaml").read_text())
        assert any(i["name"] == "source_code" for i in pll_cfg["indices"])

    def test_workspace_store_dir(self, project_with_workspaces):
        """Each workspace has a store/ directory for search data."""
        kg = project_with_workspaces / "knowledge_graph"
        for ws_name in ("stdcell", "io_phy", "pll"):
            assert (kg / ws_name / "store").is_dir()

    def test_no_config_yaml_at_project_root(self, project_with_workspaces):
        """Project root has no config.yaml even with workspaces."""
        assert not (project_with_workspaces / "config.yaml").exists()


# ------------------------------------------------------------------
# Symlink compatibility
# ------------------------------------------------------------------


class TestWorkspaceSymlinks:
    """knowledge_graph/ supports both symlinks and real directories."""

    def test_symlinked_workspace_discovered(self, project_root, tmp_path):
        """A symlinked workspace is discovered as a valid workspace."""
        import os

        # Create a real workspace outside knowledge_graph/
        external_ws = tmp_path / "external_ws"
        external_ws.mkdir()
        (external_ws / "config.yaml").write_text("indices:\n  - name: ext\n")
        (external_ws / "store").mkdir()

        # Symlink it into knowledge_graph/
        link = project_root / "knowledge_graph" / "external"
        os.symlink(str(external_ws), str(link))

        kg = project_root / "knowledge_graph"
        workspaces = [
            d.name for d in sorted(kg.iterdir())
            if d.is_dir() and (d / "config.yaml").exists()
        ]
        assert "external" in workspaces

    def test_symlinked_workspace_config_readable(self, project_root, tmp_path):
        """config.yaml in a symlinked workspace is readable."""
        import os
        import yaml

        external_ws = tmp_path / "ext_ws2"
        external_ws.mkdir()
        (external_ws / "config.yaml").write_text(
            "indices:\n  - name: source_code\n    uri: ./store/sc\n"
        )

        link = project_root / "knowledge_graph" / "linked"
        os.symlink(str(external_ws), str(link))

        cfg = yaml.safe_load((link / "config.yaml").read_text())
        assert cfg["indices"][0]["name"] == "source_code"

    def test_broken_symlink_skipped(self, project_root):
        """A broken symlink in knowledge_graph/ is silently skipped."""
        import os

        broken = project_root / "knowledge_graph" / "broken"
        os.symlink("/nonexistent/path", str(broken))

        kg = project_root / "knowledge_graph"
        # is_dir() returns False for broken symlinks, so they're skipped
        workspaces = [
            d.name for d in sorted(kg.iterdir())
            if d.is_dir() and (d / "config.yaml").exists()
        ]
        assert "broken" not in workspaces
