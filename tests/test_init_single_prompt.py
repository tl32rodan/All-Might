"""Init UX simplification — single ``Personality name?`` prompt.

Part-D commit 7 contract: ``allmight init`` creates ONE personality
with ALL discovered capabilities by default. The previous flow
(prompt per template + folder list) has been replaced with a single
question:

  Personality name? [<project-root-dir-name>]

Under ``--yes`` the prompt is skipped and the default
(``slugify_instance_name(project_root.name)``) is used. Folder
classification is deferred entirely to the agent-side
``/onboard`` skill (commit 8).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from allmight.cli import main


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    project = tmp_path / "my-chip"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("def f(): pass\n")
    (project / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    return project


class TestInitYesSinglePersonality:
    def test_creates_one_personality(self, project_dir: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--yes", str(project_dir)])
        assert result.exit_code == 0, result.output

        personality_dirs = sorted(p for p in (project_dir / "personalities").iterdir() if p.is_dir())
        assert len(personality_dirs) == 1, (
            f"--yes init must produce exactly one personality, got "
            f"{[p.name for p in personality_dirs]}"
        )

    def test_personality_named_after_project_root(self, project_dir: Path) -> None:
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(project_dir)])

        personality_dirs = list((project_dir / "personalities").iterdir())
        assert personality_dirs[0].name == "my-chip"

    def test_personality_has_all_capabilities(self, project_dir: Path) -> None:
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(project_dir)])

        p = project_dir / "personalities" / "my-chip"
        assert (p / "database").is_dir()
        assert (p / "memory").is_dir()

    def test_registry_has_one_part_d_row(self, project_dir: Path) -> None:
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(project_dir)])

        registry = yaml.safe_load(
            (project_dir / ".allmight" / "personalities.yaml").read_text()
        )
        rows = registry["personalities"]
        assert len(rows) == 1
        row = rows[0]
        assert row.get("name") == "my-chip"
        assert sorted(row.get("capabilities", [])) == ["database", "memory"]


class TestInitOnboardYaml:
    def test_writes_single_personality_block(self, project_dir: Path) -> None:
        """``onboard.yaml`` records the single personality + its
        capabilities; ``/onboard`` will read this to drive the
        qualitative half of setup."""
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(project_dir)])

        path = project_dir / ".allmight" / "onboard.yaml"
        assert path.exists()
        data = yaml.safe_load(path.read_text())
        assert data["onboarded"] is False
        assert isinstance(data["personalities"], list)
        assert len(data["personalities"]) == 1
        entry = data["personalities"][0]
        assert entry["name"] == "my-chip"
        assert sorted(entry["capabilities"]) == ["database", "memory"]

    def test_no_folders_prompt_under_yes(self, project_dir: Path) -> None:
        """``--yes`` must not gather folders; ``/onboard`` does that."""
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(project_dir)])

        path = project_dir / ".allmight" / "onboard.yaml"
        data = yaml.safe_load(path.read_text())
        assert data.get("folders", []) == []


class TestInitOutputMessage:
    def test_message_lists_one_personality(self, project_dir: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--yes", str(project_dir)])
        assert "my-chip" in result.output
