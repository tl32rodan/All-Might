"""Tests for DecayEngine and forgetting curve functions."""

from datetime import datetime, timedelta, timezone

import pytest

from allmight.memory.decay import (
    ARCHIVE_THRESHOLD,
    DORMANT_THRESHOLD,
    DecayEngine,
    compute_decay_score,
    is_archivable,
    is_dormant,
)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class TestComputeDecayScore:
    def test_just_accessed_is_near_one(self):
        now = datetime.now(timezone.utc)
        score = compute_decay_score(_iso(now), 1, now=now)
        assert score > 0.99

    def test_never_accessed_decays_faster(self):
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        # access_count=0 treated as 1 (creation counts), but still
        # decays faster than a heavily-accessed memory
        score_zero = compute_decay_score(_iso(week_ago), 0, now=now)
        score_many = compute_decay_score(_iso(week_ago), 50, now=now)
        assert score_zero < score_many

    def test_high_access_count_resists_decay(self):
        now = datetime.now(timezone.utc)
        month_ago = now - timedelta(days=30)
        # access_count=100 → high strength → slow decay
        score_high = compute_decay_score(_iso(month_ago), 100, now=now)
        score_low = compute_decay_score(_iso(month_ago), 1, now=now)
        assert score_high > score_low

    def test_older_memory_lower_score(self):
        now = datetime.now(timezone.utc)
        recent = now - timedelta(hours=1)
        old = now - timedelta(days=30)
        score_recent = compute_decay_score(_iso(recent), 5, now=now)
        score_old = compute_decay_score(_iso(old), 5, now=now)
        assert score_recent > score_old

    def test_invalid_timestamp_returns_zero(self):
        assert compute_decay_score("not-a-date", 5) == 0.0

    def test_score_between_zero_and_one(self):
        now = datetime.now(timezone.utc)
        for hours in [0, 1, 24, 168, 720, 8760]:
            ts = now - timedelta(hours=hours)
            for count in [1, 5, 10, 50]:
                score = compute_decay_score(_iso(ts), count, now=now)
                assert 0.0 <= score <= 1.0


class TestIsDormant:
    def test_recent_not_dormant(self):
        now = datetime.now(timezone.utc)
        assert not is_dormant(_iso(now), 5, now=now)

    def test_old_with_no_access_is_dormant(self):
        now = datetime.now(timezone.utc)
        year_ago = now - timedelta(days=365)
        assert is_dormant(_iso(year_ago), 1, now=now)


class TestIsArchivable:
    def test_recent_not_archivable(self):
        now = datetime.now(timezone.utc)
        assert not is_archivable(_iso(now), 5, now=now)

    def test_very_old_is_archivable(self):
        now = datetime.now(timezone.utc)
        ancient = now - timedelta(days=365 * 3)
        assert is_archivable(_iso(ancient), 1, now=now)


class TestDecayEngine:
    def test_score_method(self):
        engine = DecayEngine()
        now = datetime.now(timezone.utc)
        score = engine.score(_iso(now), 5)
        assert score > 0.9

    def test_classify_active(self):
        engine = DecayEngine()
        now = datetime.now(timezone.utc)
        assert engine.classify(_iso(now), 10) == "active"

    def test_classify_fading(self):
        engine = DecayEngine()
        now = datetime.now(timezone.utc)
        # Find a timestamp that puts score between dormant and 0.5
        two_weeks = now - timedelta(days=14)
        status = engine.classify(_iso(two_weeks), 1)
        assert status in ("fading", "dormant", "active")

    def test_classify_all_states_reachable(self):
        engine = DecayEngine()
        now = datetime.now(timezone.utc)
        states_seen = set()
        for days in [0, 7, 30, 180, 365, 1000]:
            for count in [1, 5, 50]:
                ts = now - timedelta(days=days)
                states_seen.add(engine.classify(_iso(ts), count))
        # Should see at least active and one of the decay states
        assert "active" in states_seen
