"""Tests for ``allmight compose`` — the self-evolution closure.

The agent can write ``personalities/<p>/skills/<name>/`` at runtime,
but OpenCode only sees entries projected into ``.opencode/``;
projection used to run solely inside ``allmight add`` (install time).
``allmight compose`` re-runs the projection on demand so a runtime-
created skill becomes invocable without re-installing anything.
/reflect's Skill-check step teaches the agent to call it.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from allmight.cli import main


@pytest.fixture
def runner():
    return CliRunner()


def _init_project(runner) -> None:
    result = runner.invoke(main, ["init", ".", "--yes"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(main, ["add", "tester", "--capabilities", "memory"])
    assert result.exit_code == 0, result.output


class TestComposeCommand:

    def test_compose_errors_outside_project(self, runner):
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["compose"])
            assert result.exit_code == 1
            assert "not an All-Might project" in result.output

    def test_compose_handles_empty_registry(self, runner):
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["init", ".", "--yes"])
            assert result.exit_code == 0, result.output
            result = runner.invoke(main, ["compose"])
            assert result.exit_code == 0, result.output
            assert "nothing to compose" in result.output

    def test_compose_projects_runtime_skill(self, runner):
        """The core closure: agent-written skill → visible to OpenCode."""
        with runner.isolated_filesystem():
            _init_project(runner)
            skill_dir = Path("personalities/tester/skills/probe")
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: probe\ndescription: runtime-created\n---\nDo X.\n"
            )
            result = runner.invoke(main, ["compose"])
            assert result.exit_code == 0, result.output
            assert "Composed 1 personalities" in result.output
            link = Path(".opencode/skills/probe")
            assert link.is_symlink(), "runtime skill must be projected"
            assert (link / "SKILL.md").read_text().endswith("Do X.\n")

    def test_compose_idempotent(self, runner):
        with runner.isolated_filesystem():
            _init_project(runner)
            skill_dir = Path("personalities/tester/skills/probe")
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: probe\n---\nX\n")
            first = runner.invoke(main, ["compose"])
            second = runner.invoke(main, ["compose"])
            assert first.exit_code == 0 and second.exit_code == 0
            assert "conflict" not in second.output
            assert Path(".opencode/skills/probe").is_symlink()

    def test_compose_creates_empty_slots(self, runner):
        """compose() guarantees the per-personality slots exist, so an
        agent always has a place to write runtime entries."""
        with runner.isolated_filesystem():
            _init_project(runner)
            import shutil
            shutil.rmtree("personalities/tester/skills", ignore_errors=True)
            shutil.rmtree("personalities/tester/commands", ignore_errors=True)
            result = runner.invoke(main, ["compose"])
            assert result.exit_code == 0, result.output
            assert Path("personalities/tester/skills").is_dir()
            assert Path("personalities/tester/commands").is_dir()

    def test_compose_reports_conflict_and_stages_manifest(self, runner):
        with runner.isolated_filesystem():
            _init_project(runner)
            skill_dir = Path("personalities/tester/skills/probe")
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: probe\n---\nX\n")
            # Pre-occupy the destination with user content (not ours).
            blocker = Path(".opencode/skills/probe")
            blocker.mkdir(parents=True)
            (blocker / "SKILL.md").write_text("user's own probe skill")
            result = runner.invoke(main, ["compose"])
            assert result.exit_code == 0, result.output
            assert "conflict" in result.output
            assert "run /sync" in result.output
            assert Path(".allmight/templates/conflicts.yaml").is_file()
            # User content untouched.
            assert (blocker / "SKILL.md").read_text() == "user's own probe skill"


class TestComposeAgentsMdGuard:
    """compose_agents_md must never clobber user content in AGENTS.md.

    super-learner ships a hand-written AGENTS.md entry point (no
    marker). Before the guard, any ``allmight init`` / ``compose``
    run overwrote it silently — a data-loss bug. The guard used to
    *refuse* to write, which cost the project its framework primer;
    now the composition is fenced and coexists with the user's prose.
    """

    def test_compose_appends_fence_below_custom_agents_md(self, runner):
        with runner.isolated_filesystem():
            _init_project(runner)
            custom = "# my hand-written agents file\ndo not lose me\n"
            Path("AGENTS.md").write_text(custom)
            result = runner.invoke(main, ["compose"])
            assert result.exit_code == 0, result.output
            merged = Path("AGENTS.md").read_text()
            # User bytes survive verbatim, as a prefix.
            assert merged.startswith(custom)
            # ...and the framework primer actually lands, fenced.
            assert "<!-- ALL-MIGHT:BEGIN -->" in merged
            assert "<!-- ALL-MIGHT:END -->" in merged
            assert "## About All-Might" in merged
            # No stale whole-file conflict left for /sync to chew on.
            assert not Path(".allmight/templates/AGENTS.md").exists()

    def test_reinit_appends_fence_below_custom_agents_md(self, runner):
        with runner.isolated_filesystem():
            _init_project(runner)
            custom = "# my hand-written agents file\n"
            Path("AGENTS.md").write_text(custom)
            result = runner.invoke(main, ["init", ".", "--yes"])
            assert result.exit_code == 0, result.output
            merged = Path("AGENTS.md").read_text()
            assert merged.startswith(custom)
            assert "<!-- ALL-MIGHT:BEGIN -->" in merged

    def test_opt_out_marker_blocks_all_writes(self, runner):
        """``ALL-MIGHT:OFF`` outside the fence means hands off entirely."""
        with runner.isolated_filesystem():
            _init_project(runner)
            custom = "<!-- ALL-MIGHT:OFF -->\n# mine alone\n"
            Path("AGENTS.md").write_text(custom)
            result = runner.invoke(main, ["compose"])
            assert result.exit_code == 0, result.output
            assert Path("AGENTS.md").read_text() == custom
            staged = Path(".allmight/templates/AGENTS.md")
            assert staged.is_file(), "opted-out composition must stage for /sync"
            assert "all-might generated" in staged.read_text()

    def test_user_prose_around_fence_survives_recompose(self, runner):
        """The regression this fence exists for.

        A user who appends their own dedicated agent prompts to a
        previously-composed AGENTS.md lost them on the next
        ``allmight add`` — whole-file regeneration, no warning, no
        staging.
        """
        with runner.isolated_filesystem():
            _init_project(runner)
            before = "# house rules\nalways check reset polarity\n\n"
            after = "\n## My dedicated agent prompts\n- reviewer: be terse\n"
            Path("AGENTS.md").write_text(
                before + Path("AGENTS.md").read_text() + after
            )
            result = runner.invoke(main, ["add", "second", "--capabilities", "memory"])
            assert result.exit_code == 0, result.output
            merged = Path("AGENTS.md").read_text()
            assert merged.startswith(before)
            assert merged.endswith(after)
            assert "always check reset polarity" in merged
            assert "reviewer: be terse" in merged
            # Exactly one fence — recompose must not stack blocks.
            assert merged.count("<!-- ALL-MIGHT:BEGIN -->") == 1
            assert merged.count("<!-- ALL-MIGHT:END -->") == 1

    def test_markered_agents_md_still_recomposed(self, runner):
        with runner.isolated_filesystem():
            _init_project(runner)
            body = Path("AGENTS.md").read_text()
            assert "all-might generated" in body
            result = runner.invoke(main, ["compose"])
            assert result.exit_code == 0, result.output
            recomposed = Path("AGENTS.md").read_text()
            assert "all-might generated" in recomposed
            # tester's ROLE.md body (memory capability) is stitched in —
            # not the placeholder for a personality-less project.
            assert "no personalities yet" not in recomposed
