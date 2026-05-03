"""Tests for Part-E share commands and the underlying git transport.

All tests use a local bare repo + ``file://`` URL so nothing leaves
the box.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from allmight.cli import main
from allmight.share.git_share import (
    GitShareError,
    publish_bundle,
    read_upstream,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure git has an author identity in CI / fresh sandboxes.

    Tests run in temp dirs so the user's global config is enough on
    a developer box, but CI runners often lack one. Setting env vars
    is the most isolated way (no global config side effects).
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "all-might-test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "all-might-test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "all-might-test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "all-might-test@example.com")


def _invoke_in(root: Path, args: list[str]):
    runner = CliRunner()
    cwd = os.getcwd()
    try:
        os.chdir(root)
        return runner.invoke(main, args, catch_exceptions=False)
    finally:
        os.chdir(cwd)


@pytest.fixture
def initted_project(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("def f(): pass\n")
    (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--yes", str(project)])
    assert result.exit_code == 0, result.output
    return project


@pytest.fixture
def sample_bundle(tmp_path: Path) -> Path:
    """A minimal valid bundle directory for share publish."""
    bundle = tmp_path / "stdcell_owner-export"
    bundle.mkdir()
    manifest = {
        "allmight_version": "0.1.0",
        "schema_version": 2,
        "personality_name": "stdcell_owner",
        "bundle_id": "11111111-2222-3333-4444-555555555555",
        "bundle_version": "0.1.0",
        "derived_from": [],
        "capabilities": {
            "database": {"capability_version": "1.0.0"},
            "memory": {"capability_version": "1.0.0"},
        },
    }
    (bundle / "manifest.yaml").write_text(yaml.safe_dump(manifest))
    (bundle / "ROLE.md").write_text(
        "<!-- all-might generated -->\n# stdcell_owner\nRole.\n",
    )
    (bundle / "database").mkdir()
    (bundle / "memory").mkdir()
    (bundle / "memory" / "understanding").mkdir()
    (bundle / "memory" / "understanding" / "stdcell.md").write_text(
        "<!-- all-might generated -->\n# stdcell\nNotes.\n",
    )
    return bundle


@pytest.fixture
def bare_repo_url(tmp_path: Path) -> str:
    """A local bare repo URL that publish_bundle initialises on demand."""
    return f"file://{tmp_path}/team-share.git"


# ---------------------------------------------------------------------------
# Library-level: publish_bundle / read_upstream
# ---------------------------------------------------------------------------


class TestPublishBundleLibrary:
    def test_publish_to_uninitialised_local_creates_bare_repo(
        self, sample_bundle: Path, tmp_path: Path,
    ) -> None:
        url = f"file://{tmp_path}/team.git"
        result = publish_bundle(sample_bundle, url, message="initial")
        assert result.bundle_id == \
            "11111111-2222-3333-4444-555555555555"
        # Bare repo created.
        bare = tmp_path / "team.git"
        assert (bare / "HEAD").is_file()
        # And it has at least one commit.
        log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(bare),
            capture_output=True,
            text=True,
            check=True,
        )
        assert log.stdout.strip(), "bare repo should have a commit"

    def test_publish_then_clone_yields_same_bundle(
        self, sample_bundle: Path, tmp_path: Path,
    ) -> None:
        url = f"file://{tmp_path}/team.git"
        publish_bundle(sample_bundle, url)
        clone_dest = tmp_path / "clone"
        subprocess.run(
            ["git", "clone", url, str(clone_dest)],
            check=True, capture_output=True,
        )
        # manifest + ROLE + memory understanding round-trip.
        cloned_manifest = yaml.safe_load(
            (clone_dest / "manifest.yaml").read_text()
        )
        assert cloned_manifest["personality_name"] == "stdcell_owner"
        assert cloned_manifest["bundle_id"] == \
            "11111111-2222-3333-4444-555555555555"
        assert (clone_dest / "ROLE.md").is_file()
        assert (clone_dest / "memory" / "understanding" / "stdcell.md").is_file()

    def test_publish_rejects_dir_without_manifest(
        self, tmp_path: Path,
    ) -> None:
        empty = tmp_path / "not-a-bundle"
        empty.mkdir()
        with pytest.raises(GitShareError):
            publish_bundle(empty, f"file://{tmp_path}/team.git")

    def test_publish_overrides_remote_on_second_push(
        self, sample_bundle: Path, tmp_path: Path,
    ) -> None:
        url = f"file://{tmp_path}/team.git"
        publish_bundle(sample_bundle, url, message="v1")

        # Modify the bundle (simulate a second /export with new
        # content) and re-publish.
        (sample_bundle / "ROLE.md").write_text(
            "<!-- all-might generated -->\n# stdcell_owner\nUpdated.\n",
        )
        publish_bundle(sample_bundle, url, message="v2")

        clone_dest = tmp_path / "clone"
        subprocess.run(
            ["git", "clone", url, str(clone_dest)],
            check=True, capture_output=True,
        )
        assert "Updated." in (clone_dest / "ROLE.md").read_text()


# ---------------------------------------------------------------------------
# CLI: allmight share publish / pull
# ---------------------------------------------------------------------------


class TestShareCli:
    def test_publish_records_upstream(
        self, initted_project: Path, sample_bundle: Path,
        bare_repo_url: str,
    ) -> None:
        result = _invoke_in(
            initted_project,
            ["share", "publish", str(sample_bundle), "--to", bare_repo_url],
        )
        assert result.exit_code == 0, result.output
        # Upstream YAML written.
        records = read_upstream(initted_project)
        assert "stdcell_owner" in records
        rec = records["stdcell_owner"]
        assert rec.upstream == bare_repo_url
        assert rec.last_published_bundle_id == \
            "11111111-2222-3333-4444-555555555555"
        assert rec.last_published_at

    def test_publish_to_bad_url_errors(
        self, initted_project: Path, sample_bundle: Path,
    ) -> None:
        result = _invoke_in(
            initted_project,
            ["share", "publish", str(sample_bundle),
             "--to", "file:///nonexistent/path/cant/init/here.git"],
        )
        # Either the init or the push should fail; either way exit
        # non-zero.
        assert result.exit_code != 0

    def test_pull_round_trip_imports_personality(
        self, initted_project: Path, sample_bundle: Path,
        bare_repo_url: str, tmp_path: Path,
    ) -> None:
        # First publish from an arbitrary working dir (use sample_bundle's
        # parent as a stand-in project).
        publish_bundle(sample_bundle, bare_repo_url)
        # Now pull from the receiver.
        result = _invoke_in(
            initted_project,
            ["share", "pull", bare_repo_url],
        )
        assert result.exit_code == 0, result.output
        target = initted_project / "personalities" / "stdcell_owner"
        assert (target / "ROLE.md").is_file()
        # Lineage propagated.
        registry = yaml.safe_load(
            (initted_project / ".allmight" / "personalities.yaml").read_text()
        )
        rows = [r for r in registry["personalities"]
                if (r.get("name") or r.get("instance")) == "stdcell_owner"]
        assert rows[0]["imported_from_bundle_id"] == \
            "11111111-2222-3333-4444-555555555555"
        # Upstream YAML records the pull.
        records = read_upstream(initted_project)
        assert records["stdcell_owner"].last_pulled_bundle_id == \
            "11111111-2222-3333-4444-555555555555"
        assert records["stdcell_owner"].upstream == bare_repo_url

    def test_pull_with_as_renames_target(
        self, initted_project: Path, sample_bundle: Path,
        bare_repo_url: str,
    ) -> None:
        publish_bundle(sample_bundle, bare_repo_url)
        result = _invoke_in(
            initted_project,
            ["share", "pull", bare_repo_url, "--as", "stdcell_v2"],
        )
        assert result.exit_code == 0, result.output
        assert (
            initted_project / "personalities" / "stdcell_v2" / "ROLE.md"
        ).is_file()
        records = read_upstream(initted_project)
        assert "stdcell_v2" in records

    def test_publish_outside_allmight_project_errors(
        self, sample_bundle: Path, tmp_path: Path, bare_repo_url: str,
    ) -> None:
        loose = tmp_path / "loose"
        loose.mkdir()
        result = _invoke_in(
            loose,
            ["share", "publish", str(sample_bundle), "--to", bare_repo_url],
        )
        assert result.exit_code != 0
