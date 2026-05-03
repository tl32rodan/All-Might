"""Sanity tests for Part-E documentation.

These don't validate prose quality — they only ensure the docs exist
and reference the right concepts so a content drift between code and
docs gets caught at CI time.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_team_share_doc_exists() -> None:
    assert (REPO_ROOT / "docs" / "team-share.md").is_file()


@pytest.mark.parametrize("token", [
    # Core concepts and patterns
    "Bundle share",
    "Instance share",
    "lessons_learned",
    "database_subscriptions",
    "bundle_id",
    "atomic-rename",
    "Single-writer",
    "share publish",
    "share pull",
    # Part-F naming aliases (must be discoverable from the doc)
    "/one-for-all",
    "all-for-one",
    "Scenario A",
    "Scenario B",
    "Scenario C",
])
def test_team_share_doc_covers_core_concepts(token: str) -> None:
    body = (REPO_ROOT / "docs" / "team-share.md").read_text()
    assert token in body, (
        f"docs/team-share.md should reference '{token}'"
    )


def test_readme_links_to_team_share_doc() -> None:
    body = (REPO_ROOT / "README.md").read_text()
    assert "docs/team-share.md" in body
    assert "Team Share" in body
    assert "share publish" in body
    assert "share pull" in body


def test_personalities_doc_cross_references_team_share() -> None:
    body = (REPO_ROOT / "docs" / "personalities.md").read_text()
    assert "team-share.md" in body
