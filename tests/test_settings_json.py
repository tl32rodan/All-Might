"""Tests for the marker-bounded .claude/settings.json hook writer.

The writer must:
- Register Stop + UserPromptSubmit hooks for All-Might's scripts.
- Be idempotent — re-running produces the same file.
- Preserve unrelated user-authored entries (both in `hooks` and at the
  top level).
- Use a sentinel flag on each managed entry so future upgrades replace
  only the All-Might-owned hooks, not the user's.
"""

from __future__ import annotations

import json

from allmight.memory.settings_json import merge_hooks


ALLMIGHT_HOOKS = {
    "Stop": [
        {"command": "./.claude/hooks/memory-cap.sh"},
        {"command": "./.claude/hooks/memory-nudge.sh"},
    ],
    "UserPromptSubmit": [
        {"command": "./.claude/hooks/memory-load.sh"},
    ],
}


class TestMergeHooksFreshFile:

    def test_creates_settings_json_when_absent(self, tmp_path):
        settings = tmp_path / ".claude" / "settings.json"
        merge_hooks(settings, ALLMIGHT_HOOKS)
        assert settings.exists()
        data = json.loads(settings.read_text())
        assert "hooks" in data

    def test_registers_all_three_hooks(self, tmp_path):
        settings = tmp_path / ".claude" / "settings.json"
        merge_hooks(settings, ALLMIGHT_HOOKS)

        data = json.loads(settings.read_text())
        stop_cmds = [h["command"] for h in data["hooks"]["Stop"]]
        ups_cmds = [h["command"] for h in data["hooks"]["UserPromptSubmit"]]
        assert "./.claude/hooks/memory-cap.sh" in stop_cmds
        assert "./.claude/hooks/memory-nudge.sh" in stop_cmds
        assert "./.claude/hooks/memory-load.sh" in ups_cmds

    def test_marks_each_managed_entry_with_sentinel(self, tmp_path):
        """Every All-Might entry carries the `_allmight_managed: true` flag."""
        settings = tmp_path / ".claude" / "settings.json"
        merge_hooks(settings, ALLMIGHT_HOOKS)

        data = json.loads(settings.read_text())
        for event_hooks in data["hooks"].values():
            for entry in event_hooks:
                assert entry.get("_allmight_managed") is True


class TestMergeHooksIdempotent:

    def test_two_runs_produce_identical_file(self, tmp_path):
        settings = tmp_path / ".claude" / "settings.json"
        merge_hooks(settings, ALLMIGHT_HOOKS)
        first = settings.read_text()

        merge_hooks(settings, ALLMIGHT_HOOKS)
        second = settings.read_text()

        assert first == second

    def test_second_run_does_not_duplicate_entries(self, tmp_path):
        settings = tmp_path / ".claude" / "settings.json"
        merge_hooks(settings, ALLMIGHT_HOOKS)
        merge_hooks(settings, ALLMIGHT_HOOKS)

        data = json.loads(settings.read_text())
        stop_cmds = [h["command"] for h in data["hooks"]["Stop"]]
        # Each command appears exactly once.
        assert stop_cmds.count("./.claude/hooks/memory-cap.sh") == 1
        assert stop_cmds.count("./.claude/hooks/memory-nudge.sh") == 1


class TestMergeHooksPreservesUser:

    def test_preserves_user_authored_hook_entries(self, tmp_path):
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({
            "hooks": {
                "Stop": [
                    {"command": "./my-user-hook.sh"},  # no _allmight_managed
                ],
            },
        }))

        merge_hooks(settings, ALLMIGHT_HOOKS)

        data = json.loads(settings.read_text())
        stop_cmds = [h["command"] for h in data["hooks"]["Stop"]]
        assert "./my-user-hook.sh" in stop_cmds
        assert "./.claude/hooks/memory-cap.sh" in stop_cmds

    def test_preserves_unrelated_top_level_keys(self, tmp_path):
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({
            "permissions": {"allow": ["Bash(ls:*)"]},
            "model": "claude-opus-4-7",
        }))

        merge_hooks(settings, ALLMIGHT_HOOKS)

        data = json.loads(settings.read_text())
        assert data["permissions"]["allow"] == ["Bash(ls:*)"]
        assert data["model"] == "claude-opus-4-7"

    def test_upgrade_replaces_only_managed_entries(self, tmp_path):
        """If a prior All-Might release registered an outdated hook, the
        re-run must drop the old managed entry and leave user entries alone."""
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({
            "hooks": {
                "Stop": [
                    {"command": "./.claude/hooks/old-legacy.sh",
                     "_allmight_managed": True},
                    {"command": "./my-user-hook.sh"},  # user-owned
                ],
            },
        }))

        merge_hooks(settings, ALLMIGHT_HOOKS)

        data = json.loads(settings.read_text())
        stop_cmds = [h["command"] for h in data["hooks"]["Stop"]]
        assert "./.claude/hooks/old-legacy.sh" not in stop_cmds  # dropped
        assert "./my-user-hook.sh" in stop_cmds  # kept
        assert "./.claude/hooks/memory-cap.sh" in stop_cmds  # new


class TestMergeHooksMalformedInput:

    def test_tolerates_unparseable_settings_json(self, tmp_path):
        """A corrupt settings.json should not crash init — treat as empty."""
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text("not valid json {{{")

        merge_hooks(settings, ALLMIGHT_HOOKS)

        data = json.loads(settings.read_text())
        stop_cmds = [h["command"] for h in data["hooks"]["Stop"]]
        assert "./.claude/hooks/memory-cap.sh" in stop_cmds
