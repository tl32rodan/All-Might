"""Tests for the personalities composition layer.

Exercises ``allmight.core.personalities.compose`` and friends to make
sure ``allmight init`` never silently overwrites user content under
``.opencode/`` and that the ``/sync`` manifest is correctly produced.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from allmight.core.markers import ALLMIGHT_MARKER_MD, ALLMIGHT_MARKER_TS
from allmight.core.personalities import (
    CliOption,
    ComposeConflict,
    Personality,
    PersonalityTemplate,
    compose,
    stage_compose_conflicts,
    write_init_scaffold,
)


def _dummy_template() -> PersonalityTemplate:
    """Minimal template — install/status are unused; we drive compose directly."""
    return PersonalityTemplate(
        name="t",
        short_name="t",
        version="1.0.0",
        description="",
        owned_paths=[],
        cli_options=[],
        install=lambda ctx, instance: None,  # type: ignore[arg-type]
        status=lambda root, instance: None,  # type: ignore[arg-type]
    )


def _make_instance(tmp_path: Path) -> Personality:
    """Build an instance under tmp_path/personalities/<n>/ with a few entries."""
    instance = Personality(
        template=_dummy_template(),
        project_root=tmp_path,
        name="demo-t",
        options={},
    )
    (instance.root / "commands").mkdir(parents=True)
    (instance.root / "commands" / "search.md").write_text(
        f"{ALLMIGHT_MARKER_MD}\nour content\n"
    )
    (instance.root / "plugins").mkdir(parents=True)
    (instance.root / "plugins" / "memory-load.ts").write_text(
        f"{ALLMIGHT_MARKER_TS}\nour ts content\n"
    )
    return instance


class TestComposeFreshDirectory:
    def test_creates_symlinks_when_target_empty(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)

        conflicts = compose(tmp_path, instance)

        assert conflicts == []
        link = tmp_path / ".opencode" / "commands" / "search.md"
        assert link.is_symlink()
        assert link.resolve() == (instance.root / "commands" / "search.md").resolve()

    def test_idempotent_when_run_twice(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)

        compose(tmp_path, instance)
        conflicts = compose(tmp_path, instance)

        assert conflicts == []


class TestComposeAutoResolves:
    """Files we own (carry the marker) auto-replace; no conflict surfaces."""

    def test_owned_markdown_file_is_replaced_by_symlink(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        legacy = tmp_path / ".opencode" / "commands" / "search.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_text(f"{ALLMIGHT_MARKER_MD}\nstale generated content\n")

        conflicts = compose(tmp_path, instance)

        assert conflicts == []
        assert legacy.is_symlink()

    def test_owned_typescript_plugin_is_replaced_by_symlink(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        legacy = tmp_path / ".opencode" / "plugins" / "memory-load.ts"
        legacy.parent.mkdir(parents=True)
        legacy.write_text(f"{ALLMIGHT_MARKER_TS}\nstale ts\n")

        conflicts = compose(tmp_path, instance)

        assert conflicts == []
        assert legacy.is_symlink()


class TestComposeStagesUserConflicts:
    """User-authored content is preserved and surfaced as a conflict."""

    def test_user_authored_markdown_is_not_overwritten(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        user_file = tmp_path / ".opencode" / "commands" / "search.md"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("MY OWN COMMAND — keep this\n")

        conflicts = compose(tmp_path, instance)

        # User content untouched
        assert user_file.read_text() == "MY OWN COMMAND — keep this\n"
        assert not user_file.is_symlink()
        # Conflict reported with full provenance
        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.kind == "commands"
        assert c.basename == "search.md"
        assert c.existing == "file"
        assert c.dst == user_file
        assert c.source == instance.root / "commands" / "search.md"
        assert c.instance_name == "demo-t"

    def test_symlink_to_elsewhere_is_preserved(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        # User created their own symlink to a custom command
        user_target = tmp_path / "my-search.md"
        user_target.write_text("custom\n")
        link = tmp_path / ".opencode" / "commands" / "search.md"
        link.parent.mkdir(parents=True)
        link.symlink_to(user_target)

        conflicts = compose(tmp_path, instance)

        assert link.is_symlink()
        assert link.resolve() == user_target.resolve()
        assert len(conflicts) == 1
        assert conflicts[0].existing == "symlink-to-elsewhere"

    def test_force_overrides_user_file(self, tmp_path: Path) -> None:
        """``--force`` is the explicit-intent escape hatch."""
        instance = _make_instance(tmp_path)
        user_file = tmp_path / ".opencode" / "commands" / "search.md"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("MY OWN — but I want all-might to clobber\n")

        conflicts = compose(tmp_path, instance, force=True)

        assert conflicts == []
        assert user_file.is_symlink()


class TestStageComposeConflicts:
    def test_writes_yaml_manifest(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        user_file = tmp_path / ".opencode" / "commands" / "search.md"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("user authored\n")

        conflicts = compose(tmp_path, instance)
        path = stage_compose_conflicts(tmp_path, conflicts)

        assert path == tmp_path / ".allmight" / "templates" / "conflicts.yaml"
        manifest = yaml.safe_load(path.read_text())
        rows = manifest["compose_conflicts"]
        assert len(rows) == 1
        row = rows[0]
        # Paths are recorded relative to project_root so /sync can locate
        # them regardless of where the project lives on disk.
        assert row["dst"] == ".opencode/commands/search.md"
        assert row["source"] == "personalities/demo-t/commands/search.md"
        assert row["existing"] == "file"

    def test_no_conflicts_clears_stale_manifest(self, tmp_path: Path) -> None:
        path = tmp_path / ".allmight" / "templates" / "conflicts.yaml"
        path.parent.mkdir(parents=True)
        path.write_text("compose_conflicts: [{instance: x, kind: c, basename: a}]\n")

        result = stage_compose_conflicts(tmp_path, [])

        # Stale manifest from a previous run is removed so /sync isn't
        # tricked into resolving conflicts that no longer exist.
        assert result is None
        assert not path.exists()


class TestWriteInitScaffold:
    def test_preserves_existing_schema(self, tmp_path: Path) -> None:
        opencode_dir = tmp_path / ".opencode"
        opencode_dir.mkdir()
        (opencode_dir / "opencode.json").write_text(json.dumps({
            "$schema": "https://corp-mirror.example.com/opencode/config.json",
            "model": "claude-opus-4-7",
        }))

        write_init_scaffold(tmp_path)

        cfg = json.loads((opencode_dir / "opencode.json").read_text())
        # User's $schema and unrelated settings survive the scaffold.
        assert cfg["$schema"] == "https://corp-mirror.example.com/opencode/config.json"
        assert cfg["model"] == "claude-opus-4-7"

    def test_adds_schema_when_missing(self, tmp_path: Path) -> None:
        opencode_dir = tmp_path / ".opencode"
        opencode_dir.mkdir()
        (opencode_dir / "opencode.json").write_text(json.dumps({"model": "x"}))

        write_init_scaffold(tmp_path)

        cfg = json.loads((opencode_dir / "opencode.json").read_text())
        assert cfg["$schema"] == "https://opencode.ai/config.json"
        assert cfg["model"] == "x"

    def test_preserves_existing_dependencies(self, tmp_path: Path) -> None:
        opencode_dir = tmp_path / ".opencode"
        opencode_dir.mkdir()
        (opencode_dir / "package.json").write_text(json.dumps({
            "name": "user-project",
            "dependencies": {
                "@opencode-ai/plugin": "1.2.3",
                "lodash": "^4",
            },
        }))

        write_init_scaffold(tmp_path)

        pkg = json.loads((opencode_dir / "package.json").read_text())
        # User's pinned plugin version isn't bumped to "latest"; their
        # other deps survive.
        assert pkg["dependencies"]["@opencode-ai/plugin"] == "1.2.3"
        assert pkg["dependencies"]["lodash"] == "^4"
        assert pkg["name"] == "user-project"


class TestIntegrationCliInit:
    """End-to-end: pre-existing .opencode/ + allmight init produces a
    conflict manifest, never clobbers the user's command."""

    def test_preexisting_command_is_not_clobbered(self, tmp_path: Path) -> None:
        # Pre-populate a directory as if the user already used OpenCode.
        opencode_dir = tmp_path / ".opencode"
        opencode_dir.mkdir()
        (opencode_dir / "opencode.json").write_text(json.dumps({
            "$schema": "https://corp-mirror.example.com/opencode/config.json",
        }))
        (opencode_dir / "commands").mkdir()
        (opencode_dir / "commands" / "search.md").write_text(
            "MY HAND-WRITTEN SEARCH COMMAND\n"
        )

        from click.testing import CliRunner

        from allmight.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["init", str(tmp_path)])

        assert result.exit_code == 0, result.output
        # User's file is untouched.
        assert (opencode_dir / "commands" / "search.md").read_text() == \
            "MY HAND-WRITTEN SEARCH COMMAND\n"
        # And the user's $schema choice is preserved.
        cfg = json.loads((opencode_dir / "opencode.json").read_text())
        assert cfg["$schema"] == "https://corp-mirror.example.com/opencode/config.json"
        # Conflict manifest is produced.
        manifest = yaml.safe_load(
            (tmp_path / ".allmight" / "templates" / "conflicts.yaml").read_text()
        )
        names = {row["basename"] for row in manifest["compose_conflicts"]}
        assert "search.md" in names
        # User-facing output points at /sync.
        assert "/sync" in result.output
