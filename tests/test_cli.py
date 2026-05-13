"""Tests for the All-Might CLI — bootstrapping only."""

import unittest

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


class TestCliWritableFlag(unittest.TestCase):
    """--writable flag on init command."""

    def test_writable_flag_in_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--writable", result.output)

    def test_init_readonly_default_message(self) -> None:
        """Default init (read-only) labels the project read-only and points
        the user at /onboard. Detailed command suggestions live inside
        /onboard now, not the CLI tail.
        """
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "src"))
            with open(os.path.join(td, "src", "main.py"), "w") as f:
                f.write("def hello(): pass\n")

            runner = CliRunner()
            result = runner.invoke(main, ["init", td])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("read-only", result.output)
            self.assertIn("/onboard", result.output)

    def test_init_writable_message(self) -> None:
        """Writable init labels the project writable and points the user at /onboard."""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "src"))
            with open(os.path.join(td, "src", "main.py"), "w") as f:
                f.write("def hello(): pass\n")

            runner = CliRunner()
            result = runner.invoke(main, ["init", "--writable", td])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("writable", result.output)
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
            # Every registered plugin / hook is enumerated, even
            # without a heartbeat — that's the whole point of the
            # "never fired" line.
            for name in (
                "role-load", "reflection", "memory-load", "memory-history",
                "remember-trigger", "todo-curator", "trajectory-writer",
                "usage-logger",
            ):
                self.assertIn(name, result.output)
            for name in (
                "role_load", "reflection", "memory_load", "memory_history",
            ):
                self.assertIn(name, result.output)
            self.assertIn("never fired", result.output)

    def test_status_shows_recent_fire(self) -> None:
        from pathlib import Path

        from allmight.core.plugin_telemetry import emit_heartbeat

        runner = CliRunner()
        with runner.isolated_filesystem():
            emit_heartbeat("reflection", "cc", root=Path("."))
            result = runner.invoke(main, ["plugin", "status", "."])
            self.assertEqual(result.exit_code, 0, result.output)
            # The reflection row should show a recent fire, not
            # "never fired".
            for line in result.output.splitlines():
                if line.strip().startswith("reflection") and "fired" in line:
                    # cc/reflection or oc/reflection — both rows exist
                    # but at least one should show a recent fire.
                    if "never" not in line:
                        break
            else:  # pragma: no cover - guard against silent regression
                self.fail(
                    "expected at least one 'reflection' row to show a "
                    f"recent fire; got:\n{result.output}"
                )
