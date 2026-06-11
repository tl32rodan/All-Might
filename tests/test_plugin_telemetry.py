"""Tests for the plugin heartbeat helpers.

These pin the touch-file observability contract:

* ``emit_heartbeat`` touches ``.allmight/plugins/heartbeats/<surface>/<name>``
* ``read_heartbeats`` returns the mtimes per surface
* The TS and Python snippet constants both contain the entry points the
  generators reference (``emitHeartbeat`` / ``_hb``)
* ``KNOWN_OPENCODE_PLUGINS`` and ``KNOWN_CLAUDE_HOOKS`` enumerate every
  plugin / hook the generators actually write, so ``plugin status``
  cannot silently miss a new one
"""

from __future__ import annotations

import time

from allmight.core.plugin_telemetry import (
    KNOWN_CLAUDE_HOOKS,
    KNOWN_OPENCODE_PLUGINS,
    PY_HEARTBEAT_SNIPPET,
    SURFACE_CLAUDE,
    SURFACE_OPENCODE,
    TS_HEARTBEAT_SNIPPET,
    emit_heartbeat,
    heartbeats_root,
    read_heartbeats,
)


class TestEmitHeartbeat:

    def test_creates_marker_file_on_first_emit(self, tmp_path):
        emit_heartbeat("reflection", SURFACE_CLAUDE, root=tmp_path)
        marker = heartbeats_root(tmp_path) / SURFACE_CLAUDE / "reflection"
        assert marker.is_file()

    def test_updates_mtime_on_repeat_emit(self, tmp_path):
        emit_heartbeat("memory-load", SURFACE_OPENCODE, root=tmp_path)
        marker = heartbeats_root(tmp_path) / SURFACE_OPENCODE / "memory-load"
        first = marker.stat().st_mtime
        # Force a measurable delta — mtime resolution on some fs is 1s.
        old = first - 10
        import os
        os.utime(marker, (old, old))
        emit_heartbeat("memory-load", SURFACE_OPENCODE, root=tmp_path)
        assert marker.stat().st_mtime > old

    def test_silent_on_failure(self, tmp_path):
        # Force failure by giving an unwritable path. emit_heartbeat must
        # swallow the exception, never raise.
        marker_dir = heartbeats_root(tmp_path) / SURFACE_CLAUDE
        marker_dir.parent.mkdir(parents=True, exist_ok=True)
        # Replace the path that would become the dir with a regular file
        # so mkdir(parents=True) fails. emit_heartbeat must not raise.
        marker_dir.write_text("not a directory")
        # Should not raise.
        emit_heartbeat("anything", SURFACE_CLAUDE, root=tmp_path)


class TestReadHeartbeats:

    def test_empty_project_returns_empty_maps(self, tmp_path):
        data = read_heartbeats(tmp_path)
        assert data == {SURFACE_OPENCODE: {}, SURFACE_CLAUDE: {}}

    def test_round_trip(self, tmp_path):
        before = time.time()
        emit_heartbeat("reflection", SURFACE_CLAUDE, root=tmp_path)
        emit_heartbeat("memory-load", SURFACE_OPENCODE, root=tmp_path)
        after = time.time()
        data = read_heartbeats(tmp_path)
        assert "reflection" in data[SURFACE_CLAUDE]
        assert "memory-load" in data[SURFACE_OPENCODE]
        # mtimes within the window between before/after the emits
        assert before - 1 <= data[SURFACE_CLAUDE]["reflection"] <= after + 1
        assert before - 1 <= data[SURFACE_OPENCODE]["memory-load"] <= after + 1


class TestSnippetContracts:
    """Pin the literal entry points plugin generators rely on."""

    def test_ts_snippet_defines_emit_heartbeat(self):
        # Generators paste this verbatim and call ``emitHeartbeat(...)``;
        # renaming it silently breaks every plugin.
        assert "function emitHeartbeat" in TS_HEARTBEAT_SNIPPET
        # The snippet must write to ``heartbeats/oc`` — the path is part
        # of the contract with read_heartbeats().
        assert '"oc"' in TS_HEARTBEAT_SNIPPET
        # Must be self-contained (provides its own imports under aliased
        # names so it doesn't collide with the host plugin's imports).
        assert "__hb_mkdir" in TS_HEARTBEAT_SNIPPET
        assert "__hb_join" in TS_HEARTBEAT_SNIPPET

    def test_py_snippet_defines_hb(self):
        assert "def _hb(name):" in PY_HEARTBEAT_SNIPPET
        # Writes to the cc surface per the read_heartbeats() contract.
        assert '"cc"' in PY_HEARTBEAT_SNIPPET
        # Honors CLAUDE_PROJECT_DIR so hooks running outside their cwd
        # still find the project root.
        assert "CLAUDE_PROJECT_DIR" in PY_HEARTBEAT_SNIPPET

    def test_known_plugin_list_matches_generators(self):
        """If we add an OpenCode plugin we must register it here too."""
        # Sourced from MemoryInitializer._opencode_plugin_map() + the two
        # project-level plugins in core.personalities.
        expected_memory = {
            "memory-load", "memory-history", "remember-trigger",
            "todo-curator",
        }
        expected_project = {"role-load", "feedback-check", "offline-reference"}
        assert set(KNOWN_OPENCODE_PLUGINS) == expected_memory | expected_project

    def test_known_hook_list_matches_generators(self):
        """If we add a Claude hook we must register it here too."""
        # Sourced from claude_bridge._HOOK_SCRIPTS (basename minus .py).
        expected = {
            "memory_load", "role_load", "memory_history",
            "feedback_check", "offline_reference",
        }
        assert set(KNOWN_CLAUDE_HOOKS) == expected
