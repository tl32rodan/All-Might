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
        """Default init (read-only) should NOT mention /ingest or /enrich."""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as td:
            # Create minimal project
            os.makedirs(os.path.join(td, "src"))
            with open(os.path.join(td, "src", "main.py"), "w") as f:
                f.write("def hello(): pass\n")

            runner = CliRunner()
            result = runner.invoke(main, ["init", td])
            self.assertEqual(result.exit_code, 0)
            self.assertNotIn("/ingest", result.output)
            self.assertNotIn("/enrich", result.output)
            self.assertIn("/search", result.output)

    def test_init_writable_message(self) -> None:
        """Writable init should mention /ingest and /enrich."""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "src"))
            with open(os.path.join(td, "src", "main.py"), "w") as f:
                f.write("def hello(): pass\n")

            runner = CliRunner()
            result = runner.invoke(main, ["init", "--writable", td])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("/ingest", result.output)
            self.assertIn("/enrich", result.output)


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
