"""Tests for the personalities composition layer (Part-D).

Exercises ``allmight.core.personalities.compose`` and friends in the
new model where capability templates write the agent surface
directly into ``.opencode/`` and ``compose`` only writes the upward
symlinks ``personalities/<p>/{skills,commands} → ../../.opencode/...``.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from allmight.core.personalities import (
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
    """Build a personality rooted at ``tmp_path/personalities/<n>/``.

    Empty: in the Part-D model the per-instance ``commands/`` /
    ``skills/`` dirs are created by ``compose`` as upward symlinks,
    not by capability templates writing per-instance copies.
    """
    return Personality(
        template=_dummy_template(),
        project_root=tmp_path,
        name="demo-t",
        options={},
    )


class TestComposeFreshDirectory:
    def test_creates_upward_skills_symlink(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)

        conflicts = compose(tmp_path, instance)

        assert conflicts == []
        link = instance.root / "skills"
        assert link.is_symlink()
        assert os.readlink(link) == "../../.opencode/skills"
        # Resolve target via the link's parent so the relative path
        # turns into an absolute one.
        assert link.resolve() == (tmp_path / ".opencode" / "skills").resolve()

    def test_creates_upward_commands_symlink(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)

        conflicts = compose(tmp_path, instance)

        assert conflicts == []
        link = instance.root / "commands"
        assert link.is_symlink()
        assert os.readlink(link) == "../../.opencode/commands"
        assert link.resolve() == (tmp_path / ".opencode" / "commands").resolve()

    def test_idempotent_when_run_twice(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)

        compose(tmp_path, instance)
        conflicts = compose(tmp_path, instance)

        assert conflicts == []
        assert (instance.root / "skills").is_symlink()
        assert (instance.root / "commands").is_symlink()

    def test_creates_global_target_dir(self, tmp_path: Path) -> None:
        """Compose ensures ``.opencode/<kind>/`` exists so the upward
        symlink resolves on read."""
        instance = _make_instance(tmp_path)

        compose(tmp_path, instance)

        assert (tmp_path / ".opencode" / "skills").is_dir()
        assert (tmp_path / ".opencode" / "commands").is_dir()


class TestComposeStagesUserConflicts:
    def test_real_directory_is_preserved(self, tmp_path: Path) -> None:
        """A pre-existing real ``personalities/<p>/commands/`` dir is a
        conflict — compose refuses to nuke user content."""
        instance = _make_instance(tmp_path)
        user_dir = instance.root / "commands"
        user_dir.mkdir(parents=True)
        (user_dir / "ours.md").write_text("user wrote this\n")

        conflicts = compose(tmp_path, instance)

        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.kind == "commands"
        assert c.existing == "directory"
        assert c.dst == user_dir
        # Original content untouched.
        assert (user_dir / "ours.md").read_text() == "user wrote this\n"

    def test_real_file_is_preserved(self, tmp_path: Path) -> None:
        """A pre-existing regular file at the symlink target is a
        conflict; compose leaves it alone."""
        instance = _make_instance(tmp_path)
        instance.root.mkdir(parents=True)
        target = instance.root / "skills"
        target.write_text("not a dir\n")

        conflicts = compose(tmp_path, instance)

        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.kind == "skills"
        assert c.existing == "file"
        assert target.read_text() == "not a dir\n"

    def test_symlink_to_elsewhere_is_preserved(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        instance.root.mkdir(parents=True)
        elsewhere = tmp_path / "user_skills"
        elsewhere.mkdir()
        link = instance.root / "skills"
        link.symlink_to(elsewhere.resolve())

        conflicts = compose(tmp_path, instance)

        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.kind == "skills"
        assert c.existing == "symlink-to-elsewhere"
        # User's symlink intact.
        assert link.is_symlink()
        assert link.resolve() == elsewhere.resolve()

    def test_force_overrides_real_directory(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        user_dir = instance.root / "commands"
        user_dir.mkdir(parents=True)
        (user_dir / "ours.md").write_text("user wrote this\n")

        conflicts = compose(tmp_path, instance, force=True)

        assert conflicts == []
        link = instance.root / "commands"
        assert link.is_symlink()
        assert os.readlink(link) == "../../.opencode/commands"

    def test_force_overrides_symlink_to_elsewhere(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        instance.root.mkdir(parents=True)
        elsewhere = tmp_path / "user_skills"
        elsewhere.mkdir()
        link = instance.root / "skills"
        link.symlink_to(elsewhere.resolve())

        conflicts = compose(tmp_path, instance, force=True)

        assert conflicts == []
        assert os.readlink(link) == "../../.opencode/skills"


class TestStageComposeConflicts:
    def test_writes_yaml_manifest(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        user_dir = instance.root / "commands"
        user_dir.mkdir(parents=True)
        (user_dir / "ours.md").write_text("user wrote this\n")

        conflicts = compose(tmp_path, instance)
        path = stage_compose_conflicts(tmp_path, conflicts)

        assert path is not None
        assert path == tmp_path / ".allmight" / "templates" / "conflicts.yaml"
        payload = yaml.safe_load(path.read_text())
        assert "compose_conflicts" in payload
        rows = payload["compose_conflicts"]
        assert len(rows) == 1
        assert rows[0]["instance"] == "demo-t"
        assert rows[0]["kind"] == "commands"
        assert rows[0]["existing"] == "directory"

    def test_no_conflicts_removes_existing_manifest(self, tmp_path: Path) -> None:
        # Prime an existing manifest, then call stage_compose_conflicts
        # with [] — the file should disappear.
        path = tmp_path / ".allmight" / "templates" / "conflicts.yaml"
        path.parent.mkdir(parents=True)
        path.write_text("compose_conflicts: []\n")

        result = stage_compose_conflicts(tmp_path, [])

        assert result is None
        assert not path.exists()


class TestWriteInitScaffold:
    def test_creates_personalities_dir(self, tmp_path: Path) -> None:
        write_init_scaffold(tmp_path)
        assert (tmp_path / "personalities").is_dir()

    def test_creates_dot_opencode_skeleton(self, tmp_path: Path) -> None:
        write_init_scaffold(tmp_path)
        assert (tmp_path / ".opencode" / "opencode.json").is_file()
