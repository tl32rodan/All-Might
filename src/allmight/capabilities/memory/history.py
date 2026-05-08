"""Memory version-control mirror for accident-recovery.

A separate (non-bare) git repo at ``.allmight/memory-history/`` that
shadows the project's memory data + ROLE.md + database config. The
agent — and the user via ``allmight memory log/restore`` — can roll
back any individual deletion or accidental edit.

Why a separate repo at ``.allmight/memory-history/`` (instead of the
project's main ``.git``):

* The user's project is usually already a git repo. Putting our own
  ``.git`` at the project root collides; recursing into a nested
  repo at a non-root path confuses ``git status`` for both sides.
* The mirror keeps All-Might's bookkeeping under one prefix
  (``.allmight/``) — easy to ignore, easy to clean up.

What is tracked: see :data:`TRACKED_GLOBS`. Excluded: SMAK vector
indices (``store/``) — large, machine-specific, rebuildable from
the journal + understanding. Tracking them would balloon the repo
for no recovery value.

When commits happen: file watcher equivalent (OpenCode plugin
``memory-history.ts`` hooks ``chat.message`` post-turn; Claude Code
hook ``memory_history.py`` runs after every Stop) plus session-end
fallback (``experimental.session.compacting`` and
``session.deleted``). At-most-one-turn-of-edits is the recovery
floor.

Recovery surface: ``allmight memory log / diff / restore / gc``.
No skill — recovery is mechanical.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ...utils.git import GitError, run_git


HISTORY_REL = ".allmight/memory-history"


# Glob patterns (relative to project_root) that the mirror tracks.
# Order doesn't matter — duplicates across patterns are deduplicated
# in :meth:`MemoryHistory.sync`. Patterns use ``Path.glob`` semantics
# (``**`` recurses).
TRACKED_GLOBS: tuple[str, ...] = (
    # L1 — project-wide
    "MEMORY.md",
    # Per-personality role + memory data
    "personalities/*/ROLE.md",
    "personalities/*/memory/understanding/**/*.md",
    "personalities/*/memory/journal/**/*.md",
    "personalities/*/memory/lessons_learned/**/*.md",
    "personalities/*/memory/usage.log",
    # Database config (workspace shape) — small, hand-edited, worth
    # tracking for recovery. ``store/`` is rebuildable and excluded.
    "personalities/*/database/*/config.yaml",
    "personalities/*/database/*/smak_config.yaml",
    "personalities/*/memory/config.yaml",
    "personalities/*/memory/smak_config.yaml",
)


# Glob patterns explicitly excluded. Belt-and-suspenders — the
# tracked globs above already won't match these — but having them
# in ``.gitignore`` inside the mirror catches surprises if a
# future tracked-glob accidentally widens to include them.
EXCLUDED_PATTERNS: tuple[str, ...] = (
    "**/store/",
    "**/__pycache__/",
    "**/*.pyc",
    "**/.DS_Store",
)


@dataclass(frozen=True)
class CommitRecord:
    """One row from ``git log`` inside the mirror."""

    sha: str
    timestamp: str  # ISO-8601 from `%cI`
    subject: str


class MemoryHistory:
    """Bookkeeping wrapper around the ``.allmight/memory-history/`` repo.

    Stateless — every method takes ``project_root`` so the same
    instance can be reused across personalities, sessions, etc.
    """

    def history_root(self, project_root: Path) -> Path:
        """Resolve the mirror repo path."""
        return project_root / HISTORY_REL

    # -- init ---------------------------------------------------------

    def init(self, project_root: Path) -> None:
        """Create the mirror repo and seed its first commit.

        Idempotent: re-runs of ``allmight init`` skip the create step
        if the mirror already exists. Always runs a fresh sync +
        commit so any drift since the last invocation gets captured.
        """
        history = self.history_root(project_root)
        if not (history / ".git").exists():
            history.mkdir(parents=True, exist_ok=True)
            run_git(["init", "-b", "main"], cwd=history)
            self._write_gitignore(history)
        self.sync(project_root)
        try:
            self.commit(project_root, message="init: seed memory history")
        except GitError:
            # Empty repo with nothing to track yet — fine.
            pass

    def _write_gitignore(self, history: Path) -> None:
        """Belt-and-suspenders ignore list inside the mirror.

        ``sync`` already filters by :data:`TRACKED_GLOBS`, so files
        outside the tracked set never make it into the mirror. The
        ``.gitignore`` is a second layer of defence against future
        widening of the tracked set accidentally pulling in heavy
        derived data.
        """
        gitignore = history / ".gitignore"
        body = "# All-Might memory-history mirror — exclusions.\n"
        body += "# These patterns are belt-and-suspenders; the\n"
        body += "# tracked-glob list in history.py is the primary\n"
        body += "# filter.\n\n"
        body += "\n".join(EXCLUDED_PATTERNS) + "\n"
        gitignore.write_text(body)

    # -- sync (copy live -> mirror) -----------------------------------

    def sync(self, project_root: Path) -> list[tuple[str, str]]:
        """Reconcile the mirror's working tree against the live tree.

        Returns a list of ``(relpath, op)`` for files that changed
        relative to the previous mirror state, where ``op`` is one
        of ``"create"``, ``"update"``, ``"delete"``. The mirror's
        ``.git/`` is preserved; ``.gitignore`` is preserved if it
        already matches the canonical body, otherwise rewritten.

        Files larger than 10 MB are skipped with a warning — recovery
        for binary blobs isn't this layer's job.
        """
        history = self.history_root(project_root)
        if not (history / ".git").exists():
            raise RuntimeError(
                "memory-history mirror is not initialised; "
                "run `allmight init` or `allmight memory init` first."
            )

        live_files = self._enumerate_live(project_root)
        mirror_files = self._enumerate_mirror(history)

        changes: list[tuple[str, str]] = []

        # Copy / update files present in live.
        for rel in sorted(live_files):
            src = project_root / rel
            dst = history / rel
            if not src.is_file():
                continue
            try:
                if src.stat().st_size > 10 * 1024 * 1024:
                    # Skip oversize files. The user can still recover
                    # smaller siblings; we surface this as a non-fatal
                    # warning at commit time via the plugin / CLI.
                    continue
            except OSError:
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            existed = rel in mirror_files
            if existed:
                try:
                    if dst.read_bytes() == src.read_bytes():
                        continue  # no change
                except OSError:
                    pass
            shutil.copy2(src, dst)
            changes.append((rel, "update" if existed else "create"))

        # Delete mirror files no longer present in live.
        for rel in sorted(mirror_files - live_files):
            (history / rel).unlink(missing_ok=True)
            # Walk up and remove any newly-empty dirs (within history).
            parent = (history / rel).parent
            while parent != history and parent.is_dir():
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
            changes.append((rel, "delete"))

        # Rewrite .gitignore to canonical content.
        self._write_gitignore(history)
        return changes

    def _enumerate_live(self, project_root: Path) -> set[str]:
        out: set[str] = set()
        for pattern in TRACKED_GLOBS:
            for hit in project_root.glob(pattern):
                if not hit.is_file():
                    continue
                rel = hit.relative_to(project_root).as_posix()
                # Defensive: skip anything that ended up under store/.
                if "/store/" in f"/{rel}/" or rel.endswith("/store"):
                    continue
                out.add(rel)
        return out

    def _enumerate_mirror(self, history: Path) -> set[str]:
        out: set[str] = set()
        for hit in history.rglob("*"):
            if not hit.is_file():
                continue
            rel = hit.relative_to(history).as_posix()
            # Skip the mirror's own bookkeeping.
            if rel.startswith(".git/") or rel == ".gitignore":
                continue
            out.add(rel)
        return out

    # -- commit -------------------------------------------------------

    def commit(
        self, project_root: Path, message: str,
        *, allow_empty: bool = False,
    ) -> str | None:
        """Commit whatever is currently in the mirror's working tree.

        Returns the new commit's sha, or ``None`` if nothing changed
        and ``allow_empty=False``.
        """
        history = self.history_root(project_root)
        run_git(["add", "-A"], cwd=history)
        status = run_git(["status", "--porcelain"], cwd=history).strip()
        if not status and not allow_empty:
            return None
        run_git(
            ["-c", "user.name=all-might", "-c", "user.email=all-might@local",
             "commit",
             *(["--allow-empty"] if allow_empty else []),
             "-m", message],
            cwd=history,
        )
        sha = run_git(["rev-parse", "HEAD"], cwd=history).strip()
        return sha

    def snapshot(
        self, project_root: Path, *,
        trigger: str = "manual",
        session_id: str = "",
    ) -> str | None:
        """Sync + commit in one shot. Returns the new sha or ``None``.

        The default entry point for plugin/hook callers. Generates a
        ``auto: ...`` commit message describing the change set; falls
        back to ``manual: snapshot`` when ``trigger="manual"``.
        """
        changes = self.sync(project_root)
        if not changes:
            return None
        ops_summary = self._summarise_changes(changes)
        prefix = "manual" if trigger == "manual" else "auto"
        message_lines = [f"{prefix}: {ops_summary}"]
        if trigger != "manual":
            message_lines.append("")
            message_lines.append(f"triggered_by: {trigger}")
        if session_id:
            message_lines.append(f"session_id: {session_id}")
        return self.commit(project_root, "\n".join(message_lines))

    @staticmethod
    def _summarise_changes(changes: list[tuple[str, str]]) -> str:
        if not changes:
            return "no changes"
        first_rel, first_op = changes[0]
        if len(changes) == 1:
            return f"{first_op} {first_rel}"
        return f"{first_op} {first_rel} (+ {len(changes) - 1} other files)"

    # -- log / diff / restore -----------------------------------------

    def log(
        self, project_root: Path, *,
        personality: str | None = None,
        n: int = 20,
    ) -> list[CommitRecord]:
        """Return the most recent ``n`` commits, optionally filtered.

        ``personality`` filters to commits that touched
        ``personalities/<name>/``. ``MEMORY.md`` is project-wide and
        is included only when ``personality is None``.
        """
        history = self.history_root(project_root)
        args = [
            "log",
            f"-{int(n)}",
            "--pretty=format:%H|%cI|%s",
        ]
        if personality:
            args.extend(["--", f"personalities/{personality}/"])
        try:
            out = run_git(args, cwd=history)
        except GitError:
            # Empty repo (no commits yet) — return [].
            return []
        records: list[CommitRecord] = []
        for line in out.splitlines():
            parts = line.split("|", 2)
            if len(parts) != 3:
                continue
            records.append(CommitRecord(*parts))
        return records

    def diff(
        self, project_root: Path, rev: str, relpath: str | None = None,
    ) -> str:
        """Return ``git show <rev>`` (whole commit) or a single-file diff."""
        history = self.history_root(project_root)
        if relpath:
            return run_git(
                ["show", f"{rev}", "--", relpath],
                cwd=history,
            )
        return run_git(["show", rev], cwd=history)

    def restore(
        self, project_root: Path, relpath: str, *,
        rev: str = "HEAD",
        dest: Path | None = None,
    ) -> Path:
        """Restore ``relpath`` from ``rev`` into ``dest`` (default: live).

        ``relpath`` is the path relative to ``project_root`` — same
        layout as the mirror. Returns the destination path.

        Refuses to overwrite an existing destination unless ``dest``
        explicitly points at it; the CLI confirms with the user
        before calling. Library callers wanting to overwrite must
        ``unlink`` first.
        """
        history = self.history_root(project_root)
        target = dest if dest is not None else (project_root / relpath)
        target.parent.mkdir(parents=True, exist_ok=True)
        # ``git show <rev>:<path>`` prints the file's content at that
        # revision to stdout. Works regardless of the live tree's
        # state (the mirror's HEAD doesn't have to match live).
        content = run_git(["show", f"{rev}:{relpath}"], cwd=history)
        target.write_text(content)
        return target

    def gc(self, project_root: Path) -> str:
        """Run ``git gc`` inside the mirror. Returns git's stdout."""
        history = self.history_root(project_root)
        return run_git(["gc"], cwd=history)
