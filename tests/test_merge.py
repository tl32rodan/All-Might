"""Tests for One-for-All Merge — combining knowledge bases.

Feature 2: ``allmight merge <source>`` copies knowledge graph workspaces
and memory from another All-Might project into the current one.
Conflicts produce ``.incoming`` suffixes for agent-driven resolution
via ``/sync``.
"""

import yaml
import pytest

from allmight.merge.merger import ProjectMerger


def _make_allmight_project(root, workspaces=None, understanding=None, journal=None):
    """Create a minimal All-Might project structure.

    Args:
        root: Project root path.
        workspaces: dict of {name: {index_name: [paths]}} for knowledge_graph.
        understanding: dict of {name: content} for memory/understanding/.
        journal: dict of {subdir/filename: content} for memory/journal/.
    """
    # Mark as initialized
    (root / ".allmight").mkdir(parents=True, exist_ok=True)
    (root / "knowledge_graph").mkdir(exist_ok=True)
    (root / "memory" / "understanding").mkdir(parents=True, exist_ok=True)
    (root / "memory" / "journal").mkdir(parents=True, exist_ok=True)
    (root / "memory" / "store").mkdir(parents=True, exist_ok=True)

    # Create workspaces
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

    # Create understanding files
    for name, content in (understanding or {}).items():
        (root / "memory" / "understanding" / name).write_text(content)

    # Create journal entries
    for filepath, content in (journal or {}).items():
        journal_file = root / "memory" / "journal" / filepath
        journal_file.parent.mkdir(parents=True, exist_ok=True)
        journal_file.write_text(content)


