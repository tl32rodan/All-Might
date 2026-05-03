"""Git-as-hub transport for personality bundles.

Two operations:

* :func:`publish_bundle` — take an existing bundle dir (produced by
  ``/export``) and push it to a git URL.
* :func:`pull_to_temp` — clone a git URL to a temp dir so the caller
  can run ``allmight import`` against the cloned tree.

The All-Might side cares only that ``git`` exists on PATH. Auth,
network reachability, and credentials are the user's environment's
problem; subprocess errors propagate up.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_UPSTREAM_FILE = ".allmight/upstream.yaml"


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


class GitShareError(RuntimeError):
    """Raised when a git subprocess returns non-zero."""


def _run_git(args: list[str], cwd: Path | None = None) -> str:
    """Run ``git <args>`` and return stdout. Raises on non-zero exit."""
    cmd = ["git", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise GitShareError(
            "git executable not found on PATH",
        ) from exc
    if proc.returncode != 0:
        raise GitShareError(
            f"git {' '.join(args)} failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout


def _local_path_from_url(url: str) -> Path | None:
    """If *url* is a local filesystem path or ``file://`` URL, return
    the corresponding ``Path``. Otherwise return ``None``."""
    if url.startswith("file://"):
        return Path(url[len("file://"):])
    # Heuristic: an absolute path or a path starting with ``./`` / ``../``.
    if url.startswith(("/", "./", "../")):
        return Path(url)
    return None


def _ensure_local_bare_repo(url: str) -> None:
    """If *url* is a local bare repo path that doesn't yet exist,
    init one. Pure no-op for remote URLs.

    Filesystem permission errors (parent dir not writable, etc.) are
    caught and re-raised as :class:`GitShareError` so the CLI's
    error-handling path can convert them into a clean exit code.
    """
    local = _local_path_from_url(url)
    if local is None:
        return
    if (local / "HEAD").exists():
        return  # already a bare repo
    if local.exists() and any(local.iterdir()):
        # Exists with content but not a bare repo: do not touch it.
        raise GitShareError(
            f"local path {local} exists but is not a bare git repo"
        )
    try:
        local.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise GitShareError(
            f"cannot create bare repo at {local}: {exc}"
        ) from exc
    _run_git(["init", "--bare", "--initial-branch=main"], cwd=local)


# ---------------------------------------------------------------------------
# Upstream tracking
# ---------------------------------------------------------------------------


@dataclass
class UpstreamRecord:
    """A row in ``.allmight/upstream.yaml``."""

    upstream: str = ""
    last_published_bundle_id: str = ""
    last_published_at: str = ""
    last_pulled_bundle_id: str = ""
    last_pulled_at: str = ""

    def to_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {}
        if self.upstream:
            row["upstream"] = self.upstream
        if self.last_published_bundle_id:
            row["last_published_bundle_id"] = self.last_published_bundle_id
        if self.last_published_at:
            row["last_published_at"] = self.last_published_at
        if self.last_pulled_bundle_id:
            row["last_pulled_bundle_id"] = self.last_pulled_bundle_id
        if self.last_pulled_at:
            row["last_pulled_at"] = self.last_pulled_at
        return row


def read_upstream(project_root: Path) -> dict[str, UpstreamRecord]:
    """Load ``.allmight/upstream.yaml``. Returns ``{name: record}``."""
    path = project_root / _UPSTREAM_FILE
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    raw = data.get("personalities") or {}
    out: dict[str, UpstreamRecord] = {}
    for name, row in raw.items():
        if not isinstance(row, dict):
            continue
        out[name] = UpstreamRecord(
            upstream=row.get("upstream", ""),
            last_published_bundle_id=row.get(
                "last_published_bundle_id", "",
            ),
            last_published_at=row.get("last_published_at", ""),
            last_pulled_bundle_id=row.get("last_pulled_bundle_id", ""),
            last_pulled_at=row.get("last_pulled_at", ""),
        )
    return out


def write_upstream(
    project_root: Path, records: dict[str, UpstreamRecord],
) -> None:
    """Persist ``.allmight/upstream.yaml``."""
    path = project_root / _UPSTREAM_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "personalities": {
            name: rec.to_row() for name, rec in sorted(records.items())
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


# ---------------------------------------------------------------------------
# Publish / pull
# ---------------------------------------------------------------------------


@dataclass
class PublishResult:
    bundle_id: str = ""
    upstream: str = ""
    pushed_to_branch: str = "main"
    files_pushed: int = 0


def publish_bundle(
    bundle_dir: Path,
    git_url: str,
    *,
    message: str | None = None,
    branch: str = "main",
) -> PublishResult:
    """Push *bundle_dir* (a directory produced by ``/export``) to *git_url*.

    The bundle is copied into a fresh clone of the remote, committed,
    and pushed to *branch*. If the remote is a local bare-repo path
    that doesn't yet exist, it is created with ``git init --bare``.

    Returns a :class:`PublishResult` summarising what was pushed.
    Raises :class:`GitShareError` on any git subprocess failure.
    """
    bundle_dir = Path(bundle_dir).resolve()
    if not (bundle_dir / "manifest.yaml").is_file():
        raise GitShareError(
            f"{bundle_dir} is not a valid bundle (no manifest.yaml)"
        )

    manifest = (
        yaml.safe_load((bundle_dir / "manifest.yaml").read_text()) or {}
    )
    bundle_id = str(manifest.get("bundle_id") or "")

    _ensure_local_bare_repo(git_url)

    with tempfile.TemporaryDirectory(prefix="allmight-share-") as tmp:
        work = Path(tmp) / "work"
        # ``git clone`` of an empty bare repo prints a warning but
        # still succeeds and leaves us with a working tree on
        # ``main`` (per the bare repo's ``init.defaultBranch``).
        _run_git(["clone", git_url, str(work)])

        # Copy the bundle's contents on top of whatever was in the
        # remote (which may be empty for a first publish, or the
        # previous bundle for an update). ``shutil.copytree`` with
        # dirs_exist_ok handles both cases.
        # We deliberately wipe everything except ``.git/`` first so a
        # file removed from the new bundle gets removed from upstream
        # too.
        for child in work.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        shutil.copytree(bundle_dir, work, dirs_exist_ok=True)
        # Remove an accidentally-copied .git dir from inside the
        # bundle (defensive — bundles shouldn't have one).
        nested_git = work / ".git"
        if nested_git.is_dir() and not (nested_git / "config").exists():
            shutil.rmtree(nested_git)

        # Counting files for the result summary.
        files_pushed = sum(
            1 for _ in work.rglob("*")
            if _.is_file() and ".git/" not in str(_)
        )

        # Detect "no changes" up front: if the working tree is clean
        # against HEAD, ``git commit`` would fail. We treat the call
        # as a no-op in that case (push still runs to keep the call
        # idempotent against transient remote rewrites).
        _run_git(["add", "-A"], cwd=work)
        status = _run_git(["status", "--porcelain"], cwd=work).strip()

        if status:
            commit_msg = (
                message
                or f"publish bundle {bundle_id or '(no id)'}"
            )
            _run_git(
                ["commit", "-m", commit_msg],
                cwd=work,
            )

        # Push (force-with-lease for safety if branch already exists,
        # plain push if not). For first-time publish the branch may
        # not exist on the remote yet; fall back to plain push.
        try:
            _run_git(
                ["push", "origin", f"HEAD:{branch}"],
                cwd=work,
            )
        except GitShareError:
            # Retry without --force; second failure surfaces.
            _run_git(
                ["push", "--set-upstream", "origin", f"HEAD:{branch}"],
                cwd=work,
            )

    return PublishResult(
        bundle_id=bundle_id,
        upstream=git_url,
        pushed_to_branch=branch,
        files_pushed=files_pushed,
    )


def pull_to_temp(git_url: str, dest: Path) -> Path:
    """Clone *git_url* into *dest*. Returns the resolved destination.

    Raises :class:`GitShareError` on subprocess failure.
    """
    dest = Path(dest).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["clone", "--depth", "1", git_url, str(dest)])
    return dest
