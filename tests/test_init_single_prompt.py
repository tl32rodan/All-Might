"""Init is scaffold-only: no personality is created at install time.

Track A contract: ``allmight init`` writes the project-wide
``.opencode/`` globals + ``MEMORY.md`` + ``AGENTS.md``, an empty
registry, and seeds ``.allmight/suggestions/personalities/`` with the
canonical suggestion catalog. Personalities are decided by the
agent-side ``/onboard`` skill, which proposes from the catalog and
shells out to ``allmight add``.

(File still named ``test_init_single_prompt.py`` for git history;
the "single prompt" framing predates Track A.)
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


class TestInitScaffoldOnly:
    def test_no_personality_created(self, project_dir: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--yes", str(project_dir)])
        assert result.exit_code == 0, result.output

        personalities_dir = project_dir / "personalities"
        # The directory may be created (write_init_scaffold makes a
        # stable parent for compose) but must contain no personalities.
        if personalities_dir.exists():
            children = [p for p in personalities_dir.iterdir() if p.is_dir()]
            assert children == [], (
                f"init should not create personalities, got {[p.name for p in children]}"
            )

    def test_registry_is_empty(self, project_dir: Path) -> None:
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(project_dir)])

        registry = yaml.safe_load(
            (project_dir / ".allmight" / "personalities.yaml").read_text()
        )
        assert registry["personalities"] == []

    def test_onboard_yaml_starts_unonboarded(self, project_dir: Path) -> None:
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(project_dir)])

        data = yaml.safe_load(
            (project_dir / ".allmight" / "onboard.yaml").read_text()
        )
        assert data["onboarded"] is False
        assert data["personalities"] == []
        assert data.get("folders", []) == []

    def test_seeds_suggestion_catalog(self, project_dir: Path) -> None:
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(project_dir)])

        suggestions_dir = project_dir / ".allmight" / "suggestions" / "personalities"
        assert suggestions_dir.is_dir()
        # `general` is the always-offered fallback — must always be seeded.
        general = suggestions_dir / "general.yaml"
        assert general.exists()
        body = yaml.safe_load(general.read_text())
        assert body["name"] == "general"
        assert "database" in body["capabilities"]
        assert "memory" in body["capabilities"]

    def test_does_not_populate_sync_templates(self, project_dir: Path) -> None:
        """``.allmight/templates/`` is the ``/sync`` re-init staging area.
        First init must not write into it — that path is owned by
        ``/sync``, distinct from ``.allmight/suggestions/``."""
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(project_dir)])

        templates_dir = project_dir / ".allmight" / "templates"
        if templates_dir.exists():
            files = list(templates_dir.rglob("*"))
            assert files == [], (
                f".allmight/templates/ should be empty on first init, got {files}"
            )

    def test_writes_opencode_globals(self, project_dir: Path) -> None:
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(project_dir)])

        # Project-wide skills installed by database capability
        assert (project_dir / ".opencode" / "skills" / "onboard" / "SKILL.md").is_file()
        assert (project_dir / ".opencode" / "commands" / "onboard.md").is_file()
        # Project-wide commands installed by memory capability
        assert (project_dir / ".opencode" / "commands" / "remember.md").is_file()
        assert (project_dir / ".opencode" / "commands" / "recall.md").is_file()

    def test_writes_root_context_files(self, project_dir: Path) -> None:
        runner = CliRunner()
        runner.invoke(main, ["init", "--yes", str(project_dir)])

        assert (project_dir / "MEMORY.md").is_file()
        assert (project_dir / "AGENTS.md").is_file()


class TestInitOutputMessage:
    def test_message_directs_user_to_onboard(self, project_dir: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--yes", str(project_dir)])
        assert "/onboard" in result.output


class TestReInitPreservesPersonalitiesAndAgentsMd:
    """Re-init must not clobber existing personality state.

    Track A's scaffold-only init created a regression: re-init called
    ``compose_agents_md(root, [], ...)`` and ``write_registry(root,
    [])`` unconditionally, wiping any personalities the user had added
    via ``allmight add`` or ``/onboard``. The fix:

    * Re-init reads the existing registry and passes those instances
      to ``compose_agents_md`` so the regenerated AGENTS.md still
      lists them.
    * Re-init only seeds an empty registry on **first** init.
    * Re-init backs up the existing ``AGENTS.md`` to
      ``.allmight/templates/AGENTS.md.backup`` (a fixed name) so
      ``/sync`` can reconcile any user edits that lived directly in
      AGENTS.md (rather than in the underlying ROLE.md).

    The new AGENTS.md is intentionally *not* annotated with a
    callout pointing at the backup — once ``/sync`` merges and
    deletes the backup, no stale pointer is left behind. The
    documentation lives in the ``/sync`` skill body.
    """

    def _init_and_add(self, project_dir: Path) -> CliRunner:
        runner = CliRunner()
        r = runner.invoke(main, ["init", "--yes", str(project_dir)])
        assert r.exit_code == 0, r.output
        import os
        cwd = os.getcwd()
        os.chdir(project_dir)
        try:
            r = runner.invoke(
                main,
                ["add", "general", "--capabilities", "database,memory"],
            )
            assert r.exit_code == 0, r.output
        finally:
            os.chdir(cwd)
        return runner

    def test_reinit_preserves_registry(self, project_dir: Path) -> None:
        self._init_and_add(project_dir)
        # Re-init in place.
        CliRunner().invoke(main, ["init", "--yes", str(project_dir)])

        registry = yaml.safe_load(
            (project_dir / ".allmight" / "personalities.yaml").read_text()
        )
        names = [r.get("name") or r.get("instance") for r in registry["personalities"]]
        assert "general" in names, (
            f"re-init wiped the registry; got {names}"
        )

    def test_reinit_recomposes_agents_md_with_existing_personality(
        self, project_dir: Path,
    ) -> None:
        self._init_and_add(project_dir)
        CliRunner().invoke(main, ["init", "--yes", str(project_dir)])

        content = (project_dir / "AGENTS.md").read_text()
        # The regenerated AGENTS.md must still mention the personality
        # the user added before re-init.
        assert "general" in content, (
            "re-init regenerated AGENTS.md without the existing personality"
        )

    def test_reinit_backs_up_pre_regeneration_agents_md(
        self, project_dir: Path,
    ) -> None:
        self._init_and_add(project_dir)

        # User edits AGENTS.md directly — this content is what /sync
        # later needs to reconcile from the backup.
        agents = project_dir / "AGENTS.md"
        original = agents.read_text()
        sentinel = "## User Notes\nFollow PEP-8 strictly.\n"
        agents.write_text(original + "\n" + sentinel)

        CliRunner().invoke(main, ["init", "--yes", str(project_dir)])

        backup = project_dir / ".allmight" / "templates" / "AGENTS.md.backup"
        assert backup.is_file(), "re-init did not write the AGENTS.md backup"
        assert sentinel in backup.read_text(), (
            "AGENTS.md backup is missing the user's edits"
        )

    def test_reinit_does_not_inject_backup_callout_into_agents_md(
        self, project_dir: Path,
    ) -> None:
        """The regenerated AGENTS.md must not carry a sticky pointer to
        the backup file — once /sync merges and deletes the backup, the
        pointer would become stale. Reconciliation guidance lives in
        the /sync skill body instead.
        """
        self._init_and_add(project_dir)
        CliRunner().invoke(main, ["init", "--yes", str(project_dir)])

        content = (project_dir / "AGENTS.md").read_text()
        assert "AGENTS.md.backup" not in content
        assert ".allmight/templates/AGENTS.md.backup" not in content

    def test_first_init_does_not_create_backup(self, project_dir: Path) -> None:
        """No prior AGENTS.md → no backup to make. The
        ``.allmight/templates/AGENTS.md.backup`` path must only appear
        on a true re-init.
        """
        CliRunner().invoke(main, ["init", "--yes", str(project_dir)])
        backup = project_dir / ".allmight" / "templates" / "AGENTS.md.backup"
        assert not backup.exists()
