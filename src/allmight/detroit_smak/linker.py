"""Workspace Linker — symlink external corpora into knowledge_graph/.

Creates, removes, and validates symlinks that point from
``knowledge_graph/<name>`` to an external corpus directory.
Metadata is tracked in ``knowledge_graph/.links.yaml``.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..core.domain import LinkedWorkspace
from ..utils.links import (
    add_link,
    load_links_manifest,
    remove_link,
)


class WorkspaceLinker:
    """Link, unlink, and validate external corpora."""

    def link(
        self,
        kg_dir: Path,
        source: Path,
        name: str | None = None,
        readonly: bool = True,
        description: str = "",
    ) -> LinkedWorkspace:
        """Create a symlink in *kg_dir* pointing to *source*.

        Args:
            kg_dir: The ``knowledge_graph/`` directory.
            source: Absolute path to the external corpus directory.
            name: Local alias (defaults to ``source.name``).
            readonly: Mark the link as read-only in the manifest.
            description: Human-readable description.

        Returns:
            The ``LinkedWorkspace`` entry that was created.

        Raises:
            FileNotFoundError: *source* does not exist.
            ValueError: *source* has no ``config.yaml``, or *name* conflicts.
        """
        source = source.resolve()

        if not source.is_dir():
            raise FileNotFoundError(f"Source is not a directory: {source}")
        if not (source / "config.yaml").exists():
            raise ValueError(
                f"Source has no config.yaml — not a SMAK workspace: {source}"
            )

        link_name = name or source.name
        link_path = kg_dir / link_name

        if link_path.exists() or link_path.is_symlink():
            raise ValueError(
                f"'{link_name}' already exists in knowledge_graph/. "
                f"Use --name to choose a different alias."
            )

        kg_dir.mkdir(parents=True, exist_ok=True)
        os.symlink(str(source), str(link_path))

        workspace = LinkedWorkspace(
            name=link_name,
            source=str(source),
            readonly=readonly,
            description=description,
        )
        add_link(kg_dir, workspace)
        return workspace

    def unlink(self, kg_dir: Path, name: str) -> None:
        """Remove a linked corpus.

        Only removes symlinks — refuses to delete real directories.

        Raises:
            FileNotFoundError: No entry named *name* exists.
            ValueError: The path is a real directory, not a symlink.
        """
        link_path = kg_dir / name

        if not link_path.is_symlink():
            if link_path.is_dir():
                raise ValueError(
                    f"'{name}' is a real directory, not a symlink. "
                    f"Use 'rm -rf' manually if you really want to delete it."
                )
            raise FileNotFoundError(f"No workspace named '{name}' in knowledge_graph/")

        link_path.unlink()
        remove_link(kg_dir, name)

    def list_links(self, kg_dir: Path) -> list[LinkedWorkspace]:
        """Return all linked workspaces from the manifest."""
        manifest = load_links_manifest(kg_dir)
        return list(manifest.links)

    def validate_links(self, kg_dir: Path) -> list[str]:
        """Check health of all linked workspaces.

        Returns a list of warning strings (empty means all healthy).
        """
        manifest = load_links_manifest(kg_dir)
        warnings: list[str] = []

        for lw in manifest.links:
            link_path = kg_dir / lw.name

            if not link_path.is_symlink():
                warnings.append(
                    f"'{lw.name}': symlink missing (expected link to {lw.source})"
                )
                continue

            target = Path(os.readlink(str(link_path)))
            if not target.is_absolute():
                target = (link_path.parent / target).resolve()

            if not target.is_dir():
                warnings.append(
                    f"'{lw.name}': broken symlink — target does not exist: {target}"
                )
                continue

            if not (target / "config.yaml").exists():
                warnings.append(
                    f"'{lw.name}': target exists but has no config.yaml: {target}"
                )

        return warnings
