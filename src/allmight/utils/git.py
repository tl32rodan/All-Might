"""Git repository introspection + bookkeeping utilities.

Two responsibilities:

* Read-only introspection used by the enrichment planner
  (``get_repo_name``, ``is_git_repo``, ``get_file_commit_count``).
* ``run_git``: a shared subprocess wrapper for All-Might's own
  bookkeeping repos (``share/git_share.py`` for bundle transport,
  ``memory/history.py`` for the memory recovery mirror). Both
  scenarios commit programmatically and must never trigger
  user-level GPG signing — see :func:`run_git` for the contract.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    """Raised by :func:`run_git` when a git subprocess returns non-zero."""


def run_git(args: list[str], cwd: Path | None = None) -> str:
    """Run ``git <args>`` and return stdout. Raises :class:`GitError` on non-zero.

    All-Might's bookkeeping commits (bundle publish, memory-history
    snapshots) are not user-authored content; they must never be
    GPG-signed regardless of the host's global ``commit.gpgsign``
    setting. Hosts that enforce signing via an external signer
    (sandboxes, hardware tokens, corporate CI) would otherwise fail
    every internal ``git commit``. This wrapper injects
    ``-c commit.gpgsign=false -c tag.gpgsign=false`` for every
    invocation — harmless for read-only commands, and the only way
    to opt out of a global ``true``.
    """
    cmd = [
        "git",
        "-c", "commit.gpgsign=false",
        "-c", "tag.gpgsign=false",
        *args,
    ]
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
        raise GitError("git executable not found on PATH") from exc
    if proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout


def get_repo_name(path: Path) -> str | None:
    """Extract repository name from git remote or directory name."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Handle both HTTPS and SSH URLs
            name = url.rstrip("/").rsplit("/", 1)[-1]
            return name.removesuffix(".git")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return path.name


def is_git_repo(path: Path) -> bool:
    """Check if a path is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_file_commit_count(path: Path, file_path: str) -> int:
    """Get the number of commits that touched a specific file."""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD", "--", file_path],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return 0
