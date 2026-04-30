"""Verify the registry reader/writer handle both Part-C and Part-D row shapes.

Part D introduces a new on-disk layout: a registry row carries a
``name`` + ``capabilities`` list + per-capability ``versions`` map.
Part-C rows (``template`` + ``instance`` + ``version``) must keep
working because pre-Part-D projects exist on disk; the migrator (Commit
8) will rewrite them, but until then ``read_registry`` must accept
both. ``write_registry`` always emits the Part-D shape so a fresh
project never inherits the legacy form.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from allmight.core.personalities import (
    Personality,
    PersonalityTemplate,
    RegistryEntry,
    read_registry,
    write_registry,
)


def _stub_template() -> PersonalityTemplate:
    return PersonalityTemplate(
        name="stub",
        short_name="stub",
        version="0.0.0",
        description="",
        owned_paths=[],
        cli_options=[],
        install=lambda ctx, p: None,  # type: ignore[arg-type]
        status=lambda root, p: None,  # type: ignore[arg-type]
    )


class TestPersonalityCapabilities:
    def test_capability_root_addresses_subdir(self, tmp_path: Path) -> None:
        p = Personality(
            template=_stub_template(),
            project_root=tmp_path,
            name="stdcell_owner",
            capabilities=["database", "memory"],
            role_summary="Stdcell.",
        )
        assert p.root == tmp_path / "personalities" / "stdcell_owner"
        assert p.capability_root("database") == p.root / "database"
        assert p.capability_root("memory") == p.root / "memory"

    def test_capabilities_default_empty(self, tmp_path: Path) -> None:
        """Part-C call sites (no capabilities arg) get an empty list."""
        p = Personality(
            template=_stub_template(),
            project_root=tmp_path,
            name="legacy",
        )
        assert p.capabilities == []
        assert p.role_summary == ""


class TestReader:
    def test_reads_part_c_row(self, tmp_path: Path) -> None:
        (tmp_path / ".allmight").mkdir()
        (tmp_path / ".allmight" / "personalities.yaml").write_text(
            "personalities:\n"
            "- {template: corpus_keeper, instance: knowledge, version: 1.0.0}\n"
        )
        entries = read_registry(tmp_path)
        assert len(entries) == 1
        e = entries[0]
        assert e.template == "corpus_keeper"
        assert e.instance == "knowledge"
        assert e.version == "1.0.0"
        # Part-D fields synthesised from the Part-C row.
        assert e.capabilities == ["corpus_keeper"]
        assert e.versions == {"corpus_keeper": "1.0.0"}

    def test_reads_part_d_row(self, tmp_path: Path) -> None:
        (tmp_path / ".allmight").mkdir()
        (tmp_path / ".allmight" / "personalities.yaml").write_text(
            "personalities:\n"
            "- name: stdcell_owner\n"
            "  capabilities: [database, memory]\n"
            "  versions: {database: 1.0.0, memory: 1.0.0}\n"
            "  role_summary: Standard-cell library characterisation.\n"
        )
        entries = read_registry(tmp_path)
        assert len(entries) == 1
        e = entries[0]
        assert e.instance == "stdcell_owner"  # `name` aliases instance
        assert e.capabilities == ["database", "memory"]
        assert e.versions == {"database": "1.0.0", "memory": "1.0.0"}
        assert e.role_summary == "Standard-cell library characterisation."
        # Backward-compat scalars derive from the first capability.
        assert e.template == "database"
        assert e.version == "1.0.0"

    def test_reads_mixed_file(self, tmp_path: Path) -> None:
        (tmp_path / ".allmight").mkdir()
        (tmp_path / ".allmight" / "personalities.yaml").write_text(
            "personalities:\n"
            "- {template: corpus_keeper, instance: legacy, version: 0.9.0}\n"
            "- name: new_personality\n"
            "  capabilities: [memory]\n"
            "  versions: {memory: 1.1.0}\n"
        )
        entries = read_registry(tmp_path)
        assert [e.instance for e in entries] == ["legacy", "new_personality"]


class TestWriter:
    def test_writes_part_d_shape_only(self, tmp_path: Path) -> None:
        write_registry(tmp_path, [
            RegistryEntry(
                instance="stdcell_owner",
                capabilities=["database", "memory"],
                versions={"database": "1.0.0", "memory": "1.0.0"},
                role_summary="Standard-cell library characterisation.",
            ),
        ])
        rows = yaml.safe_load(
            (tmp_path / ".allmight" / "personalities.yaml").read_text()
        )["personalities"]
        assert rows == [{
            "name": "stdcell_owner",
            "capabilities": ["database", "memory"],
            "versions": {"database": "1.0.0", "memory": "1.0.0"},
            "role_summary": "Standard-cell library characterisation.",
        }]

    def test_part_c_constructed_entry_round_trips_as_part_d(
        self, tmp_path: Path,
    ) -> None:
        """Old call sites construct entries with the Part-C signature;
        the writer up-converts them to the Part-D shape transparently."""
        write_registry(tmp_path, [
            RegistryEntry(template="corpus_keeper", instance="knowledge", version="1.0.0"),
        ])
        rows = yaml.safe_load(
            (tmp_path / ".allmight" / "personalities.yaml").read_text()
        )["personalities"]
        assert rows == [{
            "name": "knowledge",
            "capabilities": ["corpus_keeper"],
            "versions": {"corpus_keeper": "1.0.0"},
        }]
