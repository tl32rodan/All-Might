"""``allmight init`` is additive — end-to-end data-loss regression pins.

Every test here starts from a directory that already contains user
content and asserts the *content* survives a real ``allmight init``
(and, where relevant, ``allmight add`` / ``allmight compose``).
Asserting mere existence is not enough: the AGENTS.md regression this
file was written for kept the file and silently replaced its body.

Verified failures these tests would have caught:

* ``allmight add`` regenerating the whole ``AGENTS.md`` and dropping
  user-appended agent prompts;
* a pre-existing hand-written ``AGENTS.md`` blocking the framework
  primer forever (init printed "delete or rename to allow
  regeneration" and staged the composition nobody ever merged);
* ``.opencode/commands/enrich.md`` being ``unlink()``-ed with no marker
  check, destroying a user's own command on first init;
* a marker-carrying plugin fork being deleted with no way back;
* ``shutil.rmtree(.allmight/templates)`` taking another capability's
  staging and ``conflicts.yaml`` with it;
* a user-owned ``.claude/commands/`` silently costing the project its
  entire Claude Code command surface.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from allmight.cli import main


@pytest.fixture
def runner():
    return CliRunner()


def _init(runner, *extra: str):
    result = runner.invoke(main, ["init", ".", "--yes", *extra])
    assert result.exit_code == 0, result.output
    return result


# ======================================================================
# AGENTS.md — the shared agent-context file
# ======================================================================


class TestAgentsMdCoexistence:
    """AGENTS.md holds All-Might's composition *and* the user's own
    instructions. Only the fenced region is ours."""

    def test_hand_written_agents_md_survives_and_gains_the_primer(
        self, runner,
    ):
        with runner.isolated_filesystem():
            custom = (
                "# My Project\n\n"
                "## Dedicated agent prompts\n"
                "You are a rigorous RTL reviewer. Check reset polarity.\n"
            )
            Path("AGENTS.md").write_text(custom)
            _init(runner)
            merged = Path("AGENTS.md").read_text()
            assert merged.startswith(custom), "user bytes must be preserved"
            assert "rigorous RTL reviewer" in merged
            # The whole point of coexisting: the primer actually lands.
            assert "## About All-Might" in merged
            assert "<!-- ALL-MIGHT:BEGIN -->" in merged

    def test_user_prose_survives_add_and_reinit_and_compose(self, runner):
        with runner.isolated_filesystem():
            _init(runner)
            addition = "\n## My dedicated agent prompts\n- be terse\n"
            Path("AGENTS.md").write_text(Path("AGENTS.md").read_text() + addition)

            for argv in (
                ["add", "reviewer", "--capabilities", "memory"],
                ["init", ".", "--yes"],
                ["compose"],
            ):
                result = runner.invoke(main, argv)
                assert result.exit_code == 0, result.output
                body = Path("AGENTS.md").read_text()
                assert "be terse" in body, f"lost user prose after {argv}"
                assert body.count("<!-- ALL-MIGHT:BEGIN -->") == 1

    def test_recompose_refreshes_only_the_fenced_region(self, runner):
        with runner.isolated_filesystem():
            _init(runner)
            before = "TOP MARKER\n\n"
            after = "\n\nBOTTOM MARKER\n"
            Path("AGENTS.md").write_text(
                before + Path("AGENTS.md").read_text().rstrip("\n") + after
            )
            result = runner.invoke(
                main, ["add", "reviewer", "--capabilities", "memory"]
            )
            assert result.exit_code == 0, result.output
            body = Path("AGENTS.md").read_text()
            assert body.startswith(before)
            assert body.endswith(after)
            # Fence interior refreshed: the personality-less placeholder
            # is gone now that a personality exists.
            assert "no personalities yet" not in body

    def test_opt_out_marker_is_respected_by_init(self, runner):
        with runner.isolated_filesystem():
            _init(runner)
            opted = "<!-- ALL-MIGHT:OFF -->\n# strictly mine\n"
            Path("AGENTS.md").write_text(opted)
            _init(runner)
            assert Path("AGENTS.md").read_text() == opted
            assert Path(".allmight/templates/AGENTS.md").is_file()

    def test_generated_block_does_not_trip_its_own_opt_out(self, runner):
        """The header explains the opt-out; it must not *be* one.

        A literal ``ALL-MIGHT:OFF`` comment inside our own block froze
        every later recompose — the file stayed on the empty-registry
        composition forever.
        """
        with runner.isolated_filesystem():
            _init(runner)
            result = runner.invoke(
                main, ["add", "reviewer", "--capabilities", "memory"]
            )
            assert result.exit_code == 0, result.output
            assert "no personalities yet" not in Path("AGENTS.md").read_text()

    def test_legacy_unfenced_composition_is_backed_up(self, runner):
        """Pre-fence AGENTS.md: migrate, and keep a recoverable copy of
        anything we could not place."""
        with runner.isolated_filesystem():
            _init(runner)
            Path("AGENTS.md").write_text(
                "<!-- ALL-MIGHT -->\nlegacy section body\n"
            )
            _init(runner)
            body = Path("AGENTS.md").read_text()
            assert "<!-- ALL-MIGHT:BEGIN -->" in body
            assert "legacy section body" not in body
            prev = Path(".allmight/templates/AGENTS.md.prev")
            assert prev.is_file()
            assert "legacy section body" in prev.read_text()


# ======================================================================
# .opencode/ — commands, plugins, skills the user owns
# ======================================================================


class TestOpencodeSurfaceIsPreserved:

    @pytest.mark.parametrize("name", ["enrich.md", "ingest.md"])
    def test_user_command_at_a_retired_name_survives_first_init(
        self, runner, name,
    ):
        """Fresh init in a populated dir used to ``unlink()`` these."""
        with runner.isolated_filesystem():
            cmds = Path(".opencode/commands")
            cmds.mkdir(parents=True)
            body = f"# my own {name}\ndo a thing\n"
            (cmds / name).write_text(body)
            _init(runner)
            assert (cmds / name).read_text() == body

    def test_user_plugin_without_marker_is_untouched(self, runner):
        with runner.isolated_filesystem():
            _init(runner)
            mine = Path(".opencode/plugins/my-linter.ts")
            body = "export const MyLinter = async () => ({});\n"
            mine.write_text(body)
            _init(runner)
            assert mine.read_text() == body

    def test_user_skill_and_command_survive_reinit(self, runner):
        with runner.isolated_filesystem():
            _init(runner)
            skill = Path(".opencode/skills/myskill/SKILL.md")
            skill.parent.mkdir(parents=True)
            skill.write_text("my skill body\n")
            cmd = Path(".opencode/commands/mycmd.md")
            cmd.write_text("my command body\n")
            _init(runner)
            assert skill.read_text() == "my skill body\n"
            assert cmd.read_text() == "my command body\n"

    def test_user_agent_file_survives_reinit(self, runner):
        with runner.isolated_filesystem():
            _init(runner)
            agent = Path(".opencode/agents/myagent.md")
            agent.parent.mkdir(parents=True, exist_ok=True)
            agent.write_text("---\ndescription: mine\n---\nbody\n")
            _init(runner)
            assert "description: mine" in agent.read_text()


# ======================================================================
# Staging directory ownership
# ======================================================================


class TestStagingIsNotWipedWholesale:

    def test_force_init_keeps_foreign_staged_files(self, runner):
        """``--force`` used to ``rmtree`` the whole templates dir from
        inside the *database* capability — taking other capabilities'
        staging and ``conflicts.yaml`` with it."""
        with runner.isolated_filesystem():
            _init(runner)
            tpl = Path(".allmight/templates")
            tpl.mkdir(parents=True, exist_ok=True)
            (tpl / "conflicts.yaml").write_text("compose_conflicts: []\n")
            (tpl / "memory-load.ts").write_text("// all-might generated\nx\n")
            foreign = tpl / "someone-elses.txt"
            foreign.write_text("keep me\n")
            _init(runner, "--force")
            assert foreign.read_text() == "keep me\n"
            assert Path(".allmight/templates/conflicts.yaml").is_file()

    def test_force_init_drops_database_own_staging(self, runner):
        """It still clears what it owns — a stale staged search.md
        would otherwise make /sync re-apply old content."""
        with runner.isolated_filesystem():
            _init(runner)
            staged = Path(".allmight/templates/commands/search.md")
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_text("<!-- all-might generated -->\nstale\n")
            _init(runner, "--force")
            assert not staged.exists()


# ======================================================================
# Claude Code bridge
# ======================================================================


class TestClaudeBridgeIsAdditive:

    def test_user_owned_claude_commands_dir_still_gets_our_entries(
        self, runner,
    ):
        """A real ``.claude/commands/`` used to mean *no* All-Might
        commands on the Claude Code side, with no warning."""
        with runner.isolated_filesystem():
            claude_cmds = Path(".claude/commands")
            claude_cmds.mkdir(parents=True)
            (claude_cmds / "mycmd.md").write_text("mine\n")
            _init(runner)
            # User's file untouched, and not turned into a symlink.
            assert (claude_cmds / "mycmd.md").read_text() == "mine\n"
            assert not (claude_cmds / "mycmd.md").is_symlink()
            # Ours linked in beside it.
            linked = sorted(
                p.name for p in claude_cmds.iterdir() if p.is_symlink()
            )
            assert "search.md" in linked
            assert (claude_cmds / "search.md").is_file(), "link must resolve"

    def test_name_clash_in_claude_dir_keeps_user_file_and_warns(self, runner):
        with runner.isolated_filesystem():
            claude_cmds = Path(".claude/commands")
            claude_cmds.mkdir(parents=True)
            (claude_cmds / "search.md").write_text("my own search\n")
            result = _init(runner)
            assert (claude_cmds / "search.md").read_text() == "my own search\n"
            assert ".claude/commands/search.md" in result.output

    def test_user_symlink_to_elsewhere_is_preserved(self, runner):
        """`.claude/commands -> ../shared/commands` is the user's wiring.

        We used to ``unlink()`` any symlink that was not spelled exactly
        like ours and replace it — discarding their setup silently.
        """
        with runner.isolated_filesystem():
            shared = Path("shared/commands")
            shared.mkdir(parents=True)
            (shared / "theirs.md").write_text("theirs\n")
            Path(".claude").mkdir()
            link = Path(".claude/commands")
            link.symlink_to(Path("..") / "shared" / "commands")
            result = _init(runner)
            assert link.is_symlink()
            assert link.readlink() == Path("..") / "shared" / "commands"
            assert ".claude/commands" in result.output

    def test_equivalent_symlink_spelling_is_normalised(self, runner):
        """A link that already resolves to our target may be rewritten."""
        with runner.isolated_filesystem():
            _init(runner)
            link = Path(".claude/commands")
            link.unlink()
            link.symlink_to(Path(".opencode/commands").resolve())
            _init(runner)
            assert link.readlink() == Path("..") / ".opencode" / "commands"

    def test_legacy_hook_script_is_quarantined_not_deleted(self, runner):
        with runner.isolated_filesystem():
            _init(runner)
            legacy = Path(".claude/hooks/reflection.py")
            legacy.write_text("# all-might generated\nprint('old')\n")
            _init(runner)
            assert not legacy.exists()
            attic = Path(".allmight/attic/.claude/hooks/reflection.py")
            assert attic.is_file()
            assert "print('old')" in attic.read_text()

    def test_user_authored_legacy_hook_name_is_left_alone(self, runner):
        with runner.isolated_filesystem():
            _init(runner)
            mine = Path(".claude/hooks/reflection.py")
            mine.write_text("# my own reflection hook\n")
            _init(runner)
            assert mine.read_text() == "# my own reflection hook\n"

    def test_plain_project_still_gets_dir_symlinks(self, runner):
        """The preferred shape must not regress into per-entry links."""
        with runner.isolated_filesystem():
            _init(runner)
            for kind in ("commands", "skills"):
                link = Path(".claude") / kind
                assert link.is_symlink()
                assert link.readlink() == Path("..") / ".opencode" / kind

    def test_user_settings_and_mcp_entries_survive(self, runner):
        with runner.isolated_filesystem():
            _init(runner)
            settings = Path(".claude/settings.json")
            cfg = json.loads(settings.read_text())
            cfg["env"] = {"MY_VAR": "1"}
            cfg.setdefault("hooks", {}).setdefault("SessionStart", []).append(
                {"hooks": [{"type": "command", "command": "echo mine"}]}
            )
            settings.write_text(json.dumps(cfg, indent=2))
            mcp = Path(".mcp.json")
            mcp.write_text(json.dumps({"mcpServers": {"mine": {"command": "y"}}}))
            _init(runner)
            after = json.loads(settings.read_text())
            assert after.get("env") == {"MY_VAR": "1"}
            commands = [
                h["command"]
                for block in after["hooks"]["SessionStart"]
                for h in block["hooks"]
            ]
            assert "echo mine" in commands
            assert "mine" in json.loads(mcp.read_text())["mcpServers"]


# ======================================================================
# Root context files
# ======================================================================


class TestRootContextFilesArePreserved:

    def test_memory_md_user_prefs_survive(self, runner):
        with runner.isolated_filesystem():
            _init(runner)
            Path("MEMORY.md").write_text(
                Path("MEMORY.md").read_text() + "\n## My prefs\n- tabs\n"
            )
            _init(runner)
            runner.invoke(main, ["add", "reviewer", "--capabilities", "memory"])
            assert "- tabs" in Path("MEMORY.md").read_text()

    def test_role_md_edits_survive_and_reach_agents_md(self, runner):
        with runner.isolated_filesystem():
            _init(runner)
            result = runner.invoke(
                main, ["add", "reviewer", "--capabilities", "memory"]
            )
            assert result.exit_code == 0, result.output
            role = Path("personalities/reviewer/ROLE.md")
            role.write_text(role.read_text() + "\n## House rule\nno tabs\n")
            _init(runner)
            assert "no tabs" in role.read_text()
            assert "no tabs" in Path("AGENTS.md").read_text()

    def test_user_claude_md_is_not_replaced(self, runner):
        with runner.isolated_filesystem():
            body = "# my own CLAUDE.md\n@docs/whatever.md\n"
            Path("CLAUDE.md").write_text(body)
            _init(runner)
            assert Path("CLAUDE.md").read_text() == body

    def test_user_opencode_config_keys_survive(self, runner):
        with runner.isolated_filesystem():
            oc = Path(".opencode")
            oc.mkdir()
            (oc / "opencode.json").write_text(
                json.dumps({"model": "anthropic/claude-opus-4",
                            "mcp": {"myserver": {"type": "local"}}})
            )
            (oc / "package.json").write_text(
                json.dumps({"name": "mine", "dependencies": {"zod": "^3.0.0"}})
            )
            _init(runner)
            cfg = json.loads((oc / "opencode.json").read_text())
            assert cfg["model"] == "anthropic/claude-opus-4"
            assert "myserver" in cfg["mcp"]
            pkg = json.loads((oc / "package.json").read_text())
            assert pkg["dependencies"]["zod"] == "^3.0.0"
            assert "@opencode-ai/plugin" in pkg["dependencies"]


# ======================================================================
# Nothing leaves the project without landing in the attic
# ======================================================================


class TestNothingIsDeletedOutright:

    def test_every_removal_lands_in_the_attic(self, runner):
        """Sweep the tree before and after a re-init that retires files.

        Any path that disappears must be recoverable from
        ``.allmight/attic/`` — that is the whole invariant, stated once.
        """
        with runner.isolated_filesystem():
            _init(runner)
            Path(".opencode/plugins/gone.ts").write_text(
                "// all-might generated\nold plugin\n"
            )
            Path(".opencode/commands/enrich.md").write_text(
                "<!-- all-might generated -->\nold command\n"
            )
            root = Path(".")
            ignored = (".allmight/templates", ".allmight/attic")

            def snapshot() -> set[str]:
                out = set()
                for p in root.rglob("*"):
                    rel = str(p.relative_to(root))
                    if any(rel.startswith(i) for i in ignored):
                        continue
                    if p.is_file() and not p.is_symlink():
                        out.add(rel)
                return out

            before = snapshot()
            _init(runner)
            vanished = before - snapshot()
            assert vanished, "expected the sweep to retire something"
            attic = Path(".allmight/attic")
            for rel in vanished:
                assert (attic / rel).is_file(), (
                    f"{rel} disappeared without landing in the attic"
                )
