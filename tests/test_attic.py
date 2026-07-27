"""Unit tests for ``allmight.core.attic`` — the quarantine bin.

The invariant: ``allmight init`` never deletes. Anything the framework
retires is *moved* under ``.allmight/attic/`` keeping its original
project-relative path, so ``/sync`` can point the user at it.
"""

from __future__ import annotations

from pathlib import Path

from allmight.core.attic import attic_root, quarantine


def test_moves_file_preserving_relative_path(tmp_path: Path):
    src = tmp_path / ".opencode" / "plugins" / "gone.ts"
    src.parent.mkdir(parents=True)
    src.write_text("body\n")

    dest = quarantine(tmp_path, src)

    assert dest == attic_root(tmp_path) / ".opencode" / "plugins" / "gone.ts"
    assert dest.read_text() == "body\n"
    assert not src.exists()


def test_second_quarantine_does_not_clobber_the_first(tmp_path: Path):
    src = tmp_path / "a.ts"
    src.write_text("first\n")
    first = quarantine(tmp_path, src)
    src.write_text("second\n")
    second = quarantine(tmp_path, src)

    assert first is not None and second is not None
    assert first != second
    assert second.name == "a.ts.1"
    assert {first.read_text(), second.read_text()} == {"first\n", "second\n"}


def test_missing_path_is_a_no_op(tmp_path: Path):
    assert quarantine(tmp_path, tmp_path / "nope.ts") is None
    assert not attic_root(tmp_path).exists()


def test_path_outside_the_project_falls_back_to_basename(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.ts"
    outside.write_text("x\n")
    try:
        dest = quarantine(tmp_path, outside)
        assert dest == attic_root(tmp_path) / outside.name
        assert dest.read_text() == "x\n"
    finally:
        outside.unlink(missing_ok=True)


def test_directory_is_moved_whole(tmp_path: Path):
    src = tmp_path / ".opencode" / "skills" / "gone"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("body\n")

    dest = quarantine(tmp_path, src)

    assert dest is not None and dest.is_dir()
    assert (dest / "SKILL.md").read_text() == "body\n"
    assert not src.exists()
