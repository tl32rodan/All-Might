"""Tests for the instance-level merge workflow.

The previous project-level ``ProjectMerger`` is replaced by
``InstanceMerger``: the unit of work is now a single personality
instance, not a whole All-Might project. Tests below cover the two
operating modes (combine vs side-by-side) and the dry-run path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from allmight.cli import main
from allmight.merge.merger import InstanceMerger


@pytest.fixture
def two_projects(tmp_path: Path) -> tuple[Path, Path]:
    """Two real allmight-init'd projects sharing the new layout."""
    from click.testing import CliRunner

    runner = CliRunner()
    src = tmp_path / "src_project"
    dst = tmp_path / "dst_project"
    src.mkdir()
    dst.mkdir()
    for path in (src, dst):
        result = runner.invoke(main, ["init", "--yes", str(path)])
        assert result.exit_code == 0, result.output
    return src, dst


class TestInstanceResolution:
    def test_unknown_instance_raises(self, two_projects: tuple[Path, Path]) -> None:
        src, dst = two_projects
        with pytest.raises(ValueError, match="no instance named"):
            InstanceMerger().merge(src, dst, instance_name="not-there")

    def test_non_allmight_source_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        dst = tmp_path / "dst"
        dst.mkdir()
        (dst / ".allmight").mkdir()
        (dst / ".allmight" / "personalities.yaml").write_text("personalities: []\n")
        with pytest.raises(ValueError, match="not an All-Might project"):
            InstanceMerger().merge(src, dst, instance_name="knowledge")


class TestSideBySide:
    """``--as <new-name>`` installs a second instance whole-cloth."""

    def test_creates_new_instance(self, two_projects: tuple[Path, Path]) -> None:
        src, dst = two_projects
        # Add a unique workspace under the source's knowledge instance so
        # we can detect that side-by-side actually copied content.
        ws = src / "personalities" / "knowledge" / "knowledge_graph" / "alpha"
        ws.mkdir(parents=True)
        (ws / "config.yaml").write_text("indices: []\n")

        InstanceMerger().merge(
            src, dst, instance_name="knowledge", as_name="alt_knowledge",
        )

        new_dir = dst / "personalities" / "alt_knowledge"
        assert new_dir.is_dir()
        assert (new_dir / "knowledge_graph" / "alpha" / "config.yaml").is_file()

    def test_registers_in_personalities_yaml(
        self, two_projects: tuple[Path, Path],
    ) -> None:
        src, dst = two_projects
        InstanceMerger().merge(src, dst, instance_name="knowledge", as_name="alt")
        rows = yaml.safe_load(
            (dst / ".allmight" / "personalities.yaml").read_text()
        )["personalities"]
        # Writer emits Part-D rows (`name` + `capabilities`); the
        # legacy `instance` key is gone.
        names = {row["name"] for row in rows}
        assert "alt" in names

    def test_collision_with_existing_name_raises(
        self, two_projects: tuple[Path, Path],
    ) -> None:
        src, dst = two_projects
        with pytest.raises(ValueError, match="already has personalities/knowledge"):
            InstanceMerger().merge(
                src, dst, instance_name="knowledge", as_name="knowledge",
            )


class TestCombine:
    """Default mode folds source content into a same-named target instance."""

    def test_new_files_copy_through(self, two_projects: tuple[Path, Path]) -> None:
        src, dst = two_projects
        # Stage a brand-new file under the source instance only; merge
        # should copy it into the target.
        kg_dir = src / "personalities" / "knowledge" / "knowledge_graph" / "alpha"
        kg_dir.mkdir(parents=True, exist_ok=True)
        (kg_dir / "config.yaml").write_text("indices: []\n")

        InstanceMerger().merge(src, dst, instance_name="knowledge")

        copied = dst / "personalities" / "knowledge" / "knowledge_graph" / "alpha" / "config.yaml"
        assert copied.is_file()

    def test_conflict_creates_incoming(self, two_projects: tuple[Path, Path]) -> None:
        src, dst = two_projects
        # Same workspace dir, different config content -> must produce .incoming.
        for project in (src, dst):
            kg_dir = project / "personalities" / "knowledge" / "knowledge_graph" / "alpha"
            kg_dir.mkdir(parents=True, exist_ok=True)
            # Real-shape config.yaml so the post-merge path-rewriter pass
            # has dict-like indices to iterate.
            (kg_dir / "config.yaml").write_text(
                "indices:\n"
                f"  - name: {project.name}\n"
                "    uri: ./store/x\n"
                "    description: x\n"
                "    paths: []\n"
            )

        report = InstanceMerger().merge(src, dst, instance_name="knowledge")

        incoming = (
            dst / "personalities" / "knowledge"
            / "knowledge_graph" / "alpha" / "config.incoming.yaml"
        )
        assert incoming.is_file(), report.memory_conflicts
        original = (
            dst / "personalities" / "knowledge"
            / "knowledge_graph" / "alpha" / "config.yaml"
        )
        assert "dst_project" in original.read_text()
        assert any("config.yaml" in entry for entry in report.memory_conflicts)

    def test_dry_run_does_not_write(self, two_projects: tuple[Path, Path]) -> None:
        src, dst = two_projects
        kg_dir = src / "personalities" / "knowledge" / "knowledge_graph" / "alpha"
        kg_dir.mkdir(parents=True, exist_ok=True)
        (kg_dir / "config.yaml").write_text("indices: []\n")

        report = InstanceMerger().merge(
            src, dst, instance_name="knowledge", dry_run=True,
        )

        assert not (
            dst / "personalities" / "knowledge"
            / "knowledge_graph" / "alpha" / "config.yaml"
        ).is_file()
        assert report.memory_files_added or report.workspaces_added


class TestRecomposeAfterMerge:
    """A successful merge re-runs compose() + compose_agents_md()."""

    def test_root_agents_md_still_marker_stamped(
        self, two_projects: tuple[Path, Path],
    ) -> None:
        src, dst = two_projects
        InstanceMerger().merge(src, dst, instance_name="knowledge")
        assert "<!-- all-might generated -->" in (dst / "AGENTS.md").read_text()


class TestCliMergeFlags:
    """Smoke test the new ``allmight merge`` command surface."""

    def test_cli_help_lists_new_flags(self) -> None:
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(main, ["merge", "--help"])
        assert result.exit_code == 0
        assert "--from" in result.output
        assert "--instance" in result.output
        assert "--as" in result.output
        assert "--dry-run" in result.output

    def test_cli_rejects_missing_required_flags(self) -> None:
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(main, ["merge"])
        # Click exits 2 for missing required options.
        assert result.exit_code == 2
        assert "--from" in result.output or "Missing option" in result.output
