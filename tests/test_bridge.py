"""Tests for SmakBridge — subprocess wrapper for SMAK CLI."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from allmight.bridge import SmakBridge
from allmight.bridge.smak_bridge import SmakBridgeError


def _mock_run(stdout: str = "{}", returncode: int = 0, stderr: str = ""):
    """Create a mock subprocess.run result."""
    result = MagicMock()
    result.stdout = stdout
    result.stderr = stderr
    result.returncode = returncode
    return result


class TestSmakBridge(unittest.TestCase):

    def setUp(self) -> None:
        self.bridge = SmakBridge(workspace_config="/tmp/workspace_config.yaml")

    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_search_calls_smak_cli(self, mock_run) -> None:
        mock_run.return_value = _mock_run(json.dumps({"hits": [{"uid": "a::b"}]}))
        result = self.bridge.search("test query", index="source_code", top_k=5)
        self.assertEqual(result["hits"][0]["uid"], "a::b")

        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "smak")
        self.assertIn("search", cmd)
        self.assertIn("test query", cmd)
        self.assertIn("--json", cmd)
        self.assertIn("--index", cmd)

    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_search_all(self, mock_run) -> None:
        mock_run.return_value = _mock_run(json.dumps({"src": {"hits": []}}))
        result = self.bridge.search_all("query")
        self.assertIn("src", result)
        cmd = mock_run.call_args[0][0]
        self.assertIn("search-all", cmd)

    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_lookup(self, mock_run) -> None:
        mock_run.return_value = _mock_run(json.dumps({"found": True, "uid": "x::y"}))
        result = self.bridge.lookup("x::y")
        self.assertTrue(result["found"])

    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_enrich_symbol(self, mock_run) -> None:
        mock_run.return_value = _mock_run(json.dumps({"status": "ok", "symbol": "foo"}))
        result = self.bridge.enrich_symbol(
            "a.py", "foo", intent="does stuff",
            relations=["b.py::bar"], bidirectional=True,
        )
        self.assertEqual(result["status"], "ok")
        cmd = mock_run.call_args[0][0]
        self.assertIn("enrich", cmd)
        self.assertIn("--intent", cmd)
        self.assertIn("--relation", cmd)
        self.assertIn("--bidirectional", cmd)

    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_enrich_file(self, mock_run) -> None:
        mock_run.return_value = _mock_run(json.dumps({"total_symbols": 3}))
        result = self.bridge.enrich_file("a.py")
        self.assertEqual(result["total_symbols"], 3)

    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_ingest(self, mock_run) -> None:
        mock_run.return_value = _mock_run(json.dumps({"files": 5, "vectors": 20}))
        result = self.bridge.ingest(index="source_code")
        self.assertEqual(result["files"], 5)
        cmd = mock_run.call_args[0][0]
        self.assertIn("--index", cmd)

    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_ingest_no_index(self, mock_run) -> None:
        mock_run.return_value = _mock_run(json.dumps({"files": 1}))
        self.bridge.ingest()
        cmd = mock_run.call_args[0][0]
        self.assertNotIn("--index", cmd)

    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_describe(self, mock_run) -> None:
        mock_run.return_value = _mock_run(json.dumps({"indices": []}))
        result = self.bridge.describe()
        self.assertIn("indices", result)

    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_health(self, mock_run) -> None:
        mock_run.return_value = _mock_run(json.dumps({"status": "healthy"}))
        result = self.bridge.health()
        self.assertEqual(result["status"], "healthy")

    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_graph_stats(self, mock_run) -> None:
        mock_run.return_value = _mock_run(json.dumps({"by_index": {}}))
        result = self.bridge.graph_stats()
        self.assertIn("by_index", result)

    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_nonzero_exit_raises(self, mock_run) -> None:
        mock_run.return_value = _mock_run(returncode=1, stderr="Config not found")
        with self.assertRaises(SmakBridgeError) as ctx:
            self.bridge.describe()
        self.assertEqual(ctx.exception.returncode, 1)
        self.assertIn("Config not found", str(ctx.exception))

    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_invalid_json_raises(self, mock_run) -> None:
        mock_run.return_value = _mock_run(stdout="not json")
        with self.assertRaises(SmakBridgeError) as ctx:
            self.bridge.describe()
        self.assertIn("invalid JSON", str(ctx.exception))

    @patch("allmight.bridge.smak_bridge.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_cli_raises(self, mock_run) -> None:
        with self.assertRaises(SmakBridgeError) as ctx:
            self.bridge.describe()
        self.assertIn("not found", str(ctx.exception))

    def test_workspace_config_resolved(self) -> None:
        bridge = SmakBridge(workspace_config="./relative/config.yaml")
        self.assertTrue(bridge.workspace_config.startswith("/"))

    @patch("allmight.bridge.smak_bridge.subprocess.run")
    def test_all_commands_append_json_flag(self, mock_run) -> None:
        mock_run.return_value = _mock_run(json.dumps({}))
        methods = [
            lambda: self.bridge.search("q"),
            lambda: self.bridge.search_all("q"),
            lambda: self.bridge.lookup("a::b"),
            lambda: self.bridge.enrich_symbol("a.py", "foo"),
            lambda: self.bridge.enrich_file("a.py"),
            lambda: self.bridge.ingest(),
            lambda: self.bridge.describe(),
            lambda: self.bridge.health(),
            lambda: self.bridge.graph_stats(),
        ]
        for method in methods:
            method()
            cmd = mock_run.call_args[0][0]
            self.assertIn("--json", cmd, f"--json missing from {cmd}")


if __name__ == "__main__":
    unittest.main()
