"""Personality suggestion catalog (Track A).

The catalog at
``src/allmight/capabilities/database/personality_suggestions.py`` is
seeded into ``.allmight/suggestions/personalities/*.yaml`` by
``allmight init``. ``/onboard`` reads the directory at runtime and
proposes from it.

These tests pin the catalog shape (every entry has the four required
fields, ``general`` is always present as the keyword fallback,
referenced capabilities exist) and the seeding behaviour
(marker'd files, idempotent, user-edited files preserved).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from allmight.capabilities.database.personality_suggestions import (
    PERSONALITY_SUGGESTIONS,
    seed_suggestions,
    suggestion_dir,
)
from allmight.core.markers import ALLMIGHT_MARKER_YAML


class TestCatalogShape:
    def test_general_is_first_and_is_fallback(self) -> None:
        """`general` must be in the catalog and must be the empty-keyword
        fallback so /onboard always has something to offer."""
        first = PERSONALITY_SUGGESTIONS[0]
        assert first.name == "general"
        assert first.keywords == ()  # empty = fallback

    def test_every_entry_has_required_fields(self) -> None:
        for s in PERSONALITY_SUGGESTIONS:
            assert s.name and isinstance(s.name, str)
            assert s.capabilities and isinstance(s.capabilities, tuple)
            assert s.scope and isinstance(s.scope, str)
            assert isinstance(s.keywords, tuple)

    def test_capabilities_reference_real_templates(self) -> None:
        """Every capability listed must correspond to a real installed
        template — no typos, no orphaned references."""
        from allmight.core.personalities import discover

        valid = {t.name for t in discover()}
        for s in PERSONALITY_SUGGESTIONS:
            for cap in s.capabilities:
                assert cap in valid, (
                    f"suggestion {s.name!r} references unknown capability {cap!r}; "
                    f"valid: {sorted(valid)}"
                )

    def test_names_are_unique(self) -> None:
        names = [s.name for s in PERSONALITY_SUGGESTIONS]
        assert len(names) == len(set(names))


class TestSeedSuggestions:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        (tmp_path / ".allmight").mkdir()
        return tmp_path

    def test_writes_one_yaml_per_suggestion(self, project: Path) -> None:
        seed_suggestions(project)
        files = sorted(suggestion_dir(project).glob("*.yaml"))
        assert len(files) == len(PERSONALITY_SUGGESTIONS)

    def test_each_file_carries_marker(self, project: Path) -> None:
        seed_suggestions(project)
        for path in suggestion_dir(project).glob("*.yaml"):
            assert path.read_text().startswith(ALLMIGHT_MARKER_YAML), (
                f"{path.name} missing All-Might marker"
            )

    def test_general_yaml_round_trips(self, project: Path) -> None:
        seed_suggestions(project)
        general = suggestion_dir(project) / "general.yaml"
        body = yaml.safe_load(general.read_text())
        assert body["name"] == "general"
        assert "database" in body["capabilities"]
        assert "memory" in body["capabilities"]
        assert body["keywords"] == []

    def test_idempotent_on_re_seed(self, project: Path) -> None:
        seed_suggestions(project)
        first = (suggestion_dir(project) / "general.yaml").read_text()
        seed_suggestions(project)
        second = (suggestion_dir(project) / "general.yaml").read_text()
        assert first == second

    def test_user_authored_yaml_preserved(self, project: Path) -> None:
        """A user-added (no-marker) suggestion file must survive seeding."""
        sd = suggestion_dir(project)
        sd.mkdir(parents=True, exist_ok=True)
        custom = sd / "my-custom.yaml"
        custom.write_text("name: my-custom\n")  # no marker

        seed_suggestions(project)
        # Framework files are written, plus the user's file is left alone.
        assert custom.exists()
        assert "my-custom" in custom.read_text()
