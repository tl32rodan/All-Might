"""Tests for the Reminder Layer (throttled nudge + skills log).

Two runtimes share the same canonical nudge text:
- OpenCode: `.opencode/plugins/remember-trigger.ts` (in-memory Map throttle).
- Claude Code: `.claude/hooks/memory-nudge.sh` (per-session counter file).

Per-session state isolates parallel sessions; no shared mutable
counter file exists.
"""

from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path

from allmight.memory.initializer import MemoryInitializer


# --------------------------------------------------------------------- helpers

def _init(tmp_path: Path) -> Path:
    MemoryInitializer().initialize(tmp_path)
    return tmp_path


def _run_nudge(tmp_path: Path, session_id: str) -> subprocess.CompletedProcess:
    script = tmp_path / ".claude" / "hooks" / "memory-nudge.sh"
    stdin = json.dumps({"cwd": str(tmp_path), "session_id": session_id})
    return subprocess.run(
        ["bash", str(script)],
        input=stdin,
        capture_output=True,
        text=True,
    )


# --------------------------------------------------------------------- shared text

class TestSharedNudgeText:

    def test_nudge_text_helper_returns_skills_log_line(self):
        from allmight.memory.initializer import _reminder_nudge_text
        text = _reminder_nudge_text()
        assert "memory/skills-log.md" in text

    def test_nudge_text_helper_mentions_scope_reminder(self):
        from allmight.memory.initializer import _reminder_nudge_text
        text = _reminder_nudge_text()
        assert "MEMORY.md" in text
        assert "memory/understanding" in text

    def test_opencode_plugin_uses_shared_nudge_text(self, tmp_path):
        _init(tmp_path)
        content = (tmp_path / ".opencode" / "plugins"
                   / "remember-trigger.ts").read_text()
        assert "memory/skills-log.md" in content

    def test_shell_nudge_uses_shared_nudge_text(self, tmp_path):
        _init(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "memory-nudge.sh").read_text()
        assert "memory/skills-log.md" in content


# --------------------------------------------------------------------- Claude throttle

class TestNudgeShellThrottle:

    def test_reads_session_id_from_stdin(self, tmp_path):
        _init(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "memory-nudge.sh").read_text()
        assert "session_id" in content

    def test_uses_per_session_counter_path(self, tmp_path):
        _init(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "memory-nudge.sh").read_text()
        # Counter file must include session id in its name.
        assert ".nudge-counter-" in content or "nudge-counter-$" in content

    def test_nudge_silent_on_first_invocations(self, tmp_path):
        _init(tmp_path)
        for _ in range(4):
            result = _run_nudge(tmp_path, "session-A")
            assert result.returncode == 0, result.stderr
            assert "memory/skills-log.md" not in result.stdout

    def test_nudge_fires_on_fifth_invocation(self, tmp_path):
        _init(tmp_path)
        outputs = [_run_nudge(tmp_path, "session-B").stdout for _ in range(5)]
        # Fifth call emits the nudge; earlier calls do not.
        assert "memory/skills-log.md" not in "".join(outputs[:4])
        assert "memory/skills-log.md" in outputs[4]

    def test_counter_file_is_per_session(self, tmp_path):
        _init(tmp_path)
        _run_nudge(tmp_path, "session-X")
        _run_nudge(tmp_path, "session-Y")
        counters = list((tmp_path / "memory").glob(".nudge-counter-*"))
        # Two distinct sessions → two distinct counter files.
        names = {c.name for c in counters}
        assert any("session-X" in n for n in names)
        assert any("session-Y" in n for n in names)


# --------------------------------------------------------------------- settings wiring

class TestSettingsWiring:

    def test_init_writes_claude_settings_json(self, tmp_path):
        _init(tmp_path)
        settings = tmp_path / ".claude" / "settings.json"
        assert settings.exists()

    def test_settings_registers_three_hooks(self, tmp_path):
        _init(tmp_path)
        settings = tmp_path / ".claude" / "settings.json"
        data = json.loads(settings.read_text())

        stop_cmds = [h["command"] for h in data["hooks"]["Stop"]]
        ups_cmds = [h["command"] for h in data["hooks"]["UserPromptSubmit"]]
        assert any("memory-cap.sh" in c for c in stop_cmds)
        assert any("memory-nudge.sh" in c for c in stop_cmds)
        assert any("memory-load.sh" in c for c in ups_cmds)


# --------------------------------------------------------------------- skills log

class TestSkillsLog:

    def test_skills_log_template_created_by_init(self, tmp_path):
        _init(tmp_path)
        assert (tmp_path / "memory" / "skills-log.md").exists()

    def test_skills_log_header_mentions_format(self, tmp_path):
        _init(tmp_path)
        body = (tmp_path / "memory" / "skills-log.md").read_text()
        # Bullet format hint: date + path + reason.
        assert "YYYY-MM-DD" in body or "date" in body.lower()
        assert "path" in body.lower()


# --------------------------------------------------------------------- config

class TestReminderConfig:

    def test_memory_config_has_reminder_every_turns(self):
        from allmight.core.domain import MemoryConfig
        cfg = MemoryConfig()
        assert cfg.reminder_every_turns == 5


# --------------------------------------------------------------------- negatives

class TestNoSharedState:

    def test_no_shared_counter_file_name(self, tmp_path):
        """The shell script must never read/write a session-less counter."""
        _init(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "memory-nudge.sh").read_text()
        # A naked `.nudge-counter` (no session suffix) would be the race.
        assert ".nudge-counter\n" not in content
        assert ".nudge-counter\"" not in content
        assert ".nudge-counter'" not in content

    def test_opencode_session_completed_no_longer_runs_shell_nudge(self, tmp_path):
        """OpenCode's throttle lives in the TS plugin; session_completed
        should no longer wire the shell nudge (which is now Claude-only)."""
        _init(tmp_path)
        opencode_json = tmp_path / ".opencode" / "opencode.json"
        data = json.loads(opencode_json.read_text())
        hook = data.get("experimental", {}).get("hook", {})
        session_completed = hook.get("session_completed", [])
        commands = [
            " ".join(entry.get("command", []))
            for entry in session_completed
        ]
        assert not any("memory-nudge.sh" in c for c in commands)


class TestNudgeScriptExecutable:

    def test_nudge_script_is_executable(self, tmp_path):
        _init(tmp_path)
        script = tmp_path / ".claude" / "hooks" / "memory-nudge.sh"
        assert script.stat().st_mode & stat.S_IXUSR
