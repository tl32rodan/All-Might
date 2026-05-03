"""Tests for the personalities composition layer (Part-D, downward symlinks).

Exercises ``allmight.core.personalities.compose`` and friends in the
Part-D model:

* Capability templates write project-wide globals
  (``search.md``, ``remember.md``, …) directly into ``.opencode/``.
* Each personality owns real, initially empty ``commands/`` and
  ``skills/`` subdirs where the agent may add personality-specific
  entries at runtime.
* ``compose`` projects every personality entry into
  ``.opencode/<kind>/<basename>`` as a relative symlink so OpenCode
  discovers it from the same global scan.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from allmight.core.markers import ALLMIGHT_MARKER_MD, ALLMIGHT_MARKER_TS
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
    """Build an instance under tmp_path/personalities/<n>/ with a few entries.

    Pre-fills personality-specific commands/skills (the case that
    actually exercises the projection — globals are written by
    capability templates, not by us here).
    """
    instance = Personality(
        template=_dummy_template(),
        project_root=tmp_path,
        name="demo-t",
        options={},
    )
    (instance.root / "commands").mkdir(parents=True)
    (instance.root / "commands" / "stdcell-special.md").write_text(
        f"{ALLMIGHT_MARKER_MD}\nour content\n"
    )
    (instance.root / "skills").mkdir(parents=True)
    (instance.root / "skills" / "audit.ts").write_text(
        f"{ALLMIGHT_MARKER_TS}\nour ts content\n"
    )
    return instance


class TestComposeFreshDirectory:
    def test_personality_dirs_become_real_empty_when_no_entries(
        self, tmp_path: Path,
    ) -> None:
        """A personality with no custom entries still gets the real
        empty ``commands/`` / ``skills/`` slots."""
        instance = Personality(
            template=_dummy_template(),
            project_root=tmp_path,
            name="bare-t",
            options={},
        )

        conflicts = compose(tmp_path, instance)

        assert conflicts == []
        assert (instance.root / "commands").is_dir()
        assert not (instance.root / "commands").is_symlink()
        assert (instance.root / "skills").is_dir()
        assert not (instance.root / "skills").is_symlink()

    def test_creates_downward_symlinks_when_target_empty(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)

        conflicts = compose(tmp_path, instance)

        assert conflicts == []
        link = tmp_path / ".opencode" / "commands" / "stdcell-special.md"
        assert link.is_symlink()
        assert link.resolve() == (instance.root / "commands" / "stdcell-special.md").resolve()

    def test_idempotent_when_run_twice(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)

        compose(tmp_path, instance)
        conflicts = compose(tmp_path, instance)

        assert conflicts == []


class TestComposeAutoResolves:
    def test_owned_markdown_file_at_dst_is_replaced(self, tmp_path: Path) -> None:
        """An All-Might-marked file at the projection target is treated
        as our own stale copy and auto-resolved by replacement."""
        instance = _make_instance(tmp_path)
        # Pre-existing All-Might-owned file at the target — we'd have
        # written it ourselves on a previous run.
        existing = tmp_path / ".opencode" / "commands" / "stdcell-special.md"
        existing.parent.mkdir(parents=True)
        existing.write_text(f"{ALLMIGHT_MARKER_MD}\nstale content\n")

        conflicts = compose(tmp_path, instance)

        # Marker-bearing files are NOT auto-resolved in the new model
        # because they could be capability-written globals. Force is
        # required; without it, the conflict is reported.
        assert len(conflicts) == 1


class TestComposeStagesUserConflicts:
    def test_user_authored_markdown_is_not_overwritten(self, tmp_path: Path) -> None:
        """A pre-existing user file at ``.opencode/<kind>/<basename>``
        without our marker stays put; conflict surfaced."""
        instance = _make_instance(tmp_path)
        user_file = tmp_path / ".opencode" / "commands" / "stdcell-special.md"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("user wrote this\n")

        conflicts = compose(tmp_path, instance)

        assert len(conflicts) == 1
        c = conflicts[0]
        assert isinstance(c, ComposeConflict)
        assert c.kind == "commands"
        assert c.basename == "stdcell-special.md"
        assert c.existing == "file"
        assert c.dst == user_file
        assert c.source == instance.root / "commands" / "stdcell-special.md"
        # User's content untouched.
        assert user_file.read_text() == "user wrote this\n"

    def test_symlink_to_elsewhere_is_preserved(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        elsewhere = tmp_path / "user_target.md"
        elsewhere.write_text("user target\n")
        user_file = tmp_path / ".opencode" / "commands" / "stdcell-special.md"
        user_file.parent.mkdir(parents=True)
        user_file.symlink_to(elsewhere.resolve())

        conflicts = compose(tmp_path, instance)

        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.existing == "symlink-to-elsewhere"
        assert user_file.is_symlink()
        assert user_file.resolve() == elsewhere.resolve()

    def test_force_overrides_user_file(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        user_file = tmp_path / ".opencode" / "commands" / "stdcell-special.md"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("user wrote this\n")

        conflicts = compose(tmp_path, instance, force=True)

        assert conflicts == []
        assert user_file.is_symlink()
        assert user_file.resolve() == (instance.root / "commands" / "stdcell-special.md").resolve()


class TestStageComposeConflicts:
    def test_writes_yaml_manifest(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        user_file = tmp_path / ".opencode" / "commands" / "stdcell-special.md"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("user wrote this\n")

        conflicts = compose(tmp_path, instance)
        path = stage_compose_conflicts(tmp_path, conflicts)

        assert path is not None
        assert path == tmp_path / ".allmight" / "templates" / "conflicts.yaml"
        payload = yaml.safe_load(path.read_text())
        rows = payload["compose_conflicts"]
        assert len(rows) == 1
        row = rows[0]
        assert row["instance"] == "demo-t"
        assert row["kind"] == "commands"
        assert row["basename"] == "stdcell-special.md"
        assert row["dst"] == ".opencode/commands/stdcell-special.md"
        assert row["source"] == "personalities/demo-t/commands/stdcell-special.md"
        assert row["existing"] == "file"

    def test_no_conflicts_removes_existing_manifest(self, tmp_path: Path) -> None:
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
