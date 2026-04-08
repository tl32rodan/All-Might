"""Git repository introspection utilities.

Used by the enrichment planner to prioritize symbols by commit frequency.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


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
