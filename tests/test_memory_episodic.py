"""Tests for EpisodicMemoryStore (Layer 2)."""

import pytest

from allmight.memory.episodic import EpisodicMemoryStore


@pytest.fixture
def store(tmp_path):
    s = EpisodicMemoryStore(tmp_path)
    s.initialize()
    return s


class TestRecordEpisode:
    def test_creates_episode_file(self, store):
        ep = store.record_episode(
            session_id="sess_001",
            summary="Fixed authentication bug",
            observations=["Token refresh was broken"],
            key_decisions=["Used JWT instead of session cookies"],
        )
        assert ep.id.startswith("ep_")
        assert ep.session_id == "sess_001"
        assert ep.summary == "Fixed authentication bug"
        assert ep.consolidated is False

    def test_episode_persists_to_disk(self, store, tmp_path):
        store.record_episode(session_id="sess_002", summary="Test")
        files = list((tmp_path / "memory" / "episodes").rglob("*.episode.yaml"))
        assert len(files) == 1

    def test_multiple_episodes(self, store):
        store.record_episode(session_id="sess_a", summary="First")
        store.record_episode(session_id="sess_b", summary="Second")
        assert store.count() == 2


class TestGetEpisode:
    def test_get_by_id(self, store):
        ep = store.record_episode(session_id="s1", summary="Test")
        loaded = store.get_episode(ep.id)
        assert loaded is not None
        assert loaded.summary == "Test"
        assert loaded.session_id == "s1"

    def test_get_nonexistent_returns_none(self, store):
        assert store.get_episode("nonexistent") is None


class TestListEpisodes:
    def test_list_empty(self, store):
        assert store.list_episodes() == []

    def test_list_returns_episodes(self, store):
        store.record_episode(session_id="s1", summary="First")
        store.record_episode(session_id="s2", summary="Second")
        episodes = store.list_episodes()
        assert len(episodes) == 2

    def test_list_with_limit(self, store):
        for i in range(5):
            store.record_episode(session_id=f"s{i}", summary=f"Episode {i}")
        episodes = store.list_episodes(limit=3)
        assert len(episodes) == 3

    def test_unconsolidated_only(self, store):
        ep1 = store.record_episode(session_id="s1", summary="One")
        store.record_episode(session_id="s2", summary="Two")
        store.mark_consolidated(ep1.id)

        episodes = store.list_episodes(unconsolidated_only=True)
        assert len(episodes) == 1
        assert episodes[0].session_id == "s2"


class TestMarkConsolidated:
    def test_mark_existing(self, store):
        ep = store.record_episode(session_id="s1", summary="Test")
        assert store.mark_consolidated(ep.id) is True
        loaded = store.get_episode(ep.id)
        assert loaded.consolidated is True

    def test_mark_nonexistent_returns_false(self, store):
        assert store.mark_consolidated("nonexistent") is False


class TestCount:
    def test_count_zero(self, store):
        assert store.count() == 0

    def test_count_unconsolidated(self, store):
        ep = store.record_episode(session_id="s1", summary="One")
        store.record_episode(session_id="s2", summary="Two")
        store.mark_consolidated(ep.id)

        assert store.count_unconsolidated() == 1


class TestEpisodeFields:
    def test_all_fields_persisted(self, store):
        ep = store.record_episode(
            session_id="sess_full",
            summary="Full test",
            key_decisions=["dec1", "dec2"],
            observations=["obs1"],
            files_touched=["src/main.py", "tests/test_main.py"],
            topics=["auth", "security"],
            outcome="success",
            importance=0.9,
        )
        loaded = store.get_episode(ep.id)
        assert loaded.key_decisions == ["dec1", "dec2"]
        assert loaded.observations == ["obs1"]
        assert loaded.files_touched == ["src/main.py", "tests/test_main.py"]
        assert loaded.topics == ["auth", "security"]
        assert loaded.outcome == "success"
        assert loaded.importance == 0.9
