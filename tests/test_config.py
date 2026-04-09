"""Tests for ConfigManager."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from allmight.config import ConfigManager


class TestConfigManager(unittest.TestCase):

    def _setup_project(self, tmp_dir: str) -> Path:
        """Create a minimal project structure with workspace_config.yaml."""
        root = Path(tmp_dir)
        (root / "all-might").mkdir()
        # Write initial workspace_config.yaml
        config = {
            "indices": [
                {"name": "source_code", "uri": "./smak/source_code", "description": "Source code", "paths": ["./src"]},
            ],
        }
        with open(root / "workspace_config.yaml", "w") as f:
            yaml.dump(config, f)
        # Write initial all-might/config.yaml
        am_config = {"project": {"name": "test"}}
        with open(root / "all-might" / "config.yaml", "w") as f:
            yaml.dump(am_config, f)
        return root

    def test_list_indices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)
            indices = mgr.list_indices()
            self.assertEqual(len(indices), 1)
            self.assertEqual(indices[0].name, "source_code")

    def test_get_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)
            idx = mgr.get_index("source_code")
            self.assertIsNotNone(idx)
            self.assertEqual(idx.name, "source_code")
            self.assertIsNone(mgr.get_index("nonexistent"))

    def test_add_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)
            new = mgr.add_index("tests", "Test files", ["./tests"])
            self.assertEqual(new.name, "tests")

            # Verify workspace_config.yaml updated
            with open(root / "workspace_config.yaml") as f:
                data = yaml.safe_load(f)
            names = [idx["name"] for idx in data["indices"]]
            self.assertIn("tests", names)

            # Verify all-might/config.yaml synced
            with open(root / "all-might" / "config.yaml") as f:
                am_data = yaml.safe_load(f)
            am_names = [idx["name"] for idx in am_data["indices"]]
            self.assertIn("tests", am_names)

    def test_add_duplicate_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)
            with self.assertRaises(ValueError) as ctx:
                mgr.add_index("source_code", "dup", ["./src"])
            self.assertIn("already exists", str(ctx.exception))

    def test_remove_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)
            mgr.add_index("tests", "Tests", ["./tests"])
            mgr.remove_index("tests")
            self.assertEqual(len(mgr.list_indices()), 1)
            self.assertIsNone(mgr.get_index("tests"))

    def test_remove_nonexistent_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)
            with self.assertRaises(ValueError):
                mgr.remove_index("nonexistent")

    def test_update_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)
            updated = mgr.update_index("source_code", description="Updated src")
            self.assertEqual(updated.description, "Updated src")
            # Verify persisted
            mgr2 = ConfigManager(root)
            self.assertEqual(mgr2.get_index("source_code").description, "Updated src")

    def test_update_nonexistent_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)
            with self.assertRaises(ValueError):
                mgr.update_index("missing", description="x")

    def test_add_index_with_path_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)
            new = mgr.add_index("sos", "SOS files", ["$DDI_ROOT_PATH/src"],
                                path_env="DDI_ROOT_PATH")
            self.assertEqual(new.path_env, "DDI_ROOT_PATH")

            with open(root / "workspace_config.yaml") as f:
                data = yaml.safe_load(f)
            sos = next(idx for idx in data["indices"] if idx["name"] == "sos")
            self.assertEqual(sos["path_env"], "DDI_ROOT_PATH")

    def test_roundtrip_preserves_all_indices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)
            mgr.add_index("docs", "Documentation", ["./docs"])
            mgr.add_index("tests", "Tests", ["./tests"])

            # Fresh load
            mgr2 = ConfigManager(root)
            names = [idx.name for idx in mgr2.list_indices()]
            self.assertEqual(names, ["source_code", "docs", "tests"])

    def test_add_index_auto_generates_uri(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)
            new = mgr.add_index("tests", "Test files", ["./tests"])
            self.assertEqual(new.uri, "./smak/tests")

            # Verify persisted in workspace_config.yaml
            with open(root / "workspace_config.yaml") as f:
                data = yaml.safe_load(f)
            tests_idx = next(idx for idx in data["indices"] if idx["name"] == "tests")
            self.assertEqual(tests_idx["uri"], "./smak/tests")

    def test_add_index_with_custom_uri(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)
            new = mgr.add_index("tests", "Test files", ["./tests"], uri="./custom/tests")
            self.assertEqual(new.uri, "./custom/tests")

    def test_roundtrip_preserves_uri(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)

            # Verify existing uri is preserved
            idx = mgr.get_index("source_code")
            self.assertEqual(idx.uri, "./smak/source_code")

            # Add index, modify something, check uri survives round-trip
            mgr.add_index("docs", "Documentation", ["./docs"])
            mgr2 = ConfigManager(root)
            sc = mgr2.get_index("source_code")
            self.assertEqual(sc.uri, "./smak/source_code")
            docs = mgr2.get_index("docs")
            self.assertEqual(docs.uri, "./smak/docs")

    def test_update_index_preserves_uri(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp)
            mgr = ConfigManager(root)
            updated = mgr.update_index("source_code", description="Updated")
            self.assertEqual(updated.uri, "./smak/source_code")


if __name__ == "__main__":
    unittest.main()
