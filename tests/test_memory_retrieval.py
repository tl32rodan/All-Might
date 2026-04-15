"""Tests for UnifiedRetriever."""

import pytest

from allmight.core.domain import MemoryConfig
from allmight.memory.episodic import EpisodicMemoryStore
from allmight.memory.retrieval import UnifiedRetriever
from allmight.memory.semantic import SemanticMemoryStore


@pytest.fixture
def root(tmp_path):
    EpisodicMemoryStore(tmp_path).initialize()
    SemanticMemoryStore(tmp_path).initialize()
    return tmp_path


@pytest.fixture
def retriever(root):
    return UnifiedRetriever(root)


@pytest.fixture
def episodic(root):
    return EpisodicMemoryStore(root)


@pytest.fixture
def semantic(root):
    return SemanticMemoryStore(root)


class TestRetrieve:
    def test_empty_stores_return_empty(self, retriever):
        results = retriever.retrieve("authentication")
        assert results == []

    def test_finds_matching_episode(self, retriever, episodic):
        episodic.record_episode(
            session_id="s1",
            summary="Fixed authentication token refresh bug in the Redis layer",
        )
        results = retriever.retrieve("authentication")
        assert len(results) >= 1
        assert results[0].memory_type == "episode"
        assert "authentication" in results[0].content.lower() or results[0].score > 0

    def test_finds_matching_fact(self, retriever, semantic):
        semantic.create_fact(
            content="Database uses PostgreSQL 15 with pgvector extension",
            category="environment",
        )
        results = retriever.retrieve("Database PostgreSQL")
        assert len(results) >= 1
        assert results[0].memory_type == "fact"

    def test_merges_episode_and_fact_results(self, retriever, episodic, semantic):
        episodic.record_episode(
            session_id="s1",
            summary="Configured Redis caching layer",
        )
        semantic.create_fact(
            content="Redis caching is used for session storage",
            category="architecture_decision",
        )
        results = retriever.retrieve("Redis caching")
        assert len(results) == 2
        sources = {r.source for r in results}
        assert "episodic" in sources
        assert "semantic" in sources

    def test_results_sorted_by_score(self, retriever, semantic):
        semantic.create_fact(
            content="Python is the primary language",
            category="environment",
            importance=0.9,
        )
        semantic.create_fact(
            content="Python 3.11 is required for the build",
            category="environment",
            importance=0.5,
        )
        results = retriever.retrieve("Python language")
        if len(results) >= 2:
            assert results[0].score >= results[1].score

    def test_top_k_limits_results(self, retriever, semantic):
        for i in range(10):
            semantic.create_fact(
                content=f"Test fact {i} about deployment pipeline",
                category="domain_knowledge",
            )
        results = retriever.retrieve("deployment pipeline", top_k=3)
        assert len(results) <= 3

    def test_no_duplicates(self, retriever, semantic):
        semantic.create_fact(content="Unique fact", category="test")
        results = retriever.retrieve("Unique fact")
        ids = [r.memory_id for r in results]
        assert len(ids) == len(set(ids))


class TestRetrievalResult:
    def test_result_has_all_scores(self, retriever, semantic):
        semantic.create_fact(
            content="API uses REST with OpenAPI specs",
            category="architecture_decision",
        )
        results = retriever.retrieve("API REST")
        if results:
            r = results[0]
            assert hasattr(r, "recency_score")
            assert hasattr(r, "importance_score")
            assert hasattr(r, "relevance_score")
            assert hasattr(r, "score")


class TestCustomWeights:
    def test_high_importance_weight(self, root, episodic, semantic):
        config = MemoryConfig(
            retrieval_weights={"recency": 0.1, "importance": 0.8, "relevance": 0.1}
        )
        retriever = UnifiedRetriever(root, config=config)

        semantic.create_fact(
            content="High importance fact about testing",
            category="convention",
            importance=0.95,
        )
        semantic.create_fact(
            content="Low importance fact about testing",
            category="convention",
            importance=0.1,
        )
        results = retriever.retrieve("testing")
        if len(results) >= 2:
            # High importance should be ranked first
            assert results[0].importance_score > results[1].importance_score


class TestSmakIntegration:
    def test_retriever_works_without_smak(self, retriever, semantic):
        """When SMAK is unavailable, retrieval falls back to keyword matching."""
        semantic.create_fact(content="Local fact about auth tokens", category="test")
        results = retriever.retrieve("auth tokens")
        assert len(results) >= 1
        # Should use keyword fallback (SMAK not available in test env)
        assert results[0].source == "semantic"
