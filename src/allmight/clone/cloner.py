"""Project Cloner — create a read-only clone with symlinked workspaces.

The clone's knowledge_graph/ entries are symlinks pointing to the source
project's workspaces.  The clone is always read-only (no ingest/enrich).
Memory is fresh (not copied from source).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from ..core.domain import CloneReport


def _is_allmight_project(root: Path) -> bool:
    """Check if a directory is an All-Might project."""
    return (root / "knowledge_graph").is_dir() or (root / ".allmight").is_dir()


class ProjectCloner:
    """Clone an existing All-Might project with symlinked workspaces."""

    def clone(self, source: Path, target: Path) -> CloneReport:
        """Clone source All-Might project into target directory.

        Args:
            source: Path to an existing All-Might project.
            target: Path to the clone destination (may already exist).

        Returns:
            CloneReport with summary of what was linked.

        Raises:
            ValueError: If source is not an All-Might project.
        """
        if not _is_allmight_project(source):
            raise ValueError(f"'{source}' is not an All-Might project")

        report = CloneReport(
            source=str(source),
            target=str(target),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # 1. Create target directory structure
        target.mkdir(parents=True, exist_ok=True)

        # 2. Symlink workspaces
        self._link_workspaces(source, target, report)

        # 3. Build manifest for the target and initialize (read-only)
        self._initialize_target(source, target)

        # 4. Write provenance
        allmight_dir = target / ".allmight"
        allmight_dir.mkdir(exist_ok=True)
        (allmight_dir / "clone-source").write_text(str(source) + "\n")

        return report

    def _link_workspaces(
        self, source: Path, target: Path, report: CloneReport,
    ) -> None:
        """Create symlinks in target/knowledge_graph/ for each source workspace."""
        source_kg = source / "knowledge_graph"
        target_kg = target / "knowledge_graph"
        target_kg.mkdir(parents=True, exist_ok=True)

        if not source_kg.is_dir():
            return

        for ws_dir in sorted(source_kg.iterdir()):
            if not ws_dir.is_dir():
                continue
            # Only link workspaces that have a config.yaml (valid SMAK workspaces)
            # or are directories (may be partially set up)
            target_link = target_kg / ws_dir.name
            if not target_link.exists():
                os.symlink(str(ws_dir.resolve()), str(target_link))
                report.workspaces_linked.append(ws_dir.name)

    def _initialize_target(self, source: Path, target: Path) -> None:
        """Run ProjectInitializer + MemoryInitializer on the target (read-only)."""
        from ..personalities.corpus_keeper.initializer import ProjectInitializer
        from ..personalities.corpus_keeper.scanner import ProjectScanner
        from ..personalities.memory_keeper.initializer import MemoryInitializer

        # Scan the source to get manifest info, then retarget to clone
        scanner = ProjectScanner()
        manifest = scanner.scan(source)
        manifest.root_path = target

        # Initialize in read-only mode
        ProjectInitializer().initialize(manifest, writable=False)
        MemoryInitializer().initialize(target)
