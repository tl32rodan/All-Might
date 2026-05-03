"""``/export`` skill + ``allmight import`` CLI (Part-D commit 10).

Per-personality portability:

* **Export** is agent-driven (PII review, per-capability rules).
  The bundled ``/export`` skill instructs the agent how to walk a
  chosen personality's data, apply per-capability export rules,
  obtain user consent for sensitive content, and write a bundle.
* **Import** is mechanical-via-CLI: ``allmight import <bundle>
  [--as <name>]`` reads ``manifest.yaml``, runs each capability's
  install (so the directory structure conforms to the current
  ``allmight`` version), and copies the bundle's data into place.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from allmight.cli import main


def _invoke_in(root: Path, args: list[str]):
    runner = CliRunner()
    cwd = os.getcwd()
    try:
        os.chdir(root)
        return runner.invoke(main, args, catch_exceptions=False)
    finally:
        os.chdir(cwd)


@pytest.fixture
def initted_project(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("def f(): pass\n")
    (project / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--yes", str(project)])
    assert result.exit_code == 0, result.output
    return project


@pytest.fixture
def sample_bundle(tmp_path: Path) -> Path:
    """A minimal valid export bundle for ``stdcell_owner``."""
    bundle = tmp_path / "stdcell_owner-export"
    bundle.mkdir()
    (bundle / "manifest.yaml").write_text(
        "allmight_version: '0.1.0'\n"
        "schema_version: 1\n"
        "personality_name: stdcell_owner\n"
        "capabilities:\n"
        "  database:\n"
        "    capability_version: '1.0.0'\n"
        "  memory:\n"
        "    capability_version: '1.0.0'\n"
    )
    (bundle / "ROLE.md").write_text(
        "<!-- all-might generated -->\n# stdcell_owner\nRole body.\n"
    )
    (bundle / "database").mkdir()
    (bundle / "memory").mkdir()
    (bundle / "memory" / "understanding").mkdir()
    (bundle / "memory" / "understanding" / "stdcell.md").write_text(
        "<!-- all-might generated -->\n# stdcell knowledge\nNotes here.\n"
    )
    return bundle


# -----------------------------------------------------------------------
# /export skill content
# -----------------------------------------------------------------------


class TestExportSkillBody:
    def test_skill_body_imports(self) -> None:
        from allmight.capabilities.database.export_skill_content import (
            EXPORT_COMMAND_BODY,
            EXPORT_SKILL_BODY,
        )
        assert EXPORT_SKILL_BODY
        assert EXPORT_COMMAND_BODY

    def test_skill_body_describes_per_capability_rules(self) -> None:
        from allmight.capabilities.database.export_skill_content import EXPORT_SKILL_BODY
        body = EXPORT_SKILL_BODY
        # database/ rules
        assert "database" in body
        assert "config.yaml" in body
        assert "store" in body  # store/ explicitly NOT exported
        # memory/ rules
        assert "understanding" in body
        assert "journal" in body
        assert "MEMORY.md" in body

    def test_skill_body_describes_pii_review(self) -> None:
        from allmight.capabilities.database.export_skill_content import EXPORT_SKILL_BODY
        body_lower = EXPORT_SKILL_BODY.lower()
        assert "pii" in body_lower or "sensitive" in body_lower
        assert "consent" in body_lower or "ask" in body_lower

    def test_skill_body_describes_manifest(self) -> None:
        from allmight.capabilities.database.export_skill_content import EXPORT_SKILL_BODY
        body = EXPORT_SKILL_BODY
        assert "manifest.yaml" in body
        assert "allmight_version" in body
        assert "personality_name" in body
        assert "capabilities" in body


class TestExportSkillIsInstalled:
    def test_export_skill_present_after_init(self, initted_project: Path) -> None:
        skill = initted_project / ".opencode" / "skills" / "export" / "SKILL.md"
        assert skill.exists()

    def test_export_command_present_after_init(self, initted_project: Path) -> None:
        cmd = initted_project / ".opencode" / "commands" / "export.md"
        assert cmd.exists()


# -----------------------------------------------------------------------
# allmight import CLI
# -----------------------------------------------------------------------


class TestImportCli:
    def test_creates_personality_dir(
        self, initted_project: Path, sample_bundle: Path,
    ) -> None:
        result = _invoke_in(initted_project, ["import", str(sample_bundle)])
        assert result.exit_code == 0, result.output
        p = initted_project / "personalities" / "stdcell_owner"
        assert p.is_dir()
        assert (p / "ROLE.md").is_file()
        assert (p / "database").is_dir()
        assert (p / "memory").is_dir()
        # Imported memory/understanding content lands under the new
        # personality.
        assert (p / "memory" / "understanding" / "stdcell.md").is_file()

    def test_appends_to_registry(
        self, initted_project: Path, sample_bundle: Path,
    ) -> None:
        _invoke_in(initted_project, ["import", str(sample_bundle)])
        registry = yaml.safe_load(
            (initted_project / ".allmight" / "personalities.yaml").read_text()
        )
        names = [r.get("name") or r.get("instance") for r in registry["personalities"]]
        assert "stdcell_owner" in names
        rows = [r for r in registry["personalities"] if (r.get("name") or r.get("instance")) == "stdcell_owner"]
        assert sorted(rows[0].get("capabilities", [])) == ["database", "memory"]

    def test_as_renames_personality(
        self, initted_project: Path, sample_bundle: Path,
    ) -> None:
        result = _invoke_in(
            initted_project,
            ["import", str(sample_bundle), "--as", "stdcell_v2"],
        )
        assert result.exit_code == 0, result.output
        assert (initted_project / "personalities" / "stdcell_v2").is_dir()
        assert not (initted_project / "personalities" / "stdcell_owner").exists()

    def test_missing_manifest_errors(
        self, initted_project: Path, tmp_path: Path,
    ) -> None:
        bad = tmp_path / "nope"
        bad.mkdir()
        result = _invoke_in(initted_project, ["import", str(bad)])
        assert result.exit_code != 0

    def test_outside_allmight_project_errors(
        self, tmp_path: Path, sample_bundle: Path,
    ) -> None:
        loose = tmp_path / "loose"
        loose.mkdir()
        result = _invoke_in(loose, ["import", str(sample_bundle)])
        assert result.exit_code != 0

    def test_duplicate_name_without_force_errors(
        self, initted_project: Path, sample_bundle: Path,
    ) -> None:
        first = _invoke_in(initted_project, ["import", str(sample_bundle)])
        assert first.exit_code == 0
        second = _invoke_in(initted_project, ["import", str(sample_bundle)])
        assert second.exit_code != 0
