"""``/link`` skill — code<->doc knowledge-mesh builder (Framework B, slice 4).

The enrichment surface that narrows the database read-only stance:
relations + intent (sidecar metadata) are writable via
``smak enrich-symbol --relation --bidirectional``; indexed source
content is still never edited through the agent.

Pins: body content (bidirectional enrich, doc ``::*`` node UID, sidecar
not source), install presence on both surfaces, generic ``<active>``
command body, re-init safety, and the relaxed-but-still-"read-only"
ROLE.md wording (+ the ``/link`` capability row).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from allmight.capabilities.database.initializer import ProjectInitializer
from allmight.capabilities.database.link_skill_content import (
    build_link_command_body,
    build_link_skill_md,
)
from allmight.cli import main
from allmight.core.domain import ProjectManifest
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


class TestLinkBodyContent:
    def test_skill_teaches_bidirectional_enrich(self) -> None:
        body = build_link_skill_md()
        assert "smak enrich-symbol" in body
        assert "--bidirectional" in body
        assert "--relation" in body

    def test_skill_explains_doc_node_uid(self) -> None:
        # A documentation file is a file-level node — symbol ``*``.
        assert "::*" in build_link_skill_md()

    def test_skill_keeps_source_untouched(self) -> None:
        body = build_link_skill_md().lower()
        assert "sidecar" in body
        assert "never into the code" in body or "not edited" in body \
            or "never edited" in body

    def test_command_body_is_generic(self) -> None:
        body = build_link_command_body()
        assert "personalities/<active>/database/<workspace>/config.yaml" in body

    def test_command_body_carries_routing_preamble(self) -> None:
        from allmight.core.routing import ROUTING_PREAMBLE

        assert build_link_command_body().startswith(ROUTING_PREAMBLE)


class TestLinkInstalled:
    def test_skill_and_command_present(self, initted_project: Path) -> None:
        assert (initted_project / ".opencode" / "skills" / "link" / "SKILL.md").exists()
        assert (initted_project / ".opencode" / "commands" / "link.md").exists()

    def test_skill_is_model_invocable(self, initted_project: Path) -> None:
        content = (initted_project / ".opencode" / "skills" / "link" / "SKILL.md").read_text()
        assert "disable-model-invocation" not in content
        assert "enrich-symbol" in content

    def test_user_edits_survive_reinit(self, initted_project: Path) -> None:
        skill = initted_project / ".opencode" / "skills" / "link" / "SKILL.md"
        skill.write_text(
            "---\nname: link\ndescription: edited\n---\n\n"
            + ALLMIGHT_MARKER_MD
            + "\n\nUSER EDIT — must survive re-init\n"
        )
        edited = skill.read_text()
        CliRunner().invoke(main, ["init", "--yes", str(initted_project)])
        assert skill.read_text() == edited


class TestReadOnlyRelaxed:
    def _role_body(self) -> str:
        return ProjectInitializer()._role_md_body(
            ProjectManifest(name="x", root_path=Path("/tmp/x")),
        )

    def test_role_still_contains_read_only_substring(self) -> None:
        # Tests elsewhere (clone, project_init) assert this substring.
        assert "read-only" in self._role_body().lower()

    def test_role_permits_relation_enrichment(self) -> None:
        body = self._role_body()
        assert "/link" in body
        assert "relations" in body.lower()

    def test_role_still_forbids_source_content_edits(self) -> None:
        assert "NOT edit indexed source" in self._role_body()
