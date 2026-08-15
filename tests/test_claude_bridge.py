"""Tests for the Claude Code compatibility bridge.

The bridge is what lets one ``allmight init`` produce a project that
both OpenCode and Claude Code can drive without forking the source of
truth. These tests pin the contract:

* directory-level symlinks (so new commands/skills written by any
  capability template flow through to ``.claude/`` automatically),
* root ``CLAUDE.md`` is a thin ``@``-import shim,
* ``.claude/settings.json`` registers our hooks on SessionStart (no
  matcher, so every source including ``compact``) and merges with
  user-authored hooks instead of clobbering,
* ``.claude/hooks/role_load.py`` is generated and executable.
"""

import json
import os
import stat
import subprocess
import sys

import pytest

from allmight.core.claude_bridge import (
    _hook_command,
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

    def test_writes_feedback_check_hook(self, project):
        write_claude_bridge(project)
        hook = project / ".claude" / "hooks" / "feedback_check.py"
        body = hook.read_text()
        assert body.startswith("#!/usr/bin/env python3")
        assert "all-might generated" in body
        assert "DO NOT EDIT" in body
        # Mirror-of relationship is documented in the header.
        assert "feedback-check.ts" in body
        # Prompt content is present.
        assert "Feedback Check" in body
        assert "[tool-deadend]" in body
        assert ".allmight/feedback/notes.md" in body
        # Hook contract: plain stdout is the documented context channel
        # for UserPromptSubmit. Negative assertion — hookSpecificOutput
        # has no section for this event and is absorbed silently.
        assert "sys.stdout.write(FEEDBACK_CHECK_PROMPT)" in body
        assert '"hookSpecificOutput":' not in body
        assert "UserPromptSubmit" in body

    def test_feedback_check_hook_is_executable(self, project):
        write_claude_bridge(project)
        hook = project / ".claude" / "hooks" / "feedback_check.py"
        mode = hook.stat().st_mode
        assert mode & stat.S_IXUSR
        assert mode & stat.S_IXGRP
        assert mode & stat.S_IXOTH

    def test_writes_settings_json_session_start_only(self, project):
        write_claude_bridge(project)
        settings = json.loads(
            (project / ".claude" / "settings.json").read_text()
        )
        # SessionStart only — no matcher, so it fires for every source
        # including "compact". PreCompact was retired: it fired *before*
        # compaction, the opposite end from the OpenCode side.
        commands = [
            h["command"]
            for block in settings["hooks"]["SessionStart"]
            for h in block["hooks"]
        ]
        assert any("memory_load.py" in c for c in commands)
        assert any("role_load.py" in c for c in commands)
        assert "PreCompact" not in settings["hooks"]

    def test_writes_settings_json_with_user_prompt_submit(self, project):
        """Feedback-check hook is registered on UserPromptSubmit."""
        write_claude_bridge(project)
        settings = json.loads(
            (project / ".claude" / "settings.json").read_text()
        )
        commands = [
            h["command"]
            for block in settings["hooks"]["UserPromptSubmit"]
            for h in block["hooks"]
        ]
        assert any("feedback_check.py" in c for c in commands)

    def test_writes_session_evidence_hook(self, project):
        write_claude_bridge(project)
        hook = project / ".claude" / "hooks" / "session_evidence.py"
        body = hook.read_text()
        assert body.startswith("#!/usr/bin/env python3")
        assert "all-might generated" in body
        # Mirror-of relationship is documented in the header.
        assert "session-evidence.ts" in body
        assert ".allmight/feedback/" in body
        mode = hook.stat().st_mode
        assert mode & stat.S_IXUSR

    def test_writes_settings_json_with_post_tool_use(self, project):
        """Session-evidence hook is registered on PostToolUse."""
        write_claude_bridge(project)
        settings = json.loads(
            (project / ".claude" / "settings.json").read_text()
        )
        commands = [
            h["command"]
            for block in settings["hooks"]["PostToolUse"]
            for h in block["hooks"]
        ]
        assert any("session_evidence.py" in c for c in commands)

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
        commands = [
            h["command"]
            for block in merged_twice["hooks"]["SessionStart"]
            for h in block["hooks"]
        ]
        assert sum("memory_load.py" in c for c in commands) == 1
        assert sum("role_load.py" in c for c in commands) == 1
        assert "PreCompact" not in merged_twice["hooks"]


class TestRetiredEvents:
    """Retiring an event must clean up projects already carrying it.

    _merge_hook_config only strips our commands from events it still
    owns. Without _LEGACY_HOOK_EVENTS, dropping PreCompact from
    _settings_payload() would strand our registration in every project
    initialised while we still owned it — and a dangling registration
    is the OMO failure cascade CLAUDE.md warns about (missing script ->
    stderr fed back as the next user prompt).
    """

    def _stale_settings(self):
        """A settings.json as written by a pre-fix All-Might."""
        reload_block = [{"hooks": [
            {"type": "command", "command": _hook_command("memory_load.py")},
            {"type": "command", "command": _hook_command("role_load.py")},
        ]}]
        return {"hooks": {
            "SessionStart": [dict(b) for b in reload_block],
            "PreCompact": [dict(b) for b in reload_block],
        }}

    def test_reinit_strips_our_stale_precompact_entries(self):
        merged = _merge_hook_config(self._stale_settings(), _settings_payload())
        # Nothing of ours left under the retired event; the key itself
        # goes rather than lingering as an empty list.
        assert "PreCompact" not in merged["hooks"]
        # And the live event still carries exactly one of each.
        commands = [
            h["command"]
            for block in merged["hooks"]["SessionStart"]
            for h in block["hooks"]
        ]
        assert sum("memory_load.py" in c for c in commands) == 1
        assert sum("role_load.py" in c for c in commands) == 1

    def test_reinit_preserves_user_authored_precompact_hooks(self):
        """We remove only our own commands — never the user's."""
        stale = self._stale_settings()
        stale["hooks"]["PreCompact"].append(
            {"hooks": [{"type": "command", "command": "echo my-precompact"}]}
        )
        merged = _merge_hook_config(stale, _settings_payload())
        commands = [
            h["command"]
            for block in merged["hooks"]["PreCompact"]
            for h in block["hooks"]
        ]
        assert commands == ["echo my-precompact"]
        assert not any("role_load.py" in c for c in commands)

    def test_cleanup_is_idempotent(self):
        once = _merge_hook_config(self._stale_settings(), _settings_payload())
        twice = _merge_hook_config(once, _settings_payload())
        assert "PreCompact" not in twice["hooks"]


class TestHooksRunCleanly:
    """End-to-end: the generated hook scripts produce valid JSON."""

    def test_role_load_hook_writes_plain_stdout(self, project, tmp_path):
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
        ctx = result.stdout
        assert "Role: demo (ROLE.md)" in ctx
        assert "body" in ctx
        # Negative: must NOT be the JSON envelope any more.
        assert "hookSpecificOutput" not in ctx

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

    def test_feedback_check_hook_writes_plain_stdout(self, project):
        """End-to-end: the feedback-check hook prints plain text."""
        write_claude_bridge(project)
        hook = project / ".claude" / "hooks" / "feedback_check.py"

        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(project)
        result = subprocess.run(
            [sys.executable, str(hook)],
            input='{"hook_event_name": "UserPromptSubmit"}',
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr
        ctx = result.stdout
        assert "Feedback Check" in ctx
        assert "[user-correction]" in ctx
        assert "hookSpecificOutput" not in ctx

    def test_feedback_check_hook_needs_no_stdin(self, project):
        """No stdin (TTY-style invocation) still emits the prompt."""
        write_claude_bridge(project)
        hook = project / ".claude" / "hooks" / "feedback_check.py"

        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(project)
        result = subprocess.run(
            [sys.executable, str(hook)],
            input="",
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr
        assert "Feedback Check" in result.stdout
        assert "hookSpecificOutput" not in result.stdout


class TestHeartbeatWiring:
    """Each generated hook writes a heartbeat marker when invoked.

    This is the touch-file observability contract — without it,
    ``allmight plugin status`` cannot tell whether a hook ever fired.
    """

    def _run(self, project, hook_name: str, event_name: str) -> None:
        write_claude_bridge(project)
        hook = project / ".claude" / "hooks" / hook_name
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(project)
        result = subprocess.run(
            [sys.executable, str(hook)],
            input=json.dumps({"hook_event_name": event_name}),
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr

    def test_feedback_check_writes_heartbeat(self, project):
        self._run(project, "feedback_check.py", "UserPromptSubmit")
        marker = (
            project / ".allmight" / "plugins" / "heartbeats" / "cc" / "feedback_check"
        )
        assert marker.is_file()

    def test_role_load_writes_heartbeat(self, project):
        # role-load fires even with no personalities (the heartbeat is
        # before the early-return, by design).
        self._run(project, "role_load.py", "SessionStart")
        marker = (
            project / ".allmight" / "plugins" / "heartbeats" / "cc" / "role_load"
        )
        assert marker.is_file()


class TestLegacyHookCleanup:
    """Renaming a bridge hook must not leave the old name dangling.

    The 2026-06 rename (reflection.py -> feedback_check.py) is the
    first to exercise this: a dangling settings.json registration
    pointing at a deleted script is the OMO "stderr fed back as next
    user prompt" cascade, so the bridge strips legacy commands
    (removal-only) and deletes the marker'd legacy script.
    """

    def test_legacy_settings_entry_is_stripped(self, project):
        settings = project / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        legacy_cmd = (
            'python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/reflection.py'
        )
        settings.write_text(json.dumps({
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": legacy_cmd}]},
                ],
            }
        }))
        write_claude_bridge(project)
        body = settings.read_text()
        assert "hooks/reflection.py" not in body
        assert "feedback_check.py" in body

    def test_legacy_markered_script_is_deleted(self, project):
        hooks_dir = project / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        legacy = hooks_dir / "reflection.py"
        legacy.write_text("#!/usr/bin/env python3\n# all-might generated\n")
        write_claude_bridge(project)
        assert not legacy.exists()
        assert (hooks_dir / "feedback_check.py").is_file()

    def test_user_authored_legacy_name_is_preserved(self, project):
        hooks_dir = project / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        legacy = hooks_dir / "reflection.py"
        legacy.write_text("#!/usr/bin/env python3\n# mine, hands off\n")
        write_claude_bridge(project)
        assert legacy.exists()
        assert "mine, hands off" in legacy.read_text()

    def test_legacy_strip_in_non_owned_event_too(self, project):
        """A legacy command parked under an event we don't own is
        still stripped — removal applies everywhere."""
        settings = project / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        legacy_cmd = (
            'python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/reflection.py'
        )
        settings.write_text(json.dumps({
            "hooks": {
                "Notification": [
                    {"hooks": [{"type": "command", "command": legacy_cmd}]},
                ],
            }
        }))
        write_claude_bridge(project)
        data = json.loads(settings.read_text())
        assert data["hooks"].get("Notification", []) == []


class TestInjectedHeartbeats:
    """T2 markers: hooks touch ``<stem>.injected`` only on the
    delivery path, so ``plugin status`` can tell "handler ran" apart
    from "content actually reached the model"."""

    def _run(self, project, script, event):
        hook = project / ".claude" / "hooks" / script
        proc = subprocess.run(
            [sys.executable, str(hook)],
            input=json.dumps({"hook_event_name": event}),
            capture_output=True, text=True,
            cwd=project,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        )
        assert proc.returncode == 0, proc.stderr
        return proc

    def test_feedback_check_emits_injected(self, project):
        write_claude_bridge(project)
        self._run(project, "feedback_check.py", "UserPromptSubmit")
        hb = project / ".allmight" / "plugins" / "heartbeats" / "cc"
        assert (hb / "feedback_check").is_file()
        assert (hb / "feedback_check.injected").is_file()

    def _run_payload(self, project, script, payload):
        hook = project / ".claude" / "hooks" / script
        proc = subprocess.run(
            [sys.executable, str(hook)],
            input=json.dumps(payload),
            capture_output=True, text=True,
            cwd=project,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        )
        assert proc.returncode == 0, proc.stderr
        return proc

    def test_session_evidence_records_tool_error(self, project):
        """An explicit error marker in tool_response produces one JSONL
        record and the T2 heartbeat; stdout stays empty (transparent)."""
        write_claude_bridge(project)
        proc = self._run_payload(project, "session_evidence.py", {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "session_id": "s1",
            "tool_response": {"is_error": True, "error": "boom: exit 1"},
        })
        assert proc.stdout.strip() == ""
        feedback = project / ".allmight" / "feedback"
        files = list(feedback.glob("auto-*.jsonl"))
        assert len(files) == 1
        record = json.loads(files[0].read_text().splitlines()[0])
        assert record["tool"] == "Bash"
        assert "boom" in record["error"]
        hb = project / ".allmight" / "plugins" / "heartbeats" / "cc"
        assert (hb / "session_evidence").is_file()
        assert (hb / "session_evidence.injected").is_file()

    def test_session_evidence_silent_on_clean_response(self, project):
        """No error marker -> no record, no T2 (T1 still fires)."""
        write_claude_bridge(project)
        self._run_payload(project, "session_evidence.py", {
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_response": {"output": "file contents"},
        })
        feedback = project / ".allmight" / "feedback"
        assert not list(feedback.glob("auto-*.jsonl")) if feedback.exists() else True
        hb = project / ".allmight" / "plugins" / "heartbeats" / "cc"
        assert (hb / "session_evidence").is_file()
        assert not (hb / "session_evidence.injected").exists()

    def test_role_load_skips_injected_when_nothing_to_say(self, project):
        write_claude_bridge(project)
        self._run(project, "role_load.py", "SessionStart")
        hb = project / ".allmight" / "plugins" / "heartbeats" / "cc"
        assert (hb / "role_load").is_file()
        # No personalities/ -> no output -> no .injected marker.
        assert not (hb / "role_load.injected").exists()

    def test_role_load_emits_injected_with_personality(self, project):
        role = project / "personalities" / "tester"
        role.mkdir(parents=True)
        (role / "ROLE.md").write_text("# Tester role\n")
        write_claude_bridge(project)
        self._run(project, "role_load.py", "SessionStart")
        hb = project / ".allmight" / "plugins" / "heartbeats" / "cc"
        assert (hb / "role_load.injected").is_file()
