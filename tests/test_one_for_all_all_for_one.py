"""``/one-for-all`` and ``/all-for-one`` skills + ``allmight import`` CLI.

Per-personality portability. The skill pair replaces the legacy
``/export`` / ``allmight import`` split:

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

* **allmight import <bundle> [--as <name>]** is mechanical and CLI-only.
  Reads ``manifest.yaml``, runs each capability's install (so the
  directory structure conforms to the current ``allmight`` version),
  and copies the bundle's data into place. Refuses on collision and
  redirects the user to ``/all-for-one``. No ``--force`` flag.
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
# allmight import CLI (single-bundle thin path)
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

    def test_duplicate_name_redirects_to_all_for_one(
        self, initted_project: Path, sample_bundle: Path,
    ) -> None:
        """Collision behaviour replaces the old ``--force`` flag: import
        always refuses on collision and the error must point the user
        at ``/all-for-one`` (the surface that can dialog through merges).
        """
        first = _invoke_in(initted_project, ["import", str(sample_bundle)])
        assert first.exit_code == 0
        second = _invoke_in(initted_project, ["import", str(sample_bundle)])
        assert second.exit_code != 0
        assert "/all-for-one" in second.output
        assert "already exists" in second.output

    def test_no_force_flag(self) -> None:
        """The ``--force`` flag was deliberately removed — ensure it
        no longer exists on the import command."""
        runner = CliRunner()
        result = runner.invoke(main, ["import", "--help"])
        assert result.exit_code == 0
        assert "--force" not in result.output


def _bundle_with_subscriptions(
    base: Path, subs: list[dict],
) -> Path:
    """Build a minimal valid bundle whose manifest carries
    ``database_subscriptions``."""
    bundle = base / "stdcell_owner-export"
    bundle.mkdir()
    manifest = {
        "allmight_version": "0.1.0",
        "schema_version": 2,
        "personality_name": "stdcell_owner",
        "capabilities": {
            "database": {"capability_version": "1.0.0"},
            "memory": {"capability_version": "1.0.0"},
        },
        "database_subscriptions": subs,
    }
    (bundle / "manifest.yaml").write_text(yaml.safe_dump(manifest))
    (bundle / "ROLE.md").write_text(
        "<!-- all-might generated -->\n# stdcell_owner\nRole.\n",
    )
    (bundle / "database").mkdir()
    (bundle / "memory").mkdir()
    (bundle / "memory" / "understanding").mkdir()
    (bundle / "memory" / "understanding" / "stdcell.md").write_text(
        "<!-- all-might generated -->\n# stdcell\nNotes.\n",
    )
    return bundle


class TestImportDatabaseSubscriptions:
    """Manifest schema v2: database_subscriptions field."""

    def test_skill_documents_subscriptions_field(self) -> None:
        from allmight.capabilities.database.one_for_all_skill_content import (
            ONE_FOR_ALL_SKILL_BODY,
        )
        # Manifest example must show the new field, and the procedure
        # must include the populate step (5b).
        assert "database_subscriptions" in ONE_FOR_ALL_SKILL_BODY
        assert "5b" in ONE_FOR_ALL_SKILL_BODY or "Populate" in ONE_FOR_ALL_SKILL_BODY

    def test_import_warns_on_missing_required_subscription(
        self, initted_project: Path, tmp_path: Path,
    ) -> None:
        bundle = _bundle_with_subscriptions(
            tmp_path,
            [{
                "index": "stdcell",
                "nfs_path": "/nonexistent/nfs/smak/stdcell",
                "last_validated_against": "2026-04-15",
                "required": True,
            }],
        )
        result = _invoke_in(initted_project, ["import", str(bundle)])
        # Import must succeed even when the subscription path is missing.
        assert result.exit_code == 0, result.output
        # Both stdout (success line) and stderr (warning) are merged into
        # result.output by Click's CliRunner.
        assert "warning" in result.output.lower()
        assert "stdcell" in result.output
        assert "/nonexistent/nfs/smak/stdcell" in result.output

    def test_import_subscription_summary_in_output(
        self, initted_project: Path, tmp_path: Path,
    ) -> None:
        bundle = _bundle_with_subscriptions(
            tmp_path,
            [
                {"index": "a", "nfs_path": str(tmp_path), "required": True},
                {"index": "b", "nfs_path": "/nope/x", "required": True},
            ],
        )
        result = _invoke_in(initted_project, ["import", str(bundle)])
        assert result.exit_code == 0, result.output
        assert "Database subscriptions: 2" in result.output
        assert "1 warning" in result.output

    def test_import_legacy_bundle_without_subscriptions_still_works(
        self, initted_project: Path, sample_bundle: Path,
    ) -> None:
        # The sample_bundle fixture (defined above) emits a v1-shaped
        # manifest with no database_subscriptions. Old bundles must
        # import without warnings.
        result = _invoke_in(initted_project, ["import", str(sample_bundle)])
        assert result.exit_code == 0, result.output
        # No subscription summary line should appear.
        assert "Database subscriptions:" not in result.output


def _bundle_with_lineage(
    base: Path,
    *,
    bundle_id: str,
    bundle_version: str = "0.1.0",
    derived_from: list[dict] | None = None,
) -> Path:
    """Build a bundle whose manifest carries lineage fields.

    ``derived_from`` is the schema_version 3 shape: a list of
    ``{kind, ...}`` dicts. Each entry is either ``{kind: bundle,
    bundle_id, bundle_version}`` or ``{kind: personality, name}``.
    """
    bundle = base / "stdcell_owner-export"
    bundle.mkdir()
    manifest = {
        "allmight_version": "0.1.0",
        "schema_version": 3,
        "personality_name": "stdcell_owner",
        "bundle_id": bundle_id,
        "bundle_version": bundle_version,
        "derived_from": list(derived_from or []),
        "capabilities": {
            "database": {"capability_version": "1.0.0"},
            "memory": {"capability_version": "1.0.0"},
        },
    }
    (bundle / "manifest.yaml").write_text(yaml.safe_dump(manifest))
    (bundle / "ROLE.md").write_text(
        "<!-- all-might generated -->\n# stdcell_owner\nRole.\n",
    )
    (bundle / "database").mkdir()
    (bundle / "memory").mkdir()
    return bundle


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

    def test_import_records_lineage_in_registry(
        self, initted_project: Path, tmp_path: Path,
    ) -> None:
        bundle = _bundle_with_lineage(
            tmp_path,
            bundle_id="7c4f3a2e-1111-2222-3333-444455556666",
            bundle_version="1.2.3",
        )
        result = _invoke_in(initted_project, ["import", str(bundle)])
        assert result.exit_code == 0, result.output

        registry = yaml.safe_load(
            (initted_project / ".allmight" / "personalities.yaml").read_text()
        )
        rows = [r for r in registry["personalities"]
                if (r.get("name") or r.get("instance")) == "stdcell_owner"]
        assert rows, "personality row missing from registry"
        row = rows[0]
        derived_from = row["derived_from"]
        assert isinstance(derived_from, list) and len(derived_from) == 1
        src = derived_from[0]
        assert src["kind"] == "bundle"
        assert src["bundle_id"] == "7c4f3a2e-1111-2222-3333-444455556666"
        assert src["bundle_version"] == "1.2.3"
        assert row["derived_at"], "derived_at should be populated"

    def test_legacy_bundle_does_not_pollute_registry_with_empty_keys(
        self, initted_project: Path, sample_bundle: Path,
    ) -> None:
        # sample_bundle has no lineage fields. The registry row must
        # NOT carry derived_from / derived_at as empty values — they
        # should be omitted entirely so locally-created (or
        # legacy-imported) personalities have a clean row.
        _invoke_in(initted_project, ["import", str(sample_bundle)])
        registry = yaml.safe_load(
            (initted_project / ".allmight" / "personalities.yaml").read_text()
        )
        rows = [r for r in registry["personalities"]
                if (r.get("name") or r.get("instance")) == "stdcell_owner"]
        assert rows
        row = rows[0]
        for key in ("derived_from", "derived_at"):
            assert key not in row, (
                f"legacy import should not emit {key} in registry"
            )

    def test_registry_round_trip_preserves_lineage(
        self, initted_project: Path, tmp_path: Path,
    ) -> None:
        # After an import, read the registry back and verify the
        # RegistryEntry dataclass exposes the lineage fields.
        from allmight.core.personalities import read_registry
        bundle = _bundle_with_lineage(
            tmp_path,
            bundle_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            bundle_version="2.0.0",
        )
        _invoke_in(initted_project, ["import", str(bundle)])

        entries = read_registry(initted_project)
        match = next(
            (e for e in entries if e.instance == "stdcell_owner"), None,
        )
        assert match is not None
        assert len(match.derived_from) == 1
        src = match.derived_from[0]
        assert src.kind == "bundle"
        assert src.bundle_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert src.bundle_version == "2.0.0"
        assert match.derived_at
