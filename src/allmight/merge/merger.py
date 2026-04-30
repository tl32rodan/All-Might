"""Instance Merger — merge a personality instance from another project.

Replaces the older project-level merge. The unit of work is now a
single personality *instance* (e.g. ``knowledge`` from another
project). Conflicts inside the destination instance are staged with
the existing ``.incoming`` suffix pattern and resolved by ``/sync``.

Two merge modes:

* **Combine** (default): the source instance's content is folded into
  a same-named destination instance. Existing files are preserved;
  conflicting files land beside them with an ``.incoming`` suffix.
* **Side-by-side** (``as_name`` set): the source instance is copied
  whole-cloth into ``personalities/<as_name>/`` as a brand-new
  instance. The destination registry gains a row.

A successful merge re-composes the agent surface (``.opencode/``
symlinks + root ``AGENTS.md``) so the new content is visible
immediately.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..core.domain import MergeReport
from ..core.personalities import (
    Personality,
    RegistryEntry,
    compose,
    compose_agents_md,
    discover,
    read_registry,
    write_registry,
)
from .path_rewriter import PathRewriter


class InstanceMerger:
    """Merge one personality instance from a source project into the target."""

    def __init__(self) -> None:
        self._rewriter = PathRewriter()

    def merge(
        self,
        source: Path,
        target: Path,
        instance_name: str,
        as_name: str | None = None,
        dry_run: bool = False,
    ) -> MergeReport:
        """Merge instance ``instance_name`` from ``source`` into ``target``.

        Args:
            source: Source All-Might project root (must have a
                personality instance named ``instance_name``).
            target: Destination project root.
            instance_name: Name of the source instance to merge.
            as_name: When set, install the source instance under
                ``personalities/<as_name>/`` instead of combining into
                a same-named target instance. Errors if the new name
                already exists in target.
            dry_run: Report planned actions without touching disk.

        Returns:
            ``MergeReport`` describing what changed.
        """
        if not _is_allmight_project(source):
            raise ValueError(f"'{source}' is not an All-Might project")
        if not _is_allmight_project(target):
            raise ValueError(f"'{target}' is not an All-Might project")

        source_instance = self._resolve_source_instance(source, instance_name)
        if source_instance is None:
            raise ValueError(
                f"source has no instance named '{instance_name}'"
            )

        report = MergeReport(
            source=str(source),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        dest_name = as_name or instance_name
        dest_dir = target / "personalities" / dest_name
        source_dir = source / "personalities" / source_instance.instance

        if as_name is not None:
            self._merge_side_by_side(
                source_dir, target, source_instance, dest_name, dest_dir, report, dry_run,
            )
        else:
            self._merge_combine(source_dir, dest_dir, source_instance, target, report, dry_run)

        if not dry_run:
            self._recompose(target)
            self._write_report(target, report)
            self._install_sync(target)

        return report

    # ------------------------------------------------------------------
    # Source-instance resolution
    # ------------------------------------------------------------------

    def _resolve_source_instance(
        self, source: Path, instance_name: str,
    ) -> RegistryEntry | None:
        for entry in read_registry(source):
            if entry.instance == instance_name:
                return entry
        return None

    # ------------------------------------------------------------------
    # Side-by-side install
    # ------------------------------------------------------------------

    def _merge_side_by_side(
        self,
        source_dir: Path,
        target: Path,
        source_entry: RegistryEntry,
        dest_name: str,
        dest_dir: Path,
        report: MergeReport,
        dry_run: bool,
    ) -> None:
        if dest_dir.exists():
            raise ValueError(
                f"target already has personalities/{dest_name}/; "
                "pick a different --as name or omit --as to combine instead"
            )
        report.workspaces_added.append(dest_name)
        if dry_run:
            return
        shutil.copytree(source_dir, dest_dir)
        # Rewrite path-env hints inside any database configs so
        # the new instance points at the destination's environment.
        for cfg in dest_dir.rglob("config.yaml"):
            warnings = self._rewriter.rewrite_config(cfg)
            report.warnings.extend(warnings)
        # Append to target's personalities.yaml under the new name.
        entries = read_registry(target)
        entries.append(RegistryEntry(
            template=source_entry.template,
            instance=dest_name,
            version=source_entry.version,
        ))
        write_registry(target, entries)

    # ------------------------------------------------------------------
    # Combine into existing instance
    # ------------------------------------------------------------------

    def _merge_combine(
        self,
        source_dir: Path,
        dest_dir: Path,
        source_entry: RegistryEntry,
        target: Path,
        report: MergeReport,
        dry_run: bool,
    ) -> None:
        if not dest_dir.exists():
            # No same-named instance — equivalent to a fresh install.
            report.workspaces_added.append(source_entry.instance)
            if dry_run:
                return
            shutil.copytree(source_dir, dest_dir)
            for cfg in dest_dir.rglob("config.yaml"):
                warnings = self._rewriter.rewrite_config(cfg)
                report.warnings.extend(warnings)
            entries = read_registry(target)
            if not any(e.instance == source_entry.instance for e in entries):
                entries.append(RegistryEntry(
                    template=source_entry.template,
                    instance=source_entry.instance,
                    version=source_entry.version,
                ))
                write_registry(target, entries)
            return

        # Walk source instance and copy file-by-file with conflict
        # handling. ``ROLE.md`` and ``config.yaml`` are user/agent-
        # authored, so collisions get the ``.incoming`` suffix; raw
        # data dirs (database/, memory/journal/) get their contents
        # copied through where there's no conflict.
        for src_path in sorted(source_dir.rglob("*")):
            if not src_path.is_file():
                continue
            rel = src_path.relative_to(source_dir)
            dst_path = dest_dir / rel
            if dst_path.exists():
                if rel.parts and rel.parts[-1] in {"config.yaml", "ROLE.md"} \
                        or rel.parts[0] in {"memory", "database"} \
                        and dst_path.read_bytes() != src_path.read_bytes():
                    incoming = dst_path.with_name(
                        f"{dst_path.stem}.incoming{dst_path.suffix}"
                    )
                    report.memory_conflicts.append(str(rel))
                    if not dry_run:
                        dst_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_path, incoming)
                # Identical contents are silently skipped.
            else:
                report.memory_files_added.append(str(rel))
                if not dry_run:
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_path, dst_path)

        if not dry_run:
            for cfg in dest_dir.rglob("config.yaml"):
                warnings = self._rewriter.rewrite_config(cfg)
                report.warnings.extend(warnings)

    # ------------------------------------------------------------------
    # Re-composition + bookkeeping
    # ------------------------------------------------------------------

    def _recompose(self, target: Path) -> None:
        """Refresh ``.opencode/`` symlinks and root ``AGENTS.md``."""
        templates = {t.name: t for t in discover()}
        instances = []
        for entry in read_registry(target):
            template = templates.get(entry.template)
            if template is None:
                continue
            instances.append(Personality(
                template=template, project_root=target, name=entry.instance,
            ))
        for instance in instances:
            compose(target, instance, force=False)
        compose_agents_md(target, instances, project_name=target.name)

    def _write_report(self, target: Path, report: MergeReport) -> None:
        if report.memory_conflicts or report.workspaces_conflicting:
            report.action_needed.append(
                "Run /sync to resolve incoming files staged with .incoming suffix"
            )
        allmight_dir = target / ".allmight"
        allmight_dir.mkdir(exist_ok=True)
        report_data = {
            "merge": {
                "source": report.source,
                "timestamp": report.timestamp,
                "workspaces_added": report.workspaces_added,
                "memory_files_added": report.memory_files_added,
                "memory_conflicts": report.memory_conflicts,
                "warnings": report.warnings,
                "action_needed": report.action_needed,
            }
        }
        (allmight_dir / "merge-report.yaml").write_text(
            yaml.dump(report_data, default_flow_style=False)
        )

    def _install_sync(self, target: Path) -> None:
        """Install /sync skill so the agent can resolve any conflicts."""
        from ..capabilities.database.initializer import ProjectInitializer

        ProjectInitializer()._install_sync_skill(target)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_allmight_project(root: Path) -> bool:
    """An All-Might project has ``.allmight/personalities.yaml``."""
    return (root / ".allmight" / "personalities.yaml").is_file()
