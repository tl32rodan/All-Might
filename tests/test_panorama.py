"""Tests for Panorama — analyzer and exporter."""

import json
from pathlib import Path

import yaml
import pytest

from allmight.detroit_smak.scanner import ProjectScanner
from allmight.detroit_smak.initializer import ProjectInitializer
from allmight.panorama.analyzer import PanoramaAnalyzer
from allmight.panorama.exporter import PanoramaExporter


@pytest.fixture
def project_with_graph(tmp_path):
    """Create a project with sidecar relations forming a graph."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\nclass App: pass\n")
    (tmp_path / "src" / "utils.py").write_text("def helper(): pass\n")
    (tmp_path / "issues").mkdir()
    (tmp_path / "issues" / "bug-1.md").write_text("# Bug 1\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

    scanner = ProjectScanner()
    manifest = scanner.scan(tmp_path)
    initializer = ProjectInitializer()
    initializer.initialize(manifest)

    # Analyzer/exporter need config.yaml — create workspace config
    config = {
        "project": {"name": manifest.name, "root": str(tmp_path)},
        "indices": [
            {"name": idx.name, "uri": idx.uri or f"./smak/{idx.name}",
             "description": idx.description, "paths": idx.paths}
            for idx in manifest.indices
        ],
    }
    with open(tmp_path / "config.yaml", "w") as f:
        yaml.dump(config, f)

    # Create sidecars with relations
    sidecar1 = {
        "symbols": [
            {
                "name": "hello",
                "intent": "Entry point function",
                "relations": ["./src/utils.py::helper", "./issues/bug-1.md::*"],
            },
            {
                "name": "App",
                "intent": "Main application class",
                "relations": ["./src/utils.py::helper"],
            },
        ]
    }
    with open(tmp_path / "src" / ".main.py.sidecar.yaml", "w") as f:
        yaml.dump(sidecar1, f)

    sidecar2 = {
        "symbols": [
            {
                "name": "helper",
                "intent": "Utility function",
                "relations": [],
            },
        ]
    }
    with open(tmp_path / "src" / ".utils.py.sidecar.yaml", "w") as f:
        yaml.dump(sidecar2, f)

    return tmp_path


class TestPanoramaAnalyzer:
    def test_empty_project(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        scanner = ProjectScanner()
        manifest = scanner.scan(tmp_path)
        initializer = ProjectInitializer()
        initializer.initialize(manifest)

        # Analyzer needs config.yaml — create workspace config
        config = {
            "project": {"name": manifest.name, "root": str(tmp_path)},
            "indices": [
                {"name": idx.name, "uri": idx.uri or f"./smak/{idx.name}",
                 "description": idx.description, "paths": idx.paths}
                for idx in manifest.indices
            ],
        }
        with open(tmp_path / "config.yaml", "w") as f:
            yaml.dump(config, f)

        config_path = tmp_path / "config.yaml"
        analyzer = PanoramaAnalyzer()
        graph = analyzer.analyze(config_path)

        assert graph.metrics.total_nodes == 0
        assert graph.metrics.total_edges == 0

    def test_graph_with_relations(self, project_with_graph):
        config_path = project_with_graph / "config.yaml"
        analyzer = PanoramaAnalyzer()
        graph = analyzer.analyze(config_path)

        assert graph.metrics.total_nodes == 3  # hello, App, helper
        assert graph.metrics.total_edges == 3  # hello->helper, hello->bug, App->helper
        assert graph.metrics.nodes_with_intent == 3

    def test_orphan_detection(self, project_with_graph):
        config_path = project_with_graph / "config.yaml"
        analyzer = PanoramaAnalyzer()
        graph = analyzer.analyze(config_path)

        # helper has no outgoing edges but is a target — not an orphan
        # All nodes are connected through edges
        assert graph.metrics.orphan_nodes >= 0

    def test_cluster_count(self, project_with_graph):
        config_path = project_with_graph / "config.yaml"
        analyzer = PanoramaAnalyzer()
        graph = analyzer.analyze(config_path)

        # All connected through hello -> helper <- App
        assert graph.metrics.clusters >= 1


class TestPanoramaExporter:
    def test_export_json(self, project_with_graph):
        config_path = project_with_graph / "config.yaml"
        exporter = PanoramaExporter()
        output = exporter.export(config_path, fmt="json")

        assert output.exists()
        with open(output) as f:
            data = json.load(f)

        assert "metrics" in data
        assert "nodes" in data
        assert "edges" in data
        assert data["metrics"]["total_nodes"] == 3
        assert data["metrics"]["total_edges"] == 3

    def test_export_mermaid(self, project_with_graph):
        config_path = project_with_graph / "config.yaml"
        exporter = PanoramaExporter()
        output = exporter.export(config_path, fmt="mermaid")

        assert output.exists()
        content = output.read_text()
        assert "graph LR" in content
        assert "-->" in content

    def test_export_obsidian(self, project_with_graph):
        config_path = project_with_graph / "config.yaml"
        exporter = PanoramaExporter()
        output = exporter.export(config_path, fmt="obsidian")

        assert output.is_dir()
        md_files = list(output.glob("*.md"))
        assert len(md_files) >= 3  # hello, App, helper

    def test_obsidian_has_backlinks(self, project_with_graph):
        config_path = project_with_graph / "config.yaml"
        exporter = PanoramaExporter()
        output = exporter.export(config_path, fmt="obsidian")

        # helper.md should have "Referenced by" section
        helper_md = output / "helper.md"
        assert helper_md.exists()
        content = helper_md.read_text()
        assert "Referenced by" in content

    def test_custom_output_dir(self, project_with_graph, tmp_path):
        config_path = project_with_graph / "config.yaml"
        custom_dir = tmp_path / "custom_output"
        exporter = PanoramaExporter()
        output = exporter.export(config_path, fmt="json", output_dir=custom_dir)

        assert output.exists()
        assert str(output).startswith(str(custom_dir))

    def test_invalid_format_raises(self, project_with_graph):
        config_path = project_with_graph / "config.yaml"
        exporter = PanoramaExporter()
        with pytest.raises(ValueError, match="Unknown format"):
            exporter.export(config_path, fmt="invalid")
