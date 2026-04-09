"""ConfigManager — manages workspace_config.yaml and all-might/config.yaml.

All-Might owns the workspace configuration. Developers modify indices
through All-Might commands, not by hand-editing YAML.
"""

from __future__ import annotations

from pathlib import Path

from ..core.domain import IndexSpec
from ..utils.yaml_io import load_config, write_yaml


class ConfigManager:
    """Manages workspace_config.yaml — the single source of truth for SMAK indices.

    Every mutation syncs both ``workspace_config.yaml`` (SMAK reads this)
    and ``all-might/config.yaml`` (All-Might's own metadata).
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.workspace_config_path = root / "workspace_config.yaml"
        self.allmight_config_path = root / "all-might" / "config.yaml"
        self._indices: list[IndexSpec] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_index(
        self,
        name: str,
        description: str,
        paths: list[str],
        path_env: str | None = None,
    ) -> IndexSpec:
        """Add a new index. Raises ValueError if name already exists."""
        indices = self.list_indices()
        if any(idx.name == name for idx in indices):
            raise ValueError(f"Index '{name}' already exists.")
        new_index = IndexSpec(
            name=name,
            description=description,
            paths=paths,
            path_env=path_env,
        )
        indices.append(new_index)
        self._indices = indices
        self._write_all()
        return new_index

    def remove_index(self, name: str) -> None:
        """Remove an index by name. Raises ValueError if not found."""
        indices = self.list_indices()
        before = len(indices)
        indices = [idx for idx in indices if idx.name != name]
        if len(indices) == before:
            raise ValueError(f"Index '{name}' not found.")
        self._indices = indices
        self._write_all()

    def update_index(self, name: str, **kwargs: object) -> IndexSpec:
        """Update fields of an existing index. Raises ValueError if not found."""
        indices = self.list_indices()
        for i, idx in enumerate(indices):
            if idx.name == name:
                updated = IndexSpec(
                    name=kwargs.get("name", idx.name),
                    description=kwargs.get("description", idx.description),
                    paths=kwargs.get("paths", idx.paths),
                    path_env=kwargs.get("path_env", idx.path_env),
                )
                indices[i] = updated
                self._indices = indices
                self._write_all()
                return updated
        raise ValueError(f"Index '{name}' not found.")

    def list_indices(self) -> list[IndexSpec]:
        """Return current indices (loaded lazily, cached)."""
        if self._indices is None:
            self._indices = self._load_indices()
        return list(self._indices)

    def get_index(self, name: str) -> IndexSpec | None:
        """Return a single index by name, or None."""
        return next((idx for idx in self.list_indices() if idx.name == name), None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_indices(self) -> list[IndexSpec]:
        """Load indices from workspace_config.yaml."""
        config = load_config(self.workspace_config_path)
        return [
            IndexSpec(
                name=idx["name"],
                description=idx.get("description", ""),
                paths=idx.get("paths", []),
                path_env=idx.get("path_env"),
            )
            for idx in config.get("indices", [])
        ]

    def _write_all(self) -> None:
        """Write workspace_config.yaml and sync all-might/config.yaml."""
        self._write_workspace_config()
        self._sync_allmight_config()

    def _write_workspace_config(self) -> None:
        """Write indices to workspace_config.yaml in SMAK format."""
        indices = self._indices or []
        data = {
            "indices": [
                self._index_to_dict(idx) for idx in indices
            ],
        }
        write_yaml(self.workspace_config_path, data)

    def _sync_allmight_config(self) -> None:
        """Update index list in all-might/config.yaml."""
        config = load_config(self.allmight_config_path)
        config["indices"] = [
            {"name": idx.name, "description": idx.description}
            for idx in (self._indices or [])
        ]
        write_yaml(self.allmight_config_path, config)

    @staticmethod
    def _index_to_dict(idx: IndexSpec) -> dict:
        """Convert IndexSpec to SMAK workspace_config format."""
        d: dict = {
            "name": idx.name,
            "description": idx.description,
            "paths": idx.paths,
        }
        if idx.path_env:
            d["path_env"] = idx.path_env
        return d
