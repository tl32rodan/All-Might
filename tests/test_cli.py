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


class TestCliMemoryGroup(unittest.TestCase):
    def test_memory_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["memory", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("init", result.output)
