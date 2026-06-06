"""``/docs`` skill — offline documentation lookup (Framework A, skill-only).

``/docs`` is the air-gapped stand-in for ``web_search`` / ``context7``.
It searches a curated documentation corpus indexed as a ``database``
workspace at ``personalities/<active>/database/docs/``.

Design invariants this file pins:

* **Discovery-friendly description.** The point of Framework A is to
  measure how often the model reaches for ``/docs`` on its own, so the
  skill must NOT be ``disable-model-invocation``.
* **Generic body.** The command body uses the ``<active>`` placeholder,
  never a literal personality name (the Part-D rule the whole
  command surface obeys).
* **No-hallucination contract.** Both the empty-result and
  missing-config paths must tell the model to ask the user, not guess.
* **Lightweight usage marker.** The body appends to
  ``.allmight/usage/docs.log`` so the 2-week spontaneous-invocation
  measurement has a denominator.
* **Re-init safety.** Like every other database skill, ``/docs`` is
  written on fresh init only; a user-tweaked body that keeps our
  marker survives a re-init.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from allmight.capabilities.database.docs_skill_content import (
    DOCS_SKILL_DESCRIPTION,
    build_docs_command_body,
    build_docs_skill_md,
)
from allmight.capabilities.database.personality_suggestions import (
    PERSONALITY_SUGGESTIONS,
    seed_suggestions,
    suggestion_dir,
)
from allmight.cli import main
from allmight.core.markers import ALLMIGHT_MARKER_MD


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


# -----------------------------------------------------------------------
# Body content invariants
# -----------------------------------------------------------------------


class TestDocsBodyContent:
    def test_skill_body_names_the_offline_substitution(self) -> None:
        body = build_docs_skill_md()
        assert "web_search" in body
        assert "context7" in body
        assert "offline" in body.lower()

    def test_skill_body_uses_smak_search_all(self) -> None:
        assert "smak search-all" in build_docs_skill_md()

    def test_no_hallucination_contract(self) -> None:
        """Both the empty-result and missing-config paths must steer the
        model to the user rather than a guess."""
        body = build_docs_skill_md().lower()
        assert "hallucinat" in body
        assert "ask the user" in body or "tell the user" in body

    def test_usage_marker_is_recorded(self) -> None:
        """The lightweight invocation marker the 2-week measurement needs."""
        assert ".allmight/usage/docs.log" in build_docs_skill_md()
        assert ".allmight/usage/docs.log" in build_docs_command_body()

    def test_command_body_is_generic(self) -> None:
        """Uses the ``<active>`` placeholder, no literal personality name."""
        body = build_docs_command_body()
        assert "personalities/<active>/database/docs/config.yaml" in body

    def test_command_body_carries_routing_preamble(self) -> None:
        from allmight.core.routing import ROUTING_PREAMBLE

        assert build_docs_command_body().startswith(ROUTING_PREAMBLE)


# -----------------------------------------------------------------------
# Install presence
# -----------------------------------------------------------------------


class TestDocsSkillIsInstalled:
    def test_skill_present_after_init(self, initted_project: Path) -> None:
        skill = initted_project / ".opencode" / "skills" / "docs" / "SKILL.md"
        assert skill.exists()

    def test_command_present_after_init(self, initted_project: Path) -> None:
        cmd = initted_project / ".opencode" / "commands" / "docs.md"
        assert cmd.exists()

    def test_skill_is_model_invocable(self, initted_project: Path) -> None:
        """Framework A measures spontaneous invocation — the skill must be
        discoverable by the model, i.e. NOT disable-model-invocation."""
        skill = initted_project / ".opencode" / "skills" / "docs" / "SKILL.md"
        content = skill.read_text()
        assert "disable-model-invocation" not in content
        assert DOCS_SKILL_DESCRIPTION in content

    def test_installed_skill_carries_expected_signals(
        self, initted_project: Path,
    ) -> None:
        """Catches the regression where the constant exists but isn't wired
        into ``initialize_globals``."""
        skill = initted_project / ".opencode" / "skills" / "docs" / "SKILL.md"
        content = skill.read_text()
        assert "smak search-all" in content
        assert ".allmight/usage/docs.log" in content


# -----------------------------------------------------------------------
# Re-init safety (matches the established database-skill pattern)
# -----------------------------------------------------------------------


class TestDocsSkillReinitSafety:
    def test_user_edits_survive_reinit(self, initted_project: Path) -> None:
        skill = initted_project / ".opencode" / "skills" / "docs" / "SKILL.md"
        # User tweak — keeps the marker, rewrites the body.
        skill.write_text(
            "---\nname: docs\ndescription: edited\n---\n\n"
            + ALLMIGHT_MARKER_MD
            + "\n\nUSER EDIT — must survive re-init\n"
        )
        edited = skill.read_text()

        # Re-init (no --force) → staging path → skill write skipped.
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--yes", str(initted_project)])
        assert result.exit_code == 0, result.output

        assert skill.read_text() == edited


# -----------------------------------------------------------------------
# librarian suggestion
# -----------------------------------------------------------------------


class TestLibrarianSuggestion:
    def test_librarian_in_catalog(self) -> None:
        names = {s.name for s in PERSONALITY_SUGGESTIONS}
        assert "librarian" in names

    def test_librarian_seeded(self, tmp_path: Path) -> None:
        (tmp_path / ".allmight").mkdir()
        seed_suggestions(tmp_path)
        path = suggestion_dir(tmp_path) / "librarian.yaml"
        assert path.exists()
        body = yaml.safe_load(path.read_text())
        assert body["name"] == "librarian"
        assert "database" in body["capabilities"]
        assert "context7" in body["keywords"]
