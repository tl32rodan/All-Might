"""Project Merger — combine knowledge bases from separate All-Might projects.

Copies workspaces and memory from a source project into the target.
Conflicts produce ``.incoming`` suffixes for agent-driven resolution
via ``/sync``.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..core.domain import MergeReport
from ..utils.links import add_link, load_links_manifest
from .path_rewriter import PathRewriter


def _is_allmight_project(root: Path) -> bool:
    """Check if a directory is an All-Might project."""
    return (root / "knowledge_graph").is_dir() or (root / ".allmight").is_dir()


class ProjectMerger:
    """Merge knowledge bases from one All-Might project into another."""

    def __init__(self) -> None:
        self._rewriter = PathRewriter()

    def merge(
        self,
        source: Path,
        target: Path,
        workspaces: list[str] | None = None,
        dry_run: bool = False,
        no_memory: bool = False,
        copy_links: bool = False,
    ) -> MergeReport:
        """Merge source project into target.

        Args:
            source: Source All-Might project root.
            target: Target All-Might project root.
            workspaces: If set, only merge these workspace names.
            dry_run: If True, report what would happen without copying.
            no_memory: If True, skip memory merge.

        Returns:
            MergeReport with summary of what was done.

        Raises:
            ValueError: If source or target is not an All-Might project.
        """
        # Phase 1: Validate
        if not _is_allmight_project(source):
            raise ValueError(f"'{source}' is not an All-Might project")
        if not _is_allmight_project(target):
            raise ValueError(f"'{target}' is not an All-Might project")

        report = MergeReport(
            source=str(source),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Phase 2: Copy workspaces
        self._merge_workspaces(source, target, report, workspaces, dry_run, copy_links)

        # Phase 3: Merge memory
        if not no_memory:
            self._merge_memory(source, target, report, dry_run)

        # Phase 4: Determine actions needed
        if report.workspaces_conflicting or report.memory_conflicts:
            report.action_needed.append(
                "Run /sync to resolve workspace and memory conflicts"
            )
        if report.warnings:
            report.action_needed.append(
                "Review path warnings in merged workspace configs"
            )

        # Phase 5: Write report + install /sync
        if not dry_run:
            self._write_report(target, report)
            self._install_sync(target)

        return report

    def _merge_workspaces(
        self,
        source: Path,
        target: Path,
        report: MergeReport,
        filter_names: list[str] | None,
        dry_run: bool,
        copy_links: bool = False,
    ) -> None:
        """Copy knowledge_graph workspaces from source to target.

        Linked (symlinked) workspaces are re-created as symlinks in the
        target unless *copy_links* is True, in which case their contents
        are deep-copied.
        """
        source_kg = source / "knowledge_graph"
        target_kg = target / "knowledge_graph"

        if not source_kg.is_dir():
            return

        target_kg.mkdir(exist_ok=True)

        for ws_dir in sorted(source_kg.iterdir()):
            if not ws_dir.is_dir():
                continue
            if not (ws_dir / "config.yaml").exists():
                continue
            if filter_names and ws_dir.name not in filter_names:
                continue

            target_ws = target_kg / ws_dir.name

            # Handle linked (symlinked) workspaces
            if ws_dir.is_symlink() and not copy_links:
                report.workspaces_linked_skipped.append(ws_dir.name)
                if not dry_run and not target_ws.exists() and not target_ws.is_symlink():
                    link_target = os.readlink(str(ws_dir))
                    os.symlink(link_target, str(target_ws))
                    # Copy manifest entry to target
                    source_manifest = load_links_manifest(source_kg)
                    for lw in source_manifest.links:
                        if lw.name == ws_dir.name:
                            add_link(target_kg, lw)
                            break
                    report.workspaces_added.append(f"{ws_dir.name} (linked)")
                continue

            if target_ws.exists():
                # Conflict — copy as .incoming
                incoming = target_kg / f"{ws_dir.name}.incoming"
                report.workspaces_conflicting.append(ws_dir.name)
                if not dry_run:
                    shutil.copytree(ws_dir, incoming, dirs_exist_ok=True)
                    # Check paths in incoming config
                    incoming_config = incoming / "config.yaml"
                    if incoming_config.exists():
                        warnings = self._rewriter.rewrite_config(incoming_config)
                        report.warnings.extend(warnings)
            else:
                # No conflict — copy directly
                report.workspaces_added.append(ws_dir.name)
                if not dry_run:
                    shutil.copytree(ws_dir, target_ws)
                    # Check paths in copied config
                    copied_config = target_ws / "config.yaml"
                    if copied_config.exists():
                        warnings = self._rewriter.rewrite_config(copied_config)
                        report.warnings.extend(warnings)

    def _merge_memory(
        self,
        source: Path,
        target: Path,
        report: MergeReport,
        dry_run: bool,
    ) -> None:
        """Merge memory subsystem (L2 understanding + L3 journal)."""
        # L2: understanding files
        source_understanding = source / "memory" / "understanding"
        target_understanding = target / "memory" / "understanding"

        if source_understanding.is_dir():
            target_understanding.mkdir(parents=True, exist_ok=True)

            for md_file in sorted(source_understanding.iterdir()):
                if not md_file.is_file():
                    continue
                target_file = target_understanding / md_file.name

                if target_file.exists():
                    # Conflict — create .incoming.md
                    stem = md_file.stem
                    incoming_name = f"{stem}.incoming{md_file.suffix}"
                    report.memory_conflicts.append(f"understanding/{md_file.name}")
                    if not dry_run:
                        shutil.copy2(md_file, target_understanding / incoming_name)
                else:
                    report.memory_files_added.append(f"understanding/{md_file.name}")
                    if not dry_run:
                        shutil.copy2(md_file, target_file)

        # L3: journal entries (copy entire subtree, skip store)
        source_journal = source / "memory" / "journal"
        target_journal = target / "memory" / "journal"

        if source_journal.is_dir():
            target_journal.mkdir(parents=True, exist_ok=True)

            for item in sorted(source_journal.rglob("*")):
                if item.is_file():
                    rel = item.relative_to(source_journal)
                    target_file = target_journal / rel
                    if not dry_run:
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        if not target_file.exists():
                            shutil.copy2(item, target_file)

    def _write_report(self, target: Path, report: MergeReport) -> None:
        """Write merge report to .allmight/merge-report.yaml."""
        allmight_dir = target / ".allmight"
        allmight_dir.mkdir(exist_ok=True)

        report_data = {
            "merge": {
                "source": report.source,
                "timestamp": report.timestamp,
                "workspaces_added": report.workspaces_added,
                "workspaces_conflicting": report.workspaces_conflicting,
                "memory_files_added": report.memory_files_added,
                "memory_conflicts": report.memory_conflicts,
                "warnings": report.warnings,
                "action_needed": report.action_needed,
            }
        }

        report_path = allmight_dir / "merge-report.yaml"
        report_path.write_text(yaml.dump(report_data, default_flow_style=False))

    def _install_sync(self, target: Path) -> None:
        """Install /sync skill and command for conflict resolution."""
        from ..detroit_smak.initializer import ProjectInitializer
        ProjectInitializer()._install_sync_skill(target)