@pytest.fixture
def source_project(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    return root


@pytest.fixture
def target_project(tmp_path):
    root = tmp_path / "target"
    root.mkdir()
    return root


@pytest.fixture
def merger():
    return ProjectMerger()


# ======================================================================
# Validation
# ======================================================================


class TestMergeValidation:
    """Merge validates source and target are All-Might projects."""

    def test_merge_rejects_non_allmight_source(self, target_project, tmp_path, merger):
        _make_allmight_project(target_project)
        empty_dir = tmp_path / "not_allmight"
        empty_dir.mkdir()

        with pytest.raises(ValueError, match="not.*All-Might"):
            merger.merge(source=empty_dir, target=target_project)

    def test_merge_rejects_non_allmight_target(self, source_project, tmp_path, merger):
        _make_allmight_project(source_project)
        empty_dir = tmp_path / "not_allmight"
        empty_dir.mkdir()

        with pytest.raises(ValueError, match="not.*All-Might"):
            merger.merge(source=source_project, target=empty_dir)

    def test_merge_accepts_source_with_knowledge_graph(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={"pll": {"rtl": ["./src"]}})
        _make_allmight_project(target_project)

        # Should not raise
        merger.merge(source=source_project, target=target_project)


# ======================================================================
# Workspace Merge
# ======================================================================


class TestWorkspaceMerge:
    """Copying workspaces from source to target."""

    def test_merge_copies_new_workspace(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={
            "pll": {"rtl": ["$DDI_ROOT_PATH/pll/rtl"]}
        })
        _make_allmight_project(target_project, workspaces={
            "stdcell": {"rtl": ["$DDI_ROOT_PATH/stdcell/rtl"]}
        })

        merger.merge(source=source_project, target=target_project)

        # Target now has both workspaces
        assert (target_project / "knowledge_graph" / "pll" / "config.yaml").exists()
        assert (target_project / "knowledge_graph" / "stdcell" / "config.yaml").exists()

    def test_merge_copies_workspace_config(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={
            "pll": {"rtl": ["$DDI_ROOT_PATH/pll/rtl"], "verif": ["$DDI_ROOT_PATH/pll/verif"]}
        })
        _make_allmight_project(target_project)

        merger.merge(source=source_project, target=target_project)

        config = yaml.safe_load(
            (target_project / "knowledge_graph" / "pll" / "config.yaml").read_text()
        )
        index_names = [idx["name"] for idx in config["indices"]]
        assert "rtl" in index_names
        assert "verif" in index_names

    def test_merge_conflicting_workspace_creates_incoming(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={
            "stdcell": {"rtl": ["$DDI_ROOT_PATH/source_stdcell/rtl"]}
        })
        _make_allmight_project(target_project, workspaces={
            "stdcell": {"rtl": ["$DDI_ROOT_PATH/target_stdcell/rtl"]}
        })

        merger.merge(source=source_project, target=target_project)

        # Original unchanged
        config = yaml.safe_load(
            (target_project / "knowledge_graph" / "stdcell" / "config.yaml").read_text()
        )
        assert config["indices"][0]["paths"] == ["$DDI_ROOT_PATH/target_stdcell/rtl"]

        # Incoming created
        incoming = target_project / "knowledge_graph" / "stdcell.incoming"
        assert incoming.is_dir()
        assert (incoming / "config.yaml").exists()

    def test_merge_multiple_workspaces(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={
            "pll": {"rtl": ["./src"]},
            "sram": {"rtl": ["./src"]},
            "io": {"rtl": ["./src"]},
        })
        _make_allmight_project(target_project, workspaces={
            "stdcell": {"rtl": ["./src"]}
        })

        merger.merge(source=source_project, target=target_project)

        kg = target_project / "knowledge_graph"
        ws_names = sorted(d.name for d in kg.iterdir() if d.is_dir())
        assert ws_names == ["io", "pll", "sram", "stdcell"]

    def test_merge_workspace_filter(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={
            "pll": {"rtl": ["./src"]},
            "sram": {"rtl": ["./src"]},
        })
        _make_allmight_project(target_project)

        merger.merge(source=source_project, target=target_project, workspaces=["pll"])

        assert (target_project / "knowledge_graph" / "pll").is_dir()
        assert not (target_project / "knowledge_graph" / "sram").exists()

    def test_merge_dry_run_copies_nothing(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={
            "pll": {"rtl": ["./src"]}
        })
        _make_allmight_project(target_project)

        report = merger.merge(source=source_project, target=target_project, dry_run=True)

        assert not (target_project / "knowledge_graph" / "pll").exists()
        assert report is not None
        assert "pll" in report.workspaces_added


# ======================================================================
# Memory Merge
# ======================================================================


class TestMemoryMerge:
    """Merging memory subsystem from source to target."""

    def test_merge_copies_new_understanding_files(self, source_project, target_project, merger):
        _make_allmight_project(source_project, understanding={
            "pll.md": "# PLL Architecture\nLock FSM with 3 states."
        })
        _make_allmight_project(target_project, understanding={
            "stdcell.md": "# Stdcell Architecture"
        })

        merger.merge(source=source_project, target=target_project)

        assert (target_project / "memory" / "understanding" / "pll.md").exists()
        assert (target_project / "memory" / "understanding" / "stdcell.md").exists()

    def test_merge_conflicting_understanding_creates_incoming(self, source_project, target_project, merger):
        _make_allmight_project(source_project, understanding={
            "stdcell.md": "# Source version"
        })
        _make_allmight_project(target_project, understanding={
            "stdcell.md": "# Target version"
        })

        merger.merge(source=source_project, target=target_project)

        # Original unchanged
        assert "Target version" in (target_project / "memory" / "understanding" / "stdcell.md").read_text()
        # Incoming created
        assert (target_project / "memory" / "understanding" / "stdcell.incoming.md").exists()
        assert "Source version" in (target_project / "memory" / "understanding" / "stdcell.incoming.md").read_text()

    def test_merge_copies_journal_entries(self, source_project, target_project, merger):
        _make_allmight_project(source_project, journal={
            "pll/2026-04-15-lock-fsm.md": "# Lock FSM analysis"
        })
        _make_allmight_project(target_project)

        merger.merge(source=source_project, target=target_project)

        assert (target_project / "memory" / "journal" / "pll" / "2026-04-15-lock-fsm.md").exists()

    def test_merge_skips_memory_store(self, source_project, target_project, merger):
        _make_allmight_project(source_project)
        # Add binary data to source store
        (source_project / "memory" / "store" / "index.bin").write_bytes(b"\x00\x01\x02")

        _make_allmight_project(target_project)

        merger.merge(source=source_project, target=target_project)

        assert not (target_project / "memory" / "store" / "index.bin").exists()

    def test_merge_never_touches_memory_md(self, source_project, target_project, merger):
        _make_allmight_project(source_project)
        (source_project / "MEMORY.md").write_text("# Source Memory")

        _make_allmight_project(target_project)
        (target_project / "MEMORY.md").write_text("# Target Memory")

        merger.merge(source=source_project, target=target_project)

        assert "Target Memory" in (target_project / "MEMORY.md").read_text()

    def test_merge_no_memory_flag_skips_all(self, source_project, target_project, merger):
        _make_allmight_project(source_project, understanding={
            "pll.md": "# PLL"
        }, journal={
            "pll/entry.md": "# Entry"
        })
        _make_allmight_project(target_project)

        merger.merge(source=source_project, target=target_project, no_memory=True)

        assert not (target_project / "memory" / "understanding" / "pll.md").exists()
        assert not (target_project / "memory" / "journal" / "pll").exists()


# ======================================================================
# Merge Report
# ======================================================================


class TestMergeReport:
    """Merge report generation."""

    def test_report_written_to_allmight_dir(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={"pll": {"rtl": ["./src"]}})
        _make_allmight_project(target_project)

        merger.merge(source=source_project, target=target_project)

        assert (target_project / ".allmight" / "merge-report.yaml").exists()

    def test_report_lists_added_workspaces(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={
            "pll": {"rtl": ["./src"]},
            "sram": {"rtl": ["./src"]},
        })
        _make_allmight_project(target_project)

        report = merger.merge(source=source_project, target=target_project)

        assert "pll" in report.workspaces_added
        assert "sram" in report.workspaces_added

    def test_report_lists_conflicting_workspaces(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={
            "stdcell": {"rtl": ["./src"]}
        })
        _make_allmight_project(target_project, workspaces={
            "stdcell": {"rtl": ["./src"]}
        })

        report = merger.merge(source=source_project, target=target_project)

        assert "stdcell" in report.workspaces_conflicting

    def test_report_lists_path_warnings(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={
            "pll": {"rtl": ["../../external/pll/rtl"]}
        })
        _make_allmight_project(target_project)

        report = merger.merge(source=source_project, target=target_project)

        assert len(report.warnings) > 0
        assert any("../../external/pll/rtl" in w for w in report.warnings)

    def test_report_lists_action_needed(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={
            "stdcell": {"rtl": ["./src"]}
        })
        _make_allmight_project(target_project, workspaces={
            "stdcell": {"rtl": ["./src"]}
        })

        report = merger.merge(source=source_project, target=target_project)

        assert any("/sync" in a for a in report.action_needed)

    def test_report_is_valid_yaml(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={"pll": {"rtl": ["./src"]}})
        _make_allmight_project(target_project)

        merger.merge(source=source_project, target=target_project)

        report_path = target_project / ".allmight" / "merge-report.yaml"
        data = yaml.safe_load(report_path.read_text())
        assert "merge" in data

    def test_dry_run_does_not_write_report_file(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={"pll": {"rtl": ["./src"]}})
        _make_allmight_project(target_project)

        merger.merge(source=source_project, target=target_project, dry_run=True)

        assert not (target_project / ".allmight" / "merge-report.yaml").exists()


# ======================================================================
# Sync skill installation after merge
# ======================================================================


class TestMergeInstallsSync:
    """Merge installs /sync skill and command for conflict resolution."""

    def test_merge_creates_sync_command(self, source_project, target_project, merger):
        _make_allmight_project(source_project, workspaces={"pll": {"rtl": ["./src"]}})
        _make_allmight_project(target_project)
        # Create .claude/commands so sync can be installed
        (target_project / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
        (target_project / ".claude" / "skills").mkdir(parents=True, exist_ok=True)

        merger.merge(source=source_project, target=target_project)

        assert (target_project / ".claude" / "commands" / "sync.md").exists()
        assert (target_project / ".claude" / "skills" / "sync" / "SKILL.md").exists()


# ======================================================================
# Merge with Symlinks (from cloned projects)
# ======================================================================


class TestMergeWithSymlinks:
    """Merging from a clone (source has symlinked workspaces)."""

    def test_merge_from_clone_copies_actual_content(self, tmp_path, target_project, merger):
        """When merging from a clone, shutil.copytree follows symlinks
        and copies actual directory contents, not symlinks."""
        import os

        # Create "original" project with a real workspace
        original = tmp_path / "original"
        _make_allmight_project(
            original, workspaces={"pll": {"rtl": ["./src"]}}
        )

        # Create "clone" project with symlinked workspace
        clone = tmp_path / "clone"
        _make_allmight_project(clone)
        os.symlink(
            str(original / "knowledge_graph" / "pll"),
            str(clone / "knowledge_graph" / "pll"),
        )

        # Merge clone into target
        _make_allmight_project(target_project)
        merger.merge(source=clone, target=target_project)

        # Target should have a real directory, not a symlink
        pll = target_project / "knowledge_graph" / "pll"
        assert pll.is_dir()
        assert not pll.is_symlink()
        assert (pll / "config.yaml").exists()
