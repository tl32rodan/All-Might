"""Tests for the All-Might CLI — bootstrapping only."""

import unittest
from pathlib import Path

from click.testing import CliRunner

from allmight.cli import main


class TestCliInit(unittest.TestCase):
    def test_init_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Bootstrap", result.output)


class TestCliHelp(unittest.TestCase):
    """Test that the CLI is minimal — only bootstrapping commands."""

    def test_bootstrapping_commands_present(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("init", result.output)
        self.assertIn("memory", result.output)

    def test_no_wrapper_commands(self) -> None:
        """CLI should NOT have search/enrich/power-level wrappers."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        self.assertNotIn("power-level", result.output)
        self.assertNotIn("config", result.output)


class TestCliInitMessages(unittest.TestCase):
    """``allmight init`` summary message after a fresh init."""

    def test_no_writable_flag(self) -> None:
        """The retired ``--writable`` flag must not be advertised."""
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("--writable", result.output)

    def test_init_points_user_at_onboard(self) -> None:
        """Fresh init points the user at /onboard."""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "src"))
            with open(os.path.join(td, "src", "main.py"), "w") as f:
                f.write("def hello(): pass\n")

            runner = CliRunner()
            result = runner.invoke(main, ["init", td])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("/onboard", result.output)


class TestCliCloneCommand(unittest.TestCase):
    """clone subcommand present in CLI."""

    def test_clone_in_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("clone", result.output)

    def test_clone_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["clone", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("read-only", result.output.lower())


class TestCliMemoryGroup(unittest.TestCase):
    def test_memory_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["memory", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("init", result.output)


class TestCliPluginStatus(unittest.TestCase):
    """`allmight plugin status` is the read-side of plugin observability.

    The contract: every known plugin / hook is listed (so users see
    "never fired" entries explicitly), and fired ones show a relative
    age.
    """

    def test_plugin_help_lists_status(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["plugin", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("status", result.output)

    def test_status_lists_all_known_plugins_when_empty(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["plugin", "status", "."])
            self.assertEqual(result.exit_code, 0, result.output)
            # Every registered plugin is enumerated under both
            # surfaces (OC fires + CC mirror status). Capability
            # Manifest (work item A') made the CC section list
            # plugins by their canonical name rather than the
            # legacy Python file name — every plugin gets a row
            # regardless of whether it has a mirror.
            for name in (
                "role-load", "feedback-check", "memory-load", "memory-history",
                "remember-trigger", "todo-curator",
            ):
                self.assertIn(name, result.output)
            # OC plugins that have a mirror show "never fired" on
            # the CC side when no heartbeat exists; OC-only plugins
            # show "unavailable (requires: ...)" instead — see
            # tests/test_capability_manifest.py for the precise
            # contract.
            self.assertIn("never fired", result.output)
            self.assertIn("unavailable (requires:", result.output)

    def test_status_shows_recent_fire(self) -> None:
        from pathlib import Path

        from allmight.core.plugin_telemetry import emit_heartbeat

        runner = CliRunner()
        with runner.isolated_filesystem():
            emit_heartbeat("feedback_check", "cc", root=Path("."))
            result = runner.invoke(main, ["plugin", "status", "."])
            self.assertEqual(result.exit_code, 0, result.output)
            # The reflection row should show a recent fire, not
            # "never fired".
            for line in result.output.splitlines():
                if line.strip().startswith("feedback-check") and "fired" in line:
                    # cc/feedback_check or oc/feedback-check — both rows exist
                    # but at least one should show a recent fire.
                    if "never" not in line:
                        break
            else:  # pragma: no cover - guard against silent regression
                self.fail(
                    "expected at least one 'feedback-check' row to show a "
                    f"recent fire; got:\n{result.output}"
                )


class TestInitPrunesStalePlugins(unittest.TestCase):
    """Re-init sweeps marker'd plugins the framework no longer ships.

    Deleting (or renaming) a plugin in the framework must not leave
    the old generated ``.ts`` behind in deployed projects — stale
    files keep firing inside OpenCode forever. ``prune_stale_plugins``
    is marker-gated so user-authored plugins are never touched.
    """

    def test_reinit_prunes_markered_unknown_plugins(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["init", ".", "--yes"])
            self.assertEqual(result.exit_code, 0, result.output)
            plugins = Path(".opencode/plugins")
            (plugins / "trajectory-writer.ts").write_text(
                "// all-might generated\nexport default {}\n"
            )
            (plugins / "usage-logger.ts").write_text(
                "// all-might generated\nexport default {}\n"
            )
            (plugins / "mine.ts").write_text(
                "// my own plugin, hands off\nexport default {}\n"
            )
            result = runner.invoke(main, ["init", ".", "--yes"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertFalse((plugins / "trajectory-writer.ts").exists())
            self.assertFalse((plugins / "usage-logger.ts").exists())
            self.assertTrue((plugins / "mine.ts").exists())
            self.assertIn("Pruned", result.output)

    def test_prune_never_touches_current_plugins(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(main, ["init", ".", "--yes"])
            result = runner.invoke(main, ["init", ".", "--yes"])
            self.assertEqual(result.exit_code, 0, result.output)
            plugins = Path(".opencode/plugins")
            for name in (
                "memory-load.ts", "memory-history.ts",
                "remember-trigger.ts", "todo-curator.ts",
                "role-load.ts",
            ):
                self.assertTrue((plugins / name).exists(), name)

    def test_prune_sweeps_stale_staged_templates(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(main, ["init", ".", "--yes"])
            staged = Path(".allmight/templates")
            staged.mkdir(parents=True, exist_ok=True)
            (staged / "usage-logger.ts").write_text(
                "// all-might generated\nexport default {}\n"
            )
            result = runner.invoke(main, ["init", ".", "--yes"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertFalse((staged / "usage-logger.ts").exists())


class TestPluginStatusV2(unittest.TestCase):
    """Two-column status (fired/injected) + the T3 outcomes footer."""

    def test_status_renders_injected_column(self) -> None:
        from allmight.core.plugin_telemetry import emit_heartbeat

        runner = CliRunner()
        with runner.isolated_filesystem():
            emit_heartbeat("memory-load", "oc", root=Path("."))
            emit_heartbeat("memory-load.injected", "oc", root=Path("."))
            result = runner.invoke(main, ["plugin", "status", "."])
            self.assertEqual(result.exit_code, 0, result.output)
            row = next(
                line for line in result.output.splitlines()
                if line.strip().startswith("memory-load ")
            )
            self.assertIn("fired", row)
            self.assertIn("injected", row)
            # The .injected marker is a column, not a plugin row.
            self.assertNotIn("memory-load.injected", result.output)
            self.assertNotIn("(unregistered)", result.output)

    def test_status_shows_dash_when_never_injected(self) -> None:
        from allmight.core.plugin_telemetry import emit_heartbeat

        runner = CliRunner()
        with runner.isolated_filesystem():
            emit_heartbeat("remember-trigger", "oc", root=Path("."))
            result = runner.invoke(main, ["plugin", "status", "."])
            row = next(
                line for line in result.output.splitlines()
                if line.strip().startswith("remember-trigger")
            )
            self.assertIn("fired", row)
            self.assertIn("—", row)

    def test_status_outcome_footer(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["init", ".", "--yes"])
            self.assertEqual(result.exit_code, 0, result.output)
            result = runner.invoke(main, ["plugin", "status", "."])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Outcomes:", result.output)
            self.assertIn("memory-history commits:", result.output)
            self.assertIn("journal entries (L3):", result.output)
            self.assertIn("MEMORY.md placeholders:", result.output)
            # Fresh project: L1 still carries its placeholders.
            self.assertIn("yes — L1 has never been rewritten", result.output)

    def test_status_footer_flags_missing_mirror(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["plugin", "status", "."])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("mirror not initialised", result.output)


class TestSnapshotInjectedHeartbeat(unittest.TestCase):
    """``memory snapshot`` emits the memory-history T2 marker on the
    surface matching ``--trigger`` — but only when a commit landed."""

    def test_stop_hook_trigger_emits_cc_marker(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(main, ["init", ".", "--yes"])
            Path("MEMORY.md").write_text(
                Path("MEMORY.md").read_text() + "\n- fact one\n"
            )
            result = runner.invoke(
                main, ["memory", "snapshot", "--trigger=stop-hook"],
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Snapshot:", result.output)
            self.assertTrue(
                Path(".allmight/plugins/heartbeats/cc/memory_history.injected").is_file()
            )

    def test_chat_message_trigger_emits_oc_marker(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(main, ["init", ".", "--yes"])
            Path("MEMORY.md").write_text(
                Path("MEMORY.md").read_text() + "\n- fact two\n"
            )
            result = runner.invoke(
                main, ["memory", "snapshot", "--trigger=chat-message"],
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue(
                Path(".allmight/plugins/heartbeats/oc/memory-history.injected").is_file()
            )

    def test_no_change_emits_nothing(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(main, ["init", ".", "--yes"])
            # Drain the post-init drift so the next call is a no-op.
            runner.invoke(main, ["memory", "snapshot", "--trigger=manual"])
            result = runner.invoke(
                main, ["memory", "snapshot", "--trigger=stop-hook"],
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("No changes to snapshot.", result.output)
            self.assertFalse(
                Path(".allmight/plugins/heartbeats/cc/memory_history.injected").exists()
            )
