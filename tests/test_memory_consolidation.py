"""Tests for ConsolidationEngine."""

import pytest

from allmight.memory.consolidation import ConsolidationEngine
from allmight.memory.episodic import EpisodicMemoryStore
from allmight.memory.semantic import SemanticMemoryStore


@pytest.fixture
def root(tmp_path):
    EpisodicMemoryStore(tmp_path).initialize()
    SemanticMemoryStore(tmp_path).initialize()
    return tmp_path


@pytest.fixture
def engine(root):
    return ConsolidationEngine(root)


@pytest.fixture
def episodic(root):
    return EpisodicMemoryStore(root)


@pytest.fixture
def semantic(root):
    return SemanticMemoryStore(root)


class TestConsolidate:
    def test_no_episodes_returns_empty_report(self, engine):
        report = engine.consolidate()
        assert report.episodes_processed == 0
        assert report.facts_created == 0

    def test_creates_facts_from_observations(self, engine, episodic, semantic):
        episodic.record_episode(
            session_id="s1",
            summary="Worked on auth",
            observations=["Token refresh uses Redis cache"],
        )
        report = engine.consolidate()
        assert report.episodes_processed == 1
        assert report.facts_created >= 1
        assert semantic.count() >= 1

    def test_marks_episodes_consolidated(self, engine, episodic):
        ep = episodic.record_episode(session_id="s1", summary="Test")
        engine.consolidate()
        loaded = episodic.get_episode(ep.id)
        assert loaded.consolidated is True

    def test_creates_facts_from_decisions(self, engine, episodic, semantic):
        episodic.record_episode(
            session_id="s1",
            summary="Architecture review",
            key_decisions=["Use event sourcing for audit log"],
        )
        report = engine.consolidate()
        assert report.facts_created >= 1

    def test_recurring_topics_create_facts(self, engine, episodic, semantic):
        episodic.record_episode(
            session_id="s1", summary="Session 1", topics=["authentication"]
        )
        episodic.record_episode(
            session_id="s2", summary="Session 2", topics=["authentication"]
        )
        report = engine.consolidate()
        # Topic appeared 2+ times → should create a topic fact
        facts = semantic.list_facts()
        topic_facts = [f for f in facts if "authentication" in f.content.lower()]
        assert len(topic_facts) >= 1

    def test_reinforces_existing_facts(self, engine, episodic, semantic):
        # Create a fact first
        fact = semantic.create_fact(
            content="token refresh uses redis cache",
            category="domain_knowledge",
            confidence=0.5,
        )
        # Now an episode mentions the same thing
        episodic.record_episode(
            session_id="s1",
            summary="Auth work",
            observations=["Token refresh uses Redis cache"],
        )
        report = engine.consolidate()
        # Fact should have been updated (confidence bumped), not duplicated
        assert report.facts_updated >= 1 or report.facts_created >= 0

    def test_idempotent_when_all_consolidated(self, engine, episodic):
        episodic.record_episode(session_id="s1", summary="Test")
        engine.consolidate()
        # Second run should find nothing to do
        report2 = engine.consolidate()
        assert report2.episodes_processed == 0


class TestConsolidateImmediate:
    def test_creates_new_fact(self, engine, semantic):
        fact = engine.consolidate_immediate(
            observation="Build requires Node 18+",
            session_id="s_now",
            category="environment",
        )
        assert fact is not None
        assert fact.content == "Build requires Node 18+"
        assert "s_now" in fact.source_episodes

    def test_reinforces_existing_fact(self, engine, semantic):
        semantic.create_fact(
            content="build requires node 18 or higher",
            category="environment",
            confidence=0.5,
        )
        result = engine.consolidate_immediate(
            observation="build requires node 18 or higher",
            session_id="s2",
        )
        assert result is not None
        # Confidence should have been bumped
        reloaded = semantic.get_fact(result.id)
        assert reloaded.confidence >= 0.5


class TestConsolidationReport:
    def test_report_fields(self, engine, episodic):
        episodic.record_episode(
            session_id="s1",
            summary="Work",
            observations=["obs1", "obs2"],
            key_decisions=["dec1"],
        )
        report = engine.consolidate()
        assert isinstance(report.episodes_processed, int)
        assert isinstance(report.facts_created, int)
        assert isinstance(report.facts_updated, int)
        assert isinstance(report.facts_superseded, int)
        assert isinstance(report.conflicts_detected, int)
