"""Tests for SMAK config path rewriting after workspace copy."""

import yaml
import pytest

from allmight.merge.path_rewriter import PathRewriter


@pytest.fixture
def rewriter():
    return PathRewriter()


class TestPathClassification:
    """PathRewriter correctly classifies path types."""

    def test_classify_env_var_path(self, rewriter):
        assert rewriter.classify("$DDI_ROOT_PATH/stdcell/rtl") == "env_var"

    def test_classify_env_var_with_braces(self, rewriter):
        assert rewriter.classify("${DDI_ROOT_PATH}/stdcell/rtl") == "env_var"

    def test_classify_workspace_relative_path(self, rewriter):
        assert rewriter.classify("./store/rtl") == "workspace_relative"

    def test_classify_workspace_relative_store(self, rewriter):
        assert rewriter.classify("./store/verif") == "workspace_relative"

    def test_classify_external_relative_path(self, rewriter):
        assert rewriter.classify("../../src/rtl") == "external_relative"

    def test_classify_external_relative_single_dot_dot(self, rewriter):
        assert rewriter.classify("../other/src") == "external_relative"

    def test_classify_absolute_path(self, rewriter):
        assert rewriter.classify("/opt/tools/src") == "absolute"


class TestConfigRewriting:
    """Rewriting SMAK config.yaml paths after workspace copy."""

    def _make_config(self, tmp_path, indices):
        """Helper to write a config.yaml and return its path."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"indices": indices}))
        return config_path

    def test_env_var_paths_unchanged(self, tmp_path, rewriter):
        config = self._make_config(tmp_path, [
            {
                "name": "rtl",
                "uri": "./store/rtl",
                "paths": ["$DDI_ROOT_PATH/stdcell/rtl"],
            }
        ])
        warnings = rewriter.rewrite_config(config)
        data = yaml.safe_load(config.read_text())
        assert data["indices"][0]["paths"] == ["$DDI_ROOT_PATH/stdcell/rtl"]
        assert len(warnings) == 0

    def test_workspace_relative_paths_unchanged(self, tmp_path, rewriter):
        config = self._make_config(tmp_path, [
            {
                "name": "rtl",
                "uri": "./store/rtl",
                "paths": ["./store/rtl"],
            }
        ])
        warnings = rewriter.rewrite_config(config)
        data = yaml.safe_load(config.read_text())
        assert data["indices"][0]["paths"] == ["./store/rtl"]
        assert data["indices"][0]["uri"] == "./store/rtl"
        assert len(warnings) == 0

    def test_external_relative_paths_produce_warning(self, tmp_path, rewriter):
        config = self._make_config(tmp_path, [
            {
                "name": "rtl",
                "uri": "./store/rtl",
                "paths": ["../../src/rtl"],
            }
        ])
        warnings = rewriter.rewrite_config(config)
        assert len(warnings) == 1
        assert "../../src/rtl" in warnings[0]

    def test_absolute_paths_produce_warning(self, tmp_path, rewriter):
        config = self._make_config(tmp_path, [
            {
                "name": "rtl",
                "uri": "./store/rtl",
                "paths": ["/opt/tools/src"],
            }
        ])
        warnings = rewriter.rewrite_config(config)
        assert len(warnings) == 1
        assert "/opt/tools/src" in warnings[0]

    def test_rewrite_preserves_yaml_structure(self, tmp_path, rewriter):
        config = self._make_config(tmp_path, [
            {
                "name": "rtl",
                "description": "RTL design files",
                "uri": "./store/rtl",
                "paths": ["$DDI_ROOT_PATH/stdcell/rtl"],
                "path_env": "DDI_ROOT_PATH",
            }
        ])
        rewriter.rewrite_config(config)
        data = yaml.safe_load(config.read_text())
        idx = data["indices"][0]
        assert idx["name"] == "rtl"
        assert idx["description"] == "RTL design files"
        assert idx["uri"] == "./store/rtl"
        assert idx["path_env"] == "DDI_ROOT_PATH"

    def test_rewrite_handles_mixed_paths(self, tmp_path, rewriter):
        config = self._make_config(tmp_path, [
            {
                "name": "mixed",
                "uri": "./store/mixed",
                "paths": [
                    "$DDI_ROOT_PATH/ok",
                    "./store/also_ok",
                    "../../external/bad",
                ],
            }
        ])
        warnings = rewriter.rewrite_config(config)
        # Only the external relative path produces a warning
        assert len(warnings) == 1
        assert "../../external/bad" in warnings[0]
        # All paths preserved as-is (no rewriting, just warnings)
        data = yaml.safe_load(config.read_text())
        assert data["indices"][0]["paths"] == [
            "$DDI_ROOT_PATH/ok",
            "./store/also_ok",
            "../../external/bad",
        ]

    def test_rewrite_handles_empty_indices(self, tmp_path, rewriter):
        config = self._make_config(tmp_path, [])
        warnings = rewriter.rewrite_config(config)
        assert warnings == []

    def test_rewrite_handles_no_paths_key(self, tmp_path, rewriter):
        config = self._make_config(tmp_path, [
            {"name": "rtl", "uri": "./store/rtl"}
        ])
        warnings = rewriter.rewrite_config(config)
        assert warnings == []

    def test_rewrite_multiple_indices(self, tmp_path, rewriter):
        config = self._make_config(tmp_path, [
            {
                "name": "rtl",
                "uri": "./store/rtl",
                "paths": ["$DDI_ROOT_PATH/rtl"],
            },
            {
                "name": "verif",
                "uri": "./store/verif",
                "paths": ["../../verif/tb"],
            },
        ])
        warnings = rewriter.rewrite_config(config)
        assert len(warnings) == 1
        assert "verif" in warnings[0]
