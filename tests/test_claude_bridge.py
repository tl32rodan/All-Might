"""Tests for the Claude Code compatibility bridge.

The bridge is what lets one ``allmight init`` produce a project that
both OpenCode and Claude Code can drive without forking the source of
truth. These tests pin the contract:

* directory-level symlinks (so new commands/skills written by any
  capability template flow through to ``.claude/`` automatically),
* root ``CLAUDE.md`` is a thin ``@``-import shim,
* ``.claude/settings.json`` registers our hooks for SessionStart and
  PreCompact and merges with user-authored hooks instead of clobbering,
* ``.claude/hooks/role_load.py`` is generated and executable.
"""

import json
import os
import stat
import subprocess
import sys

import pytest

from allmight.core.claude_bridge import (
    _merge_hook_config,
    _settings_payload,
    write_claude_bridge,
)


@pytest.fixture
def project(tmp_path):
    """A pre-baked .opencode/ tree so the dir symlinks have a target."""
    opencode = tmp_path / ".opencode"
    (opencode / "commands").mkdir(parents=True)
    (opencode / "skills" / "onboard").mkdir(parents=True)
    (opencode / "commands" / "search.md").write_text("placeholder")
    (opencode / "skills" / "onboard" / "SKILL.md").write_text("placeholder")
    return tmp_path


class TestWriteClaudeBridge:

    def test_writes_root_claude_md(self, project):
        write_claude_bridge(project)
        body = (project / "CLAUDE.md").read_text()
        assert "@AGENTS.md" in body
        assert "@MEMORY.md" in body
        assert "all-might generated" in body

    def test_creates_dir_symlinks(self, project):
        write_claude_bridge(project)
        commands = project / ".claude" / "commands"
        skills = project / ".claude" / "skills"
        assert commands.is_symlink()
        assert skills.is_symlink()
        # Targets are relative so the project is portable.
        assert os.readlink(commands) == os.path.join("..", ".opencode", "commands")
        assert os.readlink(skills) == os.path.join("..", ".opencode", "skills")
        # And they actually resolve to the .opencode dirs.
        assert commands.resolve() == (project / ".opencode" / "commands").resolve()

    def test_dir_symlinks_pick_up_new_commands(self, project):
        """Adding a command after init shows up on both surfaces.

        This is the whole reason for using a directory-level symlink
        instead of N per-file symlinks: capability templates that add
        a new command later don't need a re-symlink step.
        """
        write_claude_bridge(project)
        (project / ".opencode" / "commands" / "newcmd.md").write_text("hi")
        assert (project / ".claude" / "commands" / "newcmd.md").is_file()

    def test_writes_role_load_hook(self, project):
        write_claude_bridge(project)
        hook = project / ".claude" / "hooks" / "role_load.py"
        body = hook.read_text()
        assert body.startswith("#!/usr/bin/env python3")
        assert "all-might generated" in body
        assert "ROLE.md" in body
        assert "DO NOT EDIT" in body

    def test_role_load_hook_is_executable(self, project):
        write_claude_bridge(project)
        hook = project / ".claude" / "hooks" / "role_load.py"
        mode = hook.stat().st_mode
        assert mode & stat.S_IXUSR
        assert mode & stat.S_IXGRP
        assert mode & stat.S_IXOTH

    def test_writes_settings_json_with_both_hooks(self, project):
        write_claude_bridge(project)
        settings = json.loads(
            (project / ".claude" / "settings.json").read_text()
        )
        for event in ("SessionStart", "PreCompact"):
            commands = [
                h["command"]
                for block in settings["hooks"][event]
                for h in block["hooks"]
            ]
            assert any("memory_load.py" in c for c in commands)
            assert any("role_load.py" in c for c in commands)

    def test_idempotent_on_rerun(self, project):
        write_claude_bridge(project)
        first_settings = (project / ".claude" / "settings.json").read_text()
        first_claude_md = (project / "CLAUDE.md").read_text()
        write_claude_bridge(project)
        second_settings = (project / ".claude" / "settings.json").read_text()
        second_claude_md = (project / "CLAUDE.md").read_text()
        assert first_settings == second_settings
        assert first_claude_md == second_claude_md


