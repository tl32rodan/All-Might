"""Tests for All-Might CLI commands.

The CLI is a thin bootstrapping surface.  Only ``init``, ``power-level``,
and ``config`` subcommands exist.  Everything else is agent-driven via skills.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from allmight.cli import main


class TestCliInit(unittest.TestCase):
    """Test the 'init' command."""

    def test_init_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Detroit SMAK", result.output)


class TestCliHelp(unittest.TestCase):
    """Test that only bootstrapping commands appear in help."""

    def test_bootstrapping_commands_present(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        self.assertEqual(result.exit_code, 0)
        for cmd in ["init", "power-level", "config"]:
            self.assertIn(cmd, result.output, f"Command '{cmd}' missing from help")

    def test_agent_driven_commands_removed(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        self.assertEqual(result.exit_code, 0)
        for cmd in ["generate", "search", "lookup", "enrich",
                     "ingest", "explain", "report", "panorama"]:
            self.assertNotIn(cmd, result.output,
                             f"Command '{cmd}' should be agent-driven, not in CLI")


class TestCliConfigGroup(unittest.TestCase):
    """Test the 'config' subcommand group."""

    def _setup_project(self, tmp_dir: str) -> Path:
        root = Path(tmp_dir)
        (root / "all-might").mkdir()
        config = {"indices": [{"name": "src", "description": "Source", "paths": ["./src"]}]}
        with open(root / "workspace_config.yaml", "w") as f:
            yaml.dump(config, f)
        am_config = {"project": {"name": "test"}}
        with open(root / "all-might" / "config.yaml", "w") as f:
            yaml.dump(am_config, f)
        return root

    def test_list_indices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            runner = CliRunner()
            result = runner.invoke(main, ["config", "list-indices", "--root", str(root)])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("src", result.output)

    def test_list_indices_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            runner = CliRunner()
            result = runner.invoke(main, ["config", "list-indices", "--root", str(root), "--json"])
            self.assertEqual(result.exit_code, 0)
            data = json.loads(result.output)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["name"], "src")

    def test_add_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            runner = CliRunner()
            result = runner.invoke(main, [
                "config", "add-index",
                "--name", "tests", "--description", "Test files",
                "--paths", "./tests", "--root", str(root),
            ])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Added index 'tests'", result.output)

    def test_remove_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            runner = CliRunner()
            runner.invoke(main, [
                "config", "add-index",
                "--name", "tests", "--description", "Tests",
                "--paths", "./tests", "--root", str(root),
            ])
            result = runner.invoke(main, [
                "config", "remove-index", "--name", "tests", "--root", str(root),
            ])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Removed", result.output)

    def test_update_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            runner = CliRunner()
            result = runner.invoke(main, [
                "config", "update-index",
                "--name", "src", "--description", "Updated source",
                "--root", str(root),
            ])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Updated index 'src'", result.output)

    def test_config_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["config", "--help"])
        self.assertEqual(result.exit_code, 0)
        for subcmd in ["add-index", "remove-index", "list-indices", "update-index"]:
            self.assertIn(subcmd, result.output)


if __name__ == "__main__":
    unittest.main()
