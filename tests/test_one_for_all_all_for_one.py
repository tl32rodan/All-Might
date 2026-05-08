"""``/one-for-all`` and ``/all-for-one`` skills.

Per-personality portability — both directions agent-driven:

* **/one-for-all** is agent-driven (PII review, per-capability rules).
  The bundled skill instructs the agent how to walk a chosen
  personality's data, apply per-capability export rules, obtain user
  consent for sensitive content, and write a directory bundle. 1
  personality → 1 bundle.

* **/all-for-one** is agent-driven (per-file dialog). The bundled
  skill instructs the agent how to absorb N source personalities
  (bundles or in-project) into 1 target (new or existing). It owns
  every merge decision: workspace clashes, understanding overwrites,
  ROLE.md prose reconciliation. N → 1.

The ``allmight import`` CLI was removed (Track C); cross-project
transfer goes through the agent-driven skills above. ``share pull``
still installs single bundles via an internal helper for git
transport.
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
    """A minimal valid bundle for ``stdcell_owner``."""
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
# /one-for-all skill content
# -----------------------------------------------------------------------


class TestOneForAllSkillBody:
    def test_skill_body_imports(self) -> None:
        from allmight.capabilities.database.one_for_all_skill_content import (
            ONE_FOR_ALL_COMMAND_BODY,
            ONE_FOR_ALL_SKILL_BODY,
        )
        assert ONE_FOR_ALL_SKILL_BODY
        assert ONE_FOR_ALL_COMMAND_BODY

    def test_skill_body_describes_per_capability_rules(self) -> None:
        from allmight.capabilities.database.one_for_all_skill_content import (
            ONE_FOR_ALL_SKILL_BODY,
        )
        body = ONE_FOR_ALL_SKILL_BODY
        # database/ rules
        assert "database" in body
        assert "config.yaml" in body
        assert "store" in body  # store/ explicitly NOT exported
        # memory/ rules
        assert "understanding" in body
        assert "journal" in body
        assert "MEMORY.md" in body

    def test_skill_body_describes_pii_review(self) -> None:
        from allmight.capabilities.database.one_for_all_skill_content import (
            ONE_FOR_ALL_SKILL_BODY,
        )
        body_lower = ONE_FOR_ALL_SKILL_BODY.lower()
        assert "pii" in body_lower or "sensitive" in body_lower
        assert "consent" in body_lower or "ask" in body_lower

    def test_skill_body_describes_manifest(self) -> None:
        from allmight.capabilities.database.one_for_all_skill_content import (
            ONE_FOR_ALL_SKILL_BODY,
        )
        body = ONE_FOR_ALL_SKILL_BODY
        assert "manifest.yaml" in body
        assert "allmight_version" in body
        assert "personality_name" in body
        assert "capabilities" in body

    def test_skill_body_cardinality_callout(self) -> None:
        """The skill body must explicitly state the 1→1 cardinality and
        point to /all-for-one for the inverse, so an agent reading it
        cold knows when to switch surfaces."""
        from allmight.capabilities.database.one_for_all_skill_content import (
            ONE_FOR_ALL_SKILL_BODY,
        )
        body = ONE_FOR_ALL_SKILL_BODY
        assert "1 personality" in body or "one personality" in body.lower()
        assert "/all-for-one" in body


class TestOneForAllSkillIsInstalled:
    def test_skill_present_after_init(self, initted_project: Path) -> None:
        skill = initted_project / ".opencode" / "skills" / "one-for-all" / "SKILL.md"
        assert skill.exists()

    def test_command_present_after_init(self, initted_project: Path) -> None:
        cmd = initted_project / ".opencode" / "commands" / "one-for-all.md"
        assert cmd.exists()

    def test_legacy_export_files_absent(self, initted_project: Path) -> None:
        """The renamed surface must fully replace the old one — no
        ``export/SKILL.md`` or ``export.md`` lingering after init."""
        assert not (initted_project / ".opencode" / "skills" / "export").exists()
        assert not (initted_project / ".opencode" / "commands" / "export.md").exists()


# -----------------------------------------------------------------------
# /all-for-one skill content
# -----------------------------------------------------------------------


class TestAllForOneSkillBody:
    def test_skill_body_imports(self) -> None:
        from allmight.capabilities.database.all_for_one_skill_content import (
            ALL_FOR_ONE_COMMAND_BODY,
            ALL_FOR_ONE_SKILL_BODY,
        )
        assert ALL_FOR_ONE_SKILL_BODY
        assert ALL_FOR_ONE_COMMAND_BODY

    def test_skill_body_describes_source_kinds(self) -> None:
        """Sources can be bundles or in-project personalities; the
        skill body must teach the agent both."""
        from allmight.capabilities.database.all_for_one_skill_content import (
            ALL_FOR_ONE_SKILL_BODY,
        )
        body = ALL_FOR_ONE_SKILL_BODY
        assert "bundle" in body.lower()
        assert "in-project" in body.lower() or "personality name" in body.lower()

    def test_skill_body_describes_target_kinds(self) -> None:
        """Targets can be a new name or an existing personality."""
        from allmight.capabilities.database.all_for_one_skill_content import (
            ALL_FOR_ONE_SKILL_BODY,
        )
        body = ALL_FOR_ONE_SKILL_BODY
        assert "new" in body.lower()
        assert "existing" in body.lower()

    def test_skill_body_describes_per_capability_merge(self) -> None:
        from allmight.capabilities.database.all_for_one_skill_content import (
            ALL_FOR_ONE_SKILL_BODY,
        )
        body = ALL_FOR_ONE_SKILL_BODY
        # database workspace merge
        assert "workspace" in body.lower()
        assert "config.yaml" in body
        # store/ never copied
        assert "store" in body
        # memory: understanding (per-file) and journal (append/dedupe)
        assert "understanding" in body
        assert "journal" in body
        assert "dedupe" in body.lower() or "deduplicate" in body.lower()
        # ROLE.md prose merge
        assert "ROLE.md" in body
        assert "confirm" in body.lower()

    def test_skill_body_describes_registry_update(self) -> None:
        """The skill must teach the agent to write a ``derived_from``
        list with one entry per source."""
        from allmight.capabilities.database.all_for_one_skill_content import (
            ALL_FOR_ONE_SKILL_BODY,
        )
        body = ALL_FOR_ONE_SKILL_BODY
        assert "derived_from" in body
        assert "kind: bundle" in body
        assert "kind: personality" in body

    def test_skill_body_describes_source_disposition(self) -> None:
        """In-project sources default to ``keep`` (git-merge --squash
        style), with a yes/no prompt for removal."""
        from allmight.capabilities.database.all_for_one_skill_content import (
            ALL_FOR_ONE_SKILL_BODY,
        )
        body = ALL_FOR_ONE_SKILL_BODY
        assert "keep" in body.lower()
        assert "remove" in body.lower()

    def test_skill_body_cardinality_callout(self) -> None:
        from allmight.capabilities.database.all_for_one_skill_content import (
            ALL_FOR_ONE_SKILL_BODY,
        )
        body = ALL_FOR_ONE_SKILL_BODY
        assert "N" in body
        assert "/one-for-all" in body


class TestAllForOneSkillIsInstalled:
    def test_skill_present_after_init(self, initted_project: Path) -> None:
        skill = initted_project / ".opencode" / "skills" / "all-for-one" / "SKILL.md"
        assert skill.exists()

    def test_command_present_after_init(self, initted_project: Path) -> None:
        cmd = initted_project / ".opencode" / "commands" / "all-for-one.md"
        assert cmd.exists()



# -----------------------------------------------------------------------
# Bundle lineage in skill body
# -----------------------------------------------------------------------


class TestBundleLineage:
    """Manifest lineage: bundle_id, bundle_version, derived_from."""

    def test_skill_documents_lineage_fields(self) -> None:
        from allmight.capabilities.database.one_for_all_skill_content import (
            ONE_FOR_ALL_SKILL_BODY,
        )
        for token in ("bundle_id", "bundle_version", "derived_from"):
            assert token in ONE_FOR_ALL_SKILL_BODY, f"missing {token}"
        # Schema v3 shape must be documented (per-source kind tags).
        assert "kind: bundle" in ONE_FOR_ALL_SKILL_BODY
        assert "kind: personality" in ONE_FOR_ALL_SKILL_BODY