class TestUserAuthoredFilesPreserved:
    """write_guarded contract — never overwrite a user-authored file."""

    def test_preserves_user_authored_claude_md(self, project):
        custom = "# my own context\nstuff I wrote\n"
        (project / "CLAUDE.md").write_text(custom)
        write_claude_bridge(project)
        assert (project / "CLAUDE.md").read_text() == custom

    def test_preserves_user_authored_claude_dir_subfolder(self, project):
        # If the user already has .claude/commands as a real dir,
        # don't replace it with our symlink.
        (project / ".claude" / "commands").mkdir(parents=True)
        (project / ".claude" / "commands" / "user.md").write_text("mine")
        write_claude_bridge(project)
        assert not (project / ".claude" / "commands").is_symlink()
        assert (project / ".claude" / "commands" / "user.md").read_text() == "mine"


class TestSettingsHookMerge:

    def test_merge_preserves_unrelated_user_hooks(self):
        existing = {
            "model": "claude-sonnet-4-6",
            "hooks": {
                "PreToolUse": [
                    {"hooks": [{"type": "command", "command": "echo before-tool"}]}
                ]
            },
        }
        merged = _merge_hook_config(existing, _settings_payload())
        assert merged["model"] == "claude-sonnet-4-6"
        assert "PreToolUse" in merged["hooks"]
        assert any(
            h["command"] == "echo before-tool"
            for block in merged["hooks"]["PreToolUse"]
            for h in block["hooks"]
        )
        assert "SessionStart" in merged["hooks"]

    def test_merge_keeps_user_session_start_hooks(self):
        existing = {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "echo my-start"}]}
                ]
            }
        }
        merged = _merge_hook_config(existing, _settings_payload())
        commands = [
            h["command"]
            for block in merged["hooks"]["SessionStart"]
            for h in block["hooks"]
        ]
        assert "echo my-start" in commands
        assert any("memory_load.py" in c for c in commands)

    def test_merge_idempotent_does_not_duplicate_owned_entries(self):
        merged_once = _merge_hook_config({}, _settings_payload())
        merged_twice = _merge_hook_config(merged_once, _settings_payload())
        for event in ("SessionStart", "PreCompact"):
            commands = [
                h["command"]
                for block in merged_twice["hooks"][event]
                for h in block["hooks"]
            ]
            assert sum("memory_load.py" in c for c in commands) == 1
            assert sum("role_load.py" in c for c in commands) == 1


class TestHooksRunCleanly:
    """End-to-end: the generated hook scripts produce valid JSON."""

    def test_role_load_hook_returns_valid_json(self, project, tmp_path):
        # Set up a personality with a ROLE.md so the hook has content.
        role_dir = project / "personalities" / "demo"
        role_dir.mkdir(parents=True)
        (role_dir / "ROLE.md").write_text("# Demo\n\nbody\n")

        write_claude_bridge(project)
        hook = project / ".claude" / "hooks" / "role_load.py"

        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(project)
        result = subprocess.run(
            [sys.executable, str(hook)],
            input='{"hook_event_name": "SessionStart"}',
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        ctx = payload["hookSpecificOutput"]["additionalContext"]
        assert "Role: demo (ROLE.md)" in ctx
        assert "body" in ctx
        assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"

    def test_role_load_hook_silent_when_no_personalities(self, project):
        write_claude_bridge(project)
        hook = project / ".claude" / "hooks" / "role_load.py"

        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(project)
        result = subprocess.run(
            [sys.executable, str(hook)],
            input='{"hook_event_name": "SessionStart"}',
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        # No personalities → no context to inject → empty stdout (no JSON).
        assert result.stdout.strip() == ""
