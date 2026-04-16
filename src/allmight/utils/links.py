"""Manifest I/O for linked corpora (``knowledge_graph/.links.yaml``).

Linked workspaces are symlinks inside ``knowledge_graph/`` that point to
external corpus directories.  The ``.links.yaml`` file tracks metadata
(source path, readonly flag, description) alongside the symlinks.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from allmight.core.domain import LinkedWorkspace, LinksManifest

LINKS_FILENAME = ".links.yaml"


def load_links_manifest(kg_dir: Path) -> LinksManifest:
    """Load ``.links.yaml`` from *kg_dir*, returning an empty manifest if absent."""
    links_path = kg_dir / LINKS_FILENAME
    if not links_path.exists():
        return LinksManifest()

    with open(links_path) as f:
        data = yaml.safe_load(f) or {}

    links = [
        LinkedWorkspace(
            name=entry["name"],
            source=entry["source"],
            readonly=entry.get("readonly", True),
            description=entry.get("description", ""),
        )
        for entry in data.get("links", [])
    ]
    return LinksManifest(links=links)


def save_links_manifest(kg_dir: Path, manifest: LinksManifest) -> None:
    """Write *manifest* to ``.links.yaml`` inside *kg_dir*."""
    links_path = kg_dir / LINKS_FILENAME
    data = {
        "links": [
            {
                "name": lw.name,
                "source": lw.source,
                "readonly": lw.readonly,
                "description": lw.description,
            }
            for lw in manifest.links
        ]
    }
    kg_dir.mkdir(parents=True, exist_ok=True)
    with open(links_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def add_link(kg_dir: Path, workspace: LinkedWorkspace) -> None:
    """Append *workspace* to the manifest, replacing any entry with the same name."""
    manifest = load_links_manifest(kg_dir)
    manifest.links = [lw for lw in manifest.links if lw.name != workspace.name]
    manifest.links.append(workspace)
    save_links_manifest(kg_dir, manifest)


def remove_link(kg_dir: Path, name: str) -> None:
    """Remove the entry named *name* from the manifest."""
    manifest = load_links_manifest(kg_dir)
    manifest.links = [lw for lw in manifest.links if lw.name != name]
    save_links_manifest(kg_dir, manifest)


def is_linked_workspace(kg_dir: Path, name: str) -> bool:
    """Return True if *name* is recorded as a linked workspace."""
    manifest = load_links_manifest(kg_dir)
    return any(lw.name == name for lw in manifest.links)
