"""Tests for the ``schedule`` capability (T1).

Acceptance criteria from ``docs/schedule-proposal.md`` §3.4.

T1 ships:
- TEMPLATE registered, discoverable via ``core.personalities.discover``
- ``_install_globals`` writes ``.opencode/skills/scheduling/SKILL.md``
  with the All-Might marker
- ``_install`` creates an empty ``personalities/<p>/scheduled/`` dir
- ``personalities.yaml`` lists ``schedule`` under the personality's
  capabilities (verified via cli ``add``)
- No Claude Code hook file emitted (CC mirror deferred per P-6)
- SKILL.md body describes the ``am-<personality>-<task>`` slug
  convention

Negative assertions are required per CLAUDE.md "Discipline When
Generating Third-Party Integrations".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from allmight.capabilities.schedule import TEMPLATE
from allmight.capabilities.schedule.initializer import ScheduleInitializer
from allmight.capabilities.schedule.skill_content import (
    SCHEDULING_SKILL_DESCRIPTION,
    build_scheduling_skill_md,
)
from allmight.core.markers import ALLMIGHT_MARKER_MD
from allmight.core.personalities import (
    InstallContext,
    Personality,
    discover,
)
from allmight.core.domain import ProjectManifest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """A minimal project root."""
    return tmp_path


@pytest.fixture
def manifest(project_root: Path) -> ProjectManifest:
    return ProjectManifest(name="demo", root_path=project_root)


@pytest.fixture
def ctx(project_root: Path, manifest: ProjectManifest) -> InstallContext:
    return InstallContext(
        project_root=project_root,
        manifest=manifest,
        staging=False,
        force=False,
    )


@pytest.fixture
def personality(project_root: Path) -> Personality:
    return Personality(
        template=TEMPLATE,
        project_root=project_root,
        name="alpha",
        capabilities=["schedule"],
    )


# ---------------------------------------------------------------------------
# TEMPLATE registration
# ---------------------------------------------------------------------------


class TestTemplateRegistration:
    def test_template_is_a_personality_template(self) -> None:
        from allmight.core.personalities import PersonalityTemplate
        assert isinstance(TEMPLATE, PersonalityTemplate)

    def test_template_name_is_schedule(self) -> None:
        assert TEMPLATE.name == "schedule"
        assert TEMPLATE.short_name == "schedule"

    def test_template_has_install_and_install_globals(self) -> None:
        assert TEMPLATE.install is not None
        assert TEMPLATE.install_globals is not None

    def test_template_declares_owned_paths(self) -> None:
        # Both write surfaces must be declared so collision detection
        # has a chance to flag overlap with future capabilities.
        assert any("scheduled" in p for p in TEMPLATE.owned_paths)
        assert any(".opencode/skills/scheduling" in p for p in TEMPLATE.owned_paths)

    def test_template_no_cli_options(self) -> None:
        # T1 ships no flags. T2 still ships none — apply is a separate
        # subcommand, not a flag on init.
        assert TEMPLATE.cli_options == []

    def test_discover_finds_schedule(self) -> None:
        templates = discover()
        names = [t.name for t in templates]
        assert "schedule" in names


# ---------------------------------------------------------------------------
# install_globals — project-wide skill write
# ---------------------------------------------------------------------------


class TestInstallGlobalsWritesSkill:
    def test_writes_skill_md(self, ctx: InstallContext, project_root: Path) -> None:
        TEMPLATE.install_globals(ctx)
        skill_md = project_root / ".opencode" / "skills" / "scheduling" / "SKILL.md"
        assert skill_md.exists()

    def test_skill_md_has_marker(self, ctx: InstallContext, project_root: Path) -> None:
        TEMPLATE.install_globals(ctx)
        content = (
            project_root / ".opencode" / "skills" / "scheduling" / "SKILL.md"
        ).read_text()
        assert ALLMIGHT_MARKER_MD in content, (
            "missing all-might marker — re-init would treat file as user-authored"
        )

    def test_skill_frontmatter_name_and_description(
        self, ctx: InstallContext, project_root: Path
    ) -> None:
        TEMPLATE.install_globals(ctx)
        content = (
            project_root / ".opencode" / "skills" / "scheduling" / "SKILL.md"
        ).read_text()
        # Anthropic skill contract requires both fields in YAML
        # frontmatter; install_skill emits them on the first two lines
        # after the opening ``---``.
        assert "name: scheduling" in content
        assert "description:" in content

    def test_skill_describes_slug_convention(
        self, ctx: InstallContext, project_root: Path
    ) -> None:
        # P-3 requires the SKILL.md to teach the agent to prefix slugs
        # with ``am-<personality>-`` so user-managed jobs are
        # distinguishable on the same opencode-scheduler scope.
        TEMPLATE.install_globals(ctx)
        content = (
            project_root / ".opencode" / "skills" / "scheduling" / "SKILL.md"
        ).read_text()
        assert "am-<personality>-<task>" in content
        assert "am-" in content

    def test_skill_mentions_opencode_scheduler(
        self, ctx: InstallContext, project_root: Path
    ) -> None:
        # The de-facto runtime; the skill must name it explicitly so
        # the agent knows which MCP tools to call.
        TEMPLATE.install_globals(ctx)
        content = (
            project_root / ".opencode" / "skills" / "scheduling" / "SKILL.md"
        ).read_text()
        assert "opencode-scheduler" in content
        assert "schedule_job" in content

    def test_skill_warns_against_l3_ingest_scheduling(
        self, ctx: InstallContext, project_root: Path
    ) -> None:
        # Anti-pattern documented in proposal §3.2 — must surface
        # explicitly so the agent doesn't duplicate the reactive
        # marker-file closure.
        TEMPLATE.install_globals(ctx)
        content = (
            project_root / ".opencode" / "skills" / "scheduling" / "SKILL.md"
        ).read_text()
        assert "Don't schedule L3 ingest" in content


# ---------------------------------------------------------------------------
# /sync interaction — re-init must NOT clobber user-edited (marker'd) SKILL.md
# ---------------------------------------------------------------------------


class TestSyncInteraction:
    """Re-init (``staging=True``) must skip the skill write.

    Matches the established pattern — memory's ``recover`` skill and
    database's ``onboard`` / ``one-for-all`` / ``all-for-one`` /
    ``split`` skills are all installed on fresh init only and skipped
    on re-init. Only the ``/sync`` meta-skill itself is unconditionally
    re-written.

    The bug this guards against: if re-init unconditionally re-emits
    the SKILL.md, a user who tweaked the body but kept our marker
    silently loses their edits the next time they run ``allmight init``.
    """

    def test_install_globals_no_op_on_staging_when_skill_absent(
        self, project_root: Path, manifest: ProjectManifest
    ) -> None:
        # Simulate re-init on a project where the skill was never
        # installed: staging=True should NOT create it.
        ctx_reinit = InstallContext(
            project_root=project_root,
            manifest=manifest,
            staging=True,
            force=False,
        )
        TEMPLATE.install_globals(ctx_reinit)
        skill_md = project_root / ".opencode" / "skills" / "scheduling" / "SKILL.md"
        assert not skill_md.exists(), (
            "re-init must not install the skill — only fresh init does"
        )

    def test_install_globals_preserves_user_edits_with_marker_on_reinit(
        self, project_root: Path, manifest: ProjectManifest
    ) -> None:
        # Set up: install once (fresh), then tamper with the body but
        # keep the marker (the realistic "user tweaked it" case).
        ctx_fresh = InstallContext(
            project_root=project_root,
            manifest=manifest,
            staging=False,
            force=False,
        )
        TEMPLATE.install_globals(ctx_fresh)
        skill_md = project_root / ".opencode" / "skills" / "scheduling" / "SKILL.md"
        # User edit — keeps the marker but rewrites the body.
        skill_md.write_text(
            "---\nname: scheduling\ndescription: edited\n---\n\n"
            + ALLMIGHT_MARKER_MD
            + "\n\nUSER EDIT — must survive re-init\n"
        )
        original_content = skill_md.read_text()

        # Re-init.
        ctx_reinit = InstallContext(
            project_root=project_root,
            manifest=manifest,
            staging=True,
            force=False,
        )
        TEMPLATE.install_globals(ctx_reinit)

        assert skill_md.read_text() == original_content, (
            "re-init silently clobbered a marker'd user-edited skill"
        )

    def test_install_globals_writes_fresh_on_non_staging(
        self, project_root: Path, manifest: ProjectManifest
    ) -> None:
        # The other side of the symmetry: fresh init still writes.
        ctx = InstallContext(
            project_root=project_root,
            manifest=manifest,
            staging=False,
            force=False,
        )
        TEMPLATE.install_globals(ctx)
        skill_md = project_root / ".opencode" / "skills" / "scheduling" / "SKILL.md"
        assert skill_md.exists()
        # Fresh body, with our marker.
        content = skill_md.read_text()
        assert ALLMIGHT_MARKER_MD in content
        assert "USER EDIT" not in content

    def test_per_personality_scheduled_dir_idempotent_on_reinit(
        self,
        project_root: Path,
        manifest: ProjectManifest,
        personality: Personality,
    ) -> None:
        # On re-init, ``allmight init`` does NOT call ``template.install``
        # for existing personalities (only ``install_globals``).
        # Independently, the per-personality dir must be idempotent
        # against staging=True for the case that a future call path
        # exercises it. User files in scheduled/ must survive.
        ctx_fresh = InstallContext(
            project_root=project_root,
            manifest=manifest,
            staging=False,
            force=False,
        )
        TEMPLATE.install(ctx_fresh, personality)
        task_file = personality.root / "scheduled" / "my-task.md"
        task_file.write_text("USER TASK FILE — no marker, must survive\n")

        ctx_reinit = InstallContext(
            project_root=project_root,
            manifest=manifest,
            staging=True,
            force=False,
        )
        TEMPLATE.install(ctx_reinit, personality)
        assert task_file.exists()
        assert "USER TASK FILE" in task_file.read_text()


# ---------------------------------------------------------------------------
# install — per-personality dir scaffold
# ---------------------------------------------------------------------------


class TestInstallCreatesPersonalityScheduledDir:
    def test_scheduled_dir_created(
        self, ctx: InstallContext, personality: Personality
    ) -> None:
        TEMPLATE.install(ctx, personality)
        assert (personality.root / "scheduled").is_dir()

    def test_scheduled_dir_starts_empty(
        self, ctx: InstallContext, personality: Personality
    ) -> None:
        # T1 contract — no auto-installed jobs.
        TEMPLATE.install(ctx, personality)
        scheduled = personality.root / "scheduled"
        assert list(scheduled.iterdir()) == []

    def test_install_is_idempotent(
        self, ctx: InstallContext, personality: Personality
    ) -> None:
        TEMPLATE.install(ctx, personality)
        TEMPLATE.install(ctx, personality)  # second call must not error
        assert (personality.root / "scheduled").is_dir()


# ---------------------------------------------------------------------------
# status — reflects on-disk state
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_uninstalled_when_no_files(
        self, project_root: Path, personality: Personality
    ) -> None:
        s = TEMPLATE.status(project_root, personality)
        assert s.installed is False

    def test_status_installed_after_install(
        self,
        ctx: InstallContext,
        project_root: Path,
        personality: Personality,
    ) -> None:
        TEMPLATE.install_globals(ctx)
        TEMPLATE.install(ctx, personality)
        s = TEMPLATE.status(project_root, personality)
        assert s.installed is True
        assert s.version_on_disk == TEMPLATE.version

    def test_status_lists_declared_tasks(
        self,
        ctx: InstallContext,
        project_root: Path,
        personality: Personality,
    ) -> None:
        TEMPLATE.install_globals(ctx)
        TEMPLATE.install(ctx, personality)
        # Agent drops a reference declaration (T1 doesn't read it but
        # status still surfaces what's on disk).
        (personality.root / "scheduled" / "curator-audit.md").write_text(
            "placeholder\n"
        )
        s = TEMPLATE.status(project_root, personality)
        assert "curator-audit.md" in s.details["declared_tasks"]


# ---------------------------------------------------------------------------
# Negative assertions (CLAUDE.md "Discipline" rules)
# ---------------------------------------------------------------------------


class TestNoClaudeCodeMirror:
    def test_no_claude_hook_emitted_for_schedule(
        self, ctx: InstallContext, project_root: Path
    ) -> None:
        # P-6: Claude Code mirror is deferred indefinitely — CC users
        # have Anthropic Desktop scheduled tasks. Any schedule*.py
        # hook in .claude/hooks/ would silently drift and is forbidden.
        TEMPLATE.install_globals(ctx)
        hooks_dir = project_root / ".claude" / "hooks"
        if hooks_dir.exists():
            hook_files = list(hooks_dir.glob("schedule*.py"))
            assert hook_files == [], (
                "schedule capability must not emit Claude Code hooks "
                "(see P-6 in docs/schedule-proposal.md)"
            )

    def test_no_opencode_plugin_emitted_in_t1(
        self, ctx: InstallContext, project_root: Path
    ) -> None:
        # T1 ships zero plugins. ``schedule-sync.ts`` is the T2 plugin;
        # if a future change accidentally lands it under T1, this
        # negative assertion catches it.
        TEMPLATE.install_globals(ctx)
        plugins_dir = project_root / ".opencode" / "plugins"
        if plugins_dir.exists():
            schedule_plugins = list(plugins_dir.glob("schedule*.ts"))
            assert schedule_plugins == [], (
                "T1 must not emit a schedule plugin — that's T2's job"
            )


# ---------------------------------------------------------------------------
# Skill content helpers
# ---------------------------------------------------------------------------


class TestSkillContentHelpers:
    def test_build_scheduling_skill_md_returns_non_empty(self) -> None:
        body = build_scheduling_skill_md()
        assert body
        assert len(body.splitlines()) > 20  # not a stub

    def test_skill_description_mentions_slug_prefix(self) -> None:
        # The description string is what surfaces in OpenCode skill
        # discovery; the agent must see ``am-<personality>-<task>``
        # there so it picks the right convention without reading the
        # full body.
        assert "am-<personality>-<task>" in SCHEDULING_SKILL_DESCRIPTION
