"""Tests for WorkingMemoryManager (Layer 1)."""

from pathlib import Path

import pytest

from allmight.memory.working import WorkingMemoryManager, SECTIONS, _estimate_tokens


@pytest.fixture
def tmp_root(tmp_path):
    """Create a temporary project root with config.yaml."""
    (tmp_path / "config.yaml").write_text("project:\n  name: test\n")
    return tmp_path


@pytest.fixture
def manager(tmp_root):
    return WorkingMemoryManager(tmp_root, budget=4000)


class TestInitialize:
    def test_creates_directory_and_file(self, manager, tmp_root):
        manager.initialize()
        assert (tmp_root / "memory" / "working" / "MEMORY.md").exists()

    def test_empty_sections_after_init(self, manager):
        manager.initialize()
        sections = manager.read()
        for section in SECTIONS:
            assert section in sections
            assert sections[section] == ""


class TestReadWrite:
    def test_update_and_read_section(self, manager):
        manager.initialize()
        manager.update("user_model", "Prefers concise answers")
        assert manager.read_section("user_model") == "Prefers concise answers"

    def test_update_preserves_other_sections(self, manager):
        manager.initialize()
        manager.update("user_model", "User info")
        manager.update("environment", "Python 3.11")

        sections = manager.read()
        assert sections["user_model"] == "User info"
        assert sections["environment"] == "Python 3.11"

    def test_clear_section(self, manager):
        manager.initialize()
        manager.update("active_goals", "Ship v2")
        manager.clear_section("active_goals")
        assert manager.read_section("active_goals") == ""

    def test_invalid_section_raises(self, manager):
        manager.initialize()
        with pytest.raises(ValueError, match="Unknown section"):
            manager.update("nonexistent", "data")

    def test_read_section_invalid_raises(self, manager):
        manager.initialize()
        with pytest.raises(ValueError, match="Unknown section"):
            manager.read_section("bad_section")


class TestRender:
    def test_render_includes_all_sections(self, manager):
        manager.initialize()
        manager.update("user_model", "Test user")
        rendered = manager.render()
        assert "## User Model" in rendered
        assert "Test user" in rendered
        assert "## Environment Facts" in rendered
        assert "## Active Goals" in rendered
        assert "## Pinned Memories" in rendered

    def test_render_includes_timestamp(self, manager):
        manager.initialize()
        rendered = manager.render()
        assert "_Last updated:" in rendered


class TestBudget:
    def test_token_usage_zero_when_empty(self, manager):
        manager.initialize()
        # Non-zero because of headers/markers
        usage = manager.token_usage()
        assert usage > 0
        assert usage < 200  # Headers alone shouldn't be huge

    def test_is_over_budget(self, tmp_root):
        mgr = WorkingMemoryManager(tmp_root, budget=10)
        mgr.initialize()
        mgr.update("user_model", "A" * 100)
        assert mgr.is_over_budget()

    def test_not_over_budget(self, manager):
        manager.initialize()
        manager.update("user_model", "Short text")
        assert not manager.is_over_budget()

    def test_budget_status_structure(self, manager):
        manager.initialize()
        status = manager.budget_status()
        assert "tokens_used" in status
        assert "budget" in status
        assert "remaining" in status
        assert "over_budget" in status


class TestEstimateTokens:
    def test_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_single_word(self):
        tokens = _estimate_tokens("hello")
        assert tokens >= 1

    def test_longer_text(self):
        text = "This is a test sentence with several words in it"
        tokens = _estimate_tokens(text)
        assert tokens > 5


class TestReadBeforeInit:
    def test_read_returns_empty_sections_when_no_file(self, tmp_root):
        mgr = WorkingMemoryManager(tmp_root)
        sections = mgr.read()
        for s in SECTIONS:
            assert sections[s] == ""

    def test_token_usage_zero_when_no_file(self, tmp_root):
        mgr = WorkingMemoryManager(tmp_root)
        assert mgr.token_usage() == 0
