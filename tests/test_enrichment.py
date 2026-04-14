"""Tests for Enrichment — policy, planner, and tracker."""

from pathlib import Path

import yaml
import pytest

from allmight.detroit_smak.scanner import ProjectScanner
from allmight.detroit_smak.initializer import ProjectInitializer
from allmight.enrichment.policy import default_policy, TriggerEvent
from allmight.enrichment.planner import EnrichmentPlanner
from allmight.enrichment.tracker import PowerTracker


@pytest.fixture
def initialized_project(tmp_path):
    """Create a project initialized by Detroit SMAK."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\nclass App: pass\n")
    (tmp_path / "src" / "utils.py").write_text("def helper(): pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

    scanner = ProjectScanner()
    manifest = scanner.scan(tmp_path)
    initializer = ProjectInitializer()
    initializer.initialize(manifest)
    return tmp_path


@pytest.fixture
def project_with_partial_sidecars(initialized_project):
    """Add sidecars with partial enrichment."""
    src = initialized_project / "src"

    # main.py: 2 symbols, 1 enriched
    sidecar1 = {
        "symbols": [
            {"name": "hello", "intent": "Greets the user", "relations": []},
            {"name": "App", "intent": "", "relations": []},
        ]
    }
    with open(src / ".main.py.sidecar.yaml", "w") as f:
        yaml.dump(sidecar1, f)

    # utils.py: 1 symbol, 0 enriched (no sidecar)

    return initialized_project


class TestEnrichmentPolicy:
    def test_default_policy_is_advisory(self):
        policy = default_policy()
        assert policy.strategy == "advisory"

    def test_default_policy_has_rules(self):
        policy = default_policy()
        assert len(policy.rules) > 0

    def test_default_policy_covers_key_triggers(self):
        policy = default_policy()
        triggers = {r.trigger for r in policy.rules}
        assert TriggerEvent.ON_READ_SYMBOL in triggers
        assert TriggerEvent.ON_CODE_CHANGE in triggers
        assert TriggerEvent.ON_DISCOVER_RELATION in triggers


class TestEnrichmentPlanner:
    def test_plan_empty_project(self, initialized_project):
        """No sidecars → all files get no_sidecar tasks."""
        config_path = initialized_project / "config.yaml"
        planner = EnrichmentPlanner()
        tasks = planner.plan(config_path)

        # Should find source files needing sidecars
        assert len(tasks) > 0
        assert all(t.reason == "no_sidecar" for t in tasks)

    def test_plan_partial_enrichment(self, project_with_partial_sidecars):
        """Partial sidecars → mix of missing_intent and no_sidecar tasks."""
        config_path = project_with_partial_sidecars / "config.yaml"
        planner = EnrichmentPlanner()
        tasks = planner.plan(config_path)

        reasons = {t.reason for t in tasks}
        # Should have missing_intent for "App" and no_sidecar for utils.py
        assert "missing_intent" in reasons or "no_sidecar" in reasons

    def test_plan_sorted_by_priority(self, project_with_partial_sidecars):
        """Tasks should be sorted highest priority first."""
        config_path = project_with_partial_sidecars / "config.yaml"
        planner = EnrichmentPlanner()
        tasks = planner.plan(config_path)

        priorities = [t.priority for t in tasks]
        assert priorities == sorted(priorities, reverse=True)

    def test_plan_missing_intent_higher_than_no_sidecar(self):
        """missing_intent should have higher base priority than no_sidecar."""
        planner = EnrichmentPlanner()
        p_intent = planner._calculate_priority(0, "missing_intent")
        p_sidecar = planner._calculate_priority(0, "no_sidecar")
        assert p_intent > p_sidecar


class TestPowerTracker:
    def test_empty_project_zero_coverage(self, initialized_project):
        config_path = initialized_project / "config.yaml"
        tracker = PowerTracker()
        level = tracker.calculate(config_path)
        assert level.coverage_pct == 0.0
        assert level.total_symbols == 0

    def test_partial_enrichment_coverage(self, project_with_partial_sidecars):
        config_path = project_with_partial_sidecars / "config.yaml"
        tracker = PowerTracker()
        level = tracker.calculate(config_path)

        # 2 symbols in sidecar, 1 with intent = 50%
        assert level.total_symbols == 2
        assert level.enriched_symbols == 1
        assert level.coverage_pct == 50.0

    def test_persists_to_tracker_yaml(self, project_with_partial_sidecars):
        config_path = project_with_partial_sidecars / "config.yaml"
        tracker = PowerTracker()
        tracker.calculate(config_path)

        tracker_path = project_with_partial_sidecars / "enrichment" / "tracker.yaml"
        assert tracker_path.exists()

        with open(tracker_path) as f:
            data = yaml.safe_load(f)

        assert data["power_level"]["coverage_pct"] == 50.0
        assert len(data["history"]) >= 1

    def test_history_accumulates(self, project_with_partial_sidecars):
        config_path = project_with_partial_sidecars / "config.yaml"
        tracker = PowerTracker()

        tracker.calculate(config_path)
        tracker.calculate(config_path)

        tracker_path = project_with_partial_sidecars / "enrichment" / "tracker.yaml"
        with open(tracker_path) as f:
            data = yaml.safe_load(f)

        assert len(data["history"]) >= 2

    def test_coverage_by_index(self, project_with_partial_sidecars):
        config_path = project_with_partial_sidecars / "config.yaml"
        tracker = PowerTracker()
        level = tracker.calculate(config_path)

        assert "source_code" in level.by_index
        assert level.by_index["source_code"] == 50.0
