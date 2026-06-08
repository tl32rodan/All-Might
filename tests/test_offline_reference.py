"""Offline-reference harness hook (Framework B, slice 3).

A dual-platform session injector telling the air-gapped agent that
``web_search`` / ``context7`` are unavailable and to use the
``project_knowledge_search`` / ``memory_recall`` MCP tools instead.
Modelled on the verified ``reflection`` injector.

Pins: presence on both surfaces, the single-source notice (rule 3),
the exact OpenCode hook shape (+ a negative assertion), the Claude
UserPromptSubmit shape and its settings.json registration, and that
the generated Python hook runs and emits valid JSON.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from allmight.core.claude_bridge import write_claude_bridge
from allmight.core.personalities import (
    OFFLINE_REFERENCE_NOTICE,
    write_init_scaffold,
)


@pytest.fixture
def scaffolded(tmp_path: Path) -> Path:
    write_init_scaffold(tmp_path)
    return tmp_path


class TestNoticeIsSingleSource:
    def test_notice_names_the_substitution(self) -> None:
        assert "web_search" in OFFLINE_REFERENCE_NOTICE
        assert "context7" in OFFLINE_REFERENCE_NOTICE
        assert "project_knowledge_search" in OFFLINE_REFERENCE_NOTICE
        assert "memory_recall" in OFFLINE_REFERENCE_NOTICE
        assert "fabricate" in OFFLINE_REFERENCE_NOTICE.lower()


class TestOpenCodePlugin:
    def test_plugin_written(self, scaffolded: Path) -> None:
        assert (scaffolded / ".opencode" / "plugins" / "offline-reference.ts").is_file()

    def test_plugin_shape(self, scaffolded: Path) -> None:
        body = (scaffolded / ".opencode" / "plugins" / "offline-reference.ts").read_text()
        # Hook registration (not the event bus), correct injection path.
        assert '"chat.message": async (input: any, output: any)' in body
        assert "output.parts.unshift" in body
        assert 'emitHeartbeat("offline-reference", cwd)' in body
        # Notice text made it into the backtick string.
        assert "project_knowledge_search" in body
        assert "context7" in body
        # Negative: not the broken direct-mutation shape.
        assert "msg.content =" not in body


class TestClaudeHook:
    def test_hook_written_and_executable(self, scaffolded: Path) -> None:
        hook = scaffolded / ".claude" / "hooks" / "offline_reference.py"
        assert hook.is_file()
        assert hook.stat().st_mode & 0o111  # executable bit

    def test_hook_shape(self, scaffolded: Path) -> None:
        body = (scaffolded / ".claude" / "hooks" / "offline_reference.py").read_text()
        assert "UserPromptSubmit" in body
        assert "additionalContext" in body
        assert '_hb("offline_reference")' in body
        assert "project_knowledge_search" in body

    def test_registered_in_settings_under_user_prompt(self, scaffolded: Path) -> None:
        settings = json.loads((scaffolded / ".claude" / "settings.json").read_text())
        cmds = [
            h["command"]
            for block in settings["hooks"]["UserPromptSubmit"]
            for h in block["hooks"]
        ]
        assert any("offline_reference.py" in c for c in cmds)

    def test_hook_runs_and_emits_valid_json(self, scaffolded: Path) -> None:
        hook = scaffolded / ".claude" / "hooks" / "offline_reference.py"
        proc = subprocess.run(
            [sys.executable, str(hook)],
            input="{}",
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "project_knowledge_search" in ctx


class TestBothSurfacesAgree:
    def test_same_notice_text_on_both(self, scaffolded: Path) -> None:
        ts = (scaffolded / ".opencode" / "plugins" / "offline-reference.ts").read_text()
        py = (scaffolded / ".claude" / "hooks" / "offline_reference.py").read_text()
        # A distinctive sentence fragment from the single-source notice
        # appears verbatim in both generated files.
        fragment = "do NOT"
        assert fragment in OFFLINE_REFERENCE_NOTICE
        assert fragment in ts
        assert fragment in py
