"""Tests for All-Might CLI commands."""

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


class TestCliGenerate(unittest.TestCase):
    """Test the 'generate' command."""

    def test_generate_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["generate", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Regenerate One For All", result.output)


class TestCliNewCommands(unittest.TestCase):
    """Test new Phase 7 CLI commands exist in help."""

    def test_all_commands_present(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        self.assertEqual(result.exit_code, 0)
        for cmd in ["init", "generate", "power-level", "panorama",
                     "search", "lookup", "enrich", "ingest",
                     "explain", "report", "config"]:
            self.assertIn(cmd, result.output, f"Command '{cmd}' missing from help")


class TestCliSearch(unittest.TestCase):
    """Test the 'search' command."""

    @patch("allmight.cli._workspace_config", return_value="/tmp/workspace_config.yaml")
    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_search_json(self, mock_run, _mock_ws) -> None:
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"hits": [{"uid": "a::b", "score": 0.9}]})
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        runner = CliRunner()
        result = runner.invoke(main, ["search", "test query", "--json", "--config", "/tmp/all-might/config.yaml"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["hits"][0]["uid"], "a::b")

    @patch("allmight.cli._workspace_config", return_value="/tmp/workspace_config.yaml")
    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_search_pretty(self, mock_run, _mock_ws) -> None:
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"hits": [{"uid": "a::b", "score": 0.9}]})
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        runner = CliRunner()
        result = runner.invoke(main, ["search", "test query", "--config", "/tmp/all-might/config.yaml"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("a::b", result.output)


class TestCliLookup(unittest.TestCase):

    @patch("allmight.cli._workspace_config", return_value="/tmp/workspace_config.yaml")
    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_lookup_found(self, mock_run, _mock_ws) -> None:
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"found": True, "uid": "a::b", "content": "hello"})
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        runner = CliRunner()
        result = runner.invoke(main, ["lookup", "a::b", "--config", "/tmp/all-might/config.yaml"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("a::b", result.output)


class TestCliEnrich(unittest.TestCase):

    @patch("allmight.cli._workspace_config", return_value="/tmp/workspace_config.yaml")
    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_enrich_with_intent(self, mock_run, _mock_ws) -> None:
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        runner = CliRunner()
        result = runner.invoke(main, [
            "enrich", "--file", "a.py", "--symbol", "Foo",
            "--intent", "does stuff", "--config", "/tmp/all-might/config.yaml",
        ])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Enriched", result.output)

    def test_enrich_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["enrich", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--symbol", result.output)
        self.assertIn("--intent", result.output)
        self.assertIn("--relation", result.output)


class TestCliIngest(unittest.TestCase):

    @patch("allmight.cli._workspace_config", return_value="/tmp/workspace_config.yaml")
    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_ingest_all(self, mock_run, _mock_ws) -> None:
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"files": 10, "vectors": 50})
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        runner = CliRunner()
        result = runner.invoke(main, ["ingest", "--config", "/tmp/all-might/config.yaml"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("10 files", result.output)


class TestCliExplain(unittest.TestCase):

    @patch("allmight.panorama.analyzer.PanoramaAnalyzer.analyze")
    def test_explain_found(self, mock_analyze) -> None:
        from allmight.core.domain import GraphEdge, GraphNode
        from allmight.panorama.analyzer import GraphMetrics, KnowledgeGraph

        mock_analyze.return_value = KnowledgeGraph(
            nodes=[GraphNode(uid="a.py::Foo", name="Foo", file_path="a.py",
                             index="src", has_intent=True, intent="Entry")],
            edges=[],
            metrics=GraphMetrics(total_nodes=1),
        )

        runner = CliRunner()
        result = runner.invoke(main, ["explain", "a.py::Foo", "--config", "/tmp/config.yaml"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Foo", result.output)
        self.assertIn("Entry", result.output)

    @patch("allmight.panorama.analyzer.PanoramaAnalyzer.analyze")
    def test_explain_missing(self, mock_analyze) -> None:
        from allmight.panorama.analyzer import GraphMetrics, KnowledgeGraph

        mock_analyze.return_value = KnowledgeGraph(
            nodes=[], edges=[], metrics=GraphMetrics(),
        )

        runner = CliRunner()
        result = runner.invoke(main, ["explain", "missing::sym", "--config", "/tmp/config.yaml"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("not found", result.output)


class TestCliReport(unittest.TestCase):

    @patch("allmight.panorama.analyzer.PanoramaAnalyzer.analyze")
    def test_report_writes_file(self, mock_analyze) -> None:
        from allmight.panorama.analyzer import GraphMetrics, KnowledgeGraph

        mock_analyze.return_value = KnowledgeGraph(
            nodes=[], edges=[], metrics=GraphMetrics(),
        )

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "GRAPH_REPORT.md"
            runner = CliRunner()
            result = runner.invoke(main, [
                "report", "--config", "/tmp/config.yaml", "--output", str(out),
            ])
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(out.exists())
            content = out.read_text()
            self.assertIn("Knowledge Graph Report", content)


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
            # First add, then remove
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
