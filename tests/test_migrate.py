"""Tests for ``allmight migrate`` — the one-shot upgrader.

Covers detection (idempotent on already-migrated projects, fires on
legacy markers), and the apply path: rename instance dirs, drop
``/reflect``, split AGENTS.md by marker fences, refresh registry +
``.opencode/`` symlinks.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from allmight.cli import main
from allmight.migrate.migrator import detect, migrate


def _write_legacy_layout(root: Path) -> None:
    """Build a project shaped like the pre-Part-C layout.

    Mirrors what ``allmight init`` would have produced before this
    branch landed: project-prefixed instance dirs, single root
    AGENTS.md with both marker fences, a /reflect command, and a
    legacy personalities.yaml.
    """
    name = root.name
    (root / ".allmight").mkdir(parents=True)
    (root / ".allmight" / "personalities.yaml").write_text(
        "personalities:\n"
        f"- {{template: corpus_keeper, instance: {name}-corpus, version: 1.0.0}}\n"
        f"- {{template: memory_keeper, instance: {name}-memory, version: 1.0.0}}\n"
    )
    # Instance dirs
    (root / "personalities" / f"{name}-corpus" / "knowledge_graph").mkdir(parents=True)
    (root / "personalities" / f"{name}-corpus" / "commands").mkdir(parents=True)
    (root / "personalities" / f"{name}-memory" / "memory").mkdir(parents=True)
    (root / "personalities" / f"{name}-memory" / "commands").mkdir(parents=True)
    # Root AGENTS.md with both fences
    (root / "AGENTS.md").write_text(
        "# Project\n\n"
        "<!-- ALL-MIGHT -->\n"
        "## All-Might: Active Knowledge Graph (read-only)\n\n"
        "Corpus prose here.\n\n"
        "<!-- ALL-MIGHT-MEMORY -->\n"
        "## Agent Memory\n\n"
        "Memory prose here.\n"
    )
    # Legacy /reflect command + symlink-style stub
    (root / ".opencode" / "commands").mkdir(parents=True)
    (root / ".opencode" / "commands" / "reflect.md").write_text(
        "<!-- all-might generated -->\nlegacy /reflect body\n"
    )


class TestDetect:
    def test_detects_legacy_instance_dirs(self, tmp_path: Path) -> None:
        root = tmp_path / "demo"
        root.mkdir()
        _write_legacy_layout(root)

        plan = detect(root)

        assert plan.needs_migration
        assert plan.rename == {"demo-corpus": "knowledge", "demo-memory": "memory"}
        assert ".opencode/commands/reflect.md" in plan.dropped_files

    def test_no_op_on_fresh_project(self, tmp_path: Path) -> None:
        runner = CliRunner()
        root = tmp_path / "fresh"
        root.mkdir()
        result = runner.invoke(main, ["init", "--yes", str(root)])
        assert result.exit_code == 0

        plan = detect(root)

        assert not plan.needs_migration
        assert plan.rename == {}


class TestApply:
    def test_renames_instance_dirs(self, tmp_path: Path) -> None:
        root = tmp_path / "demo"
        root.mkdir()
        _write_legacy_layout(root)

        migrate(root)

        assert not (root / "personalities" / "demo-corpus").exists()
        assert not (root / "personalities" / "demo-memory").exists()
        assert (root / "personalities" / "knowledge").is_dir()
        assert (root / "personalities" / "memory").is_dir()

    def test_drops_reflect(self, tmp_path: Path) -> None:
        root = tmp_path / "demo"
        root.mkdir()
        _write_legacy_layout(root)

        migrate(root)

        assert not (root / ".opencode" / "commands" / "reflect.md").exists()

    def test_splits_agents_md_into_role_md(self, tmp_path: Path) -> None:
        root = tmp_path / "demo"
        root.mkdir()
        _write_legacy_layout(root)

        plan = migrate(root)

        corpus_role = root / "personalities" / "knowledge" / "ROLE.md"
        memory_role = root / "personalities" / "memory" / "ROLE.md"
        assert corpus_role.is_file()
        assert memory_role.is_file()
        assert "# Corpus Keeper" in corpus_role.read_text()
        assert "Corpus prose here." in corpus_role.read_text()
        assert "# Memory Keeper" in memory_role.read_text()
        assert "Memory prose here." in memory_role.read_text()
        # Plan reports the writes for human-readable summary.
        assert any("knowledge/ROLE.md" in entry for entry in plan.written_role_files)
        assert any("memory/ROLE.md" in entry for entry in plan.written_role_files)

    def test_personalities_yaml_uses_new_names(self, tmp_path: Path) -> None:
        root = tmp_path / "demo"
        root.mkdir()
        _write_legacy_layout(root)

        migrate(root)

        rows = yaml.safe_load(
            (root / ".allmight" / "personalities.yaml").read_text()
        )["personalities"]
        # Part-D rows use `name` instead of `instance`; reader still
        # accepts the legacy shape (test_personalities_shim covers that).
        names = {row["name"] for row in rows}
        assert names == {"knowledge", "memory"}

    def test_recomposes_root_agents_md(self, tmp_path: Path) -> None:
        root = tmp_path / "demo"
        root.mkdir()
        _write_legacy_layout(root)

        migrate(root)

        agents_md = (root / "AGENTS.md").read_text()
        # Root AGENTS.md is now the composed view — single marker at
        # top + both ROLE.md bodies stitched in.
        assert "<!-- all-might generated -->" in agents_md
        assert "# Corpus Keeper" in agents_md
        assert "# Memory Keeper" in agents_md
        # The legacy section fences are gone.
        assert "<!-- ALL-MIGHT -->" not in agents_md
        assert "<!-- ALL-MIGHT-MEMORY -->" not in agents_md

    def test_idempotent(self, tmp_path: Path) -> None:
        root = tmp_path / "demo"
        root.mkdir()
        _write_legacy_layout(root)

        migrate(root)
        plan = migrate(root)  # second run

        assert not plan.needs_migration


class TestDryRun:
    def test_dry_run_does_not_touch_disk(self, tmp_path: Path) -> None:
        root = tmp_path / "demo"
        root.mkdir()
        _write_legacy_layout(root)

        plan = migrate(root, dry_run=True)

        assert plan.needs_migration
        # Nothing was actually changed.
        assert (root / "personalities" / "demo-corpus").is_dir()
        assert (root / ".opencode" / "commands" / "reflect.md").is_file()


class TestCli:
    def test_cli_dry_run_prints_plan(self, tmp_path: Path) -> None:
        root = tmp_path / "demo"
        root.mkdir()
        _write_legacy_layout(root)

        runner = CliRunner()
        result = runner.invoke(main, ["migrate", str(root), "--dry-run"])

        assert result.exit_code == 0
        assert "personalities/demo-corpus/" in result.output
        assert "knowledge" in result.output
        assert "Re-run without --dry-run" in result.output

    def test_cli_no_op_on_clean_project(self, tmp_path: Path) -> None:
        runner = CliRunner()
        root = tmp_path / "clean"
        root.mkdir()
        result = runner.invoke(main, ["init", "--yes", str(root)])
        assert result.exit_code == 0

        result = runner.invoke(main, ["migrate", str(root)])

        assert result.exit_code == 0
        assert "Nothing to migrate" in result.output
