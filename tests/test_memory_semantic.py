"""Tests for SemanticMemoryStore (Layer 3)."""

import pytest

from allmight.memory.semantic import SemanticMemoryStore


@pytest.fixture
def store(tmp_path):
    s = SemanticMemoryStore(tmp_path)
    s.initialize()
    return s


class TestCreateFact:
    def test_creates_fact_with_id(self, store):
        fact = store.create_fact(
            content="User prefers dark mode",
            category="user_preference",
        )
        assert fact.id.startswith("fact_")
        assert fact.content == "User prefers dark mode"
        assert fact.category == "user_preference"
        assert fact.confidence == 1.0

    def test_fact_persists_to_disk(self, store, tmp_path):
        store.create_fact(content="Test", category="domain_knowledge")
        files = list((tmp_path / "memory" / "semantic").glob("*.fact.yaml"))
        assert len(files) == 1

    def test_custom_fields(self, store):
        fact = store.create_fact(
            content="Always run lint before commit",
            category="convention",
            confidence=0.9,
            importance=0.8,
            source_episodes=["ep_001", "ep_002"],
            namespace="team_alpha",
        )
        assert fact.confidence == 0.9
        assert fact.importance == 0.8
        assert fact.source_episodes == ["ep_001", "ep_002"]
        assert fact.namespace == "team_alpha"


class TestGetFact:
    def test_get_existing(self, store):
        fact = store.create_fact(content="Test", category="test")
        loaded = store.get_fact(fact.id)
        assert loaded is not None
        assert loaded.content == "Test"

    def test_get_nonexistent(self, store):
        assert store.get_fact("nonexistent") is None


class TestListFacts:
    def test_list_empty(self, store):
        assert store.list_facts() == []

    def test_list_all(self, store):
        store.create_fact(content="Fact 1", category="a")
        store.create_fact(content="Fact 2", category="b")
        assert len(store.list_facts()) == 2

    def test_filter_by_category(self, store):
        store.create_fact(content="Pref", category="user_preference")
        store.create_fact(content="Conv", category="convention")
        store.create_fact(content="Pref2", category="user_preference")
        prefs = store.list_facts(category="user_preference")
        assert len(prefs) == 2

    def test_limit(self, store):
        for i in range(10):
            store.create_fact(content=f"Fact {i}", category="test")
        assert len(store.list_facts(limit=3)) == 3


class TestUpdateFact:
    def test_update_content(self, store):
        fact = store.create_fact(content="Old", category="test")
        updated = store.update_fact(fact.id, content="New")
        assert updated.content == "New"

    def test_update_confidence(self, store):
        fact = store.create_fact(content="Test", category="test", confidence=0.5)
        updated = store.update_fact(fact.id, confidence=0.9)
        assert updated.confidence == 0.9

    def test_add_source_episodes(self, store):
        fact = store.create_fact(
            content="Test", category="test", source_episodes=["ep_001"]
        )
        updated = store.update_fact(
            fact.id, add_source_episodes=["ep_002", "ep_003"]
        )
        assert set(updated.source_episodes) == {"ep_001", "ep_002", "ep_003"}

    def test_update_nonexistent_returns_none(self, store):
        assert store.update_fact("nope", content="x") is None


class TestRecordAccess:
    def test_bumps_access_count(self, store):
        fact = store.create_fact(content="Test", category="test")
        assert fact.access_count == 0
        updated = store.record_access(fact.id)
        assert updated.access_count == 1
        updated2 = store.record_access(fact.id)
        assert updated2.access_count == 2

    def test_updates_last_accessed(self, store):
        fact = store.create_fact(content="Test", category="test")
        original_accessed = fact.last_accessed
        updated = store.record_access(fact.id)
        assert updated.last_accessed >= original_accessed


class TestSupersede:
    def test_creates_successor_fact(self, store):
        old = store.create_fact(
            content="Python 3.10 required",
            category="convention",
            confidence=1.0,
        )
        new = store.supersede(
            old.id,
            new_content="Python 3.11 required",
            source_episodes=["ep_upgrade"],
        )
        assert new is not None
        assert new.supersedes == old.id
        assert new.content == "Python 3.11 required"
        assert new.confidence == 1.0

    def test_reduces_old_fact_confidence(self, store):
        old = store.create_fact(content="Old info", category="test", confidence=1.0)
        store.supersede(old.id, new_content="New info")
        reloaded = store.get_fact(old.id)
        assert reloaded.confidence < 0.5  # Reduced by × 0.3

    def test_supersede_nonexistent_returns_none(self, store):
        assert store.supersede("nope", new_content="x") is None


class TestCountAndAvg:
    def test_count(self, store):
        assert store.count() == 0
        store.create_fact(content="A", category="a")
        store.create_fact(content="B", category="b")
        assert store.count() == 2

    def test_avg_confidence(self, store):
        store.create_fact(content="A", category="a", confidence=0.8)
        store.create_fact(content="B", category="b", confidence=0.6)
        assert abs(store.avg_confidence() - 0.7) < 0.01

    def test_avg_confidence_empty(self, store):
        assert store.avg_confidence() == 0.0
