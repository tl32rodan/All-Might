"""ConfigManager — manages config.yaml.

All-Might owns the workspace configuration. Developers modify indices
through All-Might commands, not by hand-editing YAML.
"""

from __future__ import annotations

from pathlib import Path

from ..core.domain import IndexSpec
from ..utils.yaml_io import load_config, write_yaml


class ConfigManager:
    """Manages config.yaml — the single source of truth for SMAK indices.

    Every mutation updates ``config.yaml`` which holds both project
    metadata and the full index definitions.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.config_path = root / "config.yaml"
        self._indices: list[IndexSpec] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_index(
        self,
        name: str,
        description: str,
        paths: list[str],
        uri: str | None = None,
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
            uri=uri or f"./smak/{name}",
            path_env=path_env,
        )
        indices.append(new_index)
        self._indices = indices
        self._write_config()
        return new_index

    def remove_index(self, name: str) -> None:
        """Remove an index by name. Raises ValueError if not found."""
        indices = self.list_indices()
        before = len(indices)
        indices = [idx for idx in indices if idx.name != name]
        if len(indices) == before:
            raise ValueError(f"Index '{name}' not found.")
        self._indices = indices
        self._write_config()

    def update_index(self, name: str, **kwargs: object) -> IndexSpec:
        """Update fields of an existing index. Raises ValueError if not found."""
        indices = self.list_indices()
        for i, idx in enumerate(indices):
            if idx.name == name:
                updated = IndexSpec(
                    name=kwargs.get("name", idx.name),
                    description=kwargs.get("description", idx.description),
                    paths=kwargs.get("paths", idx.paths),
                    uri=kwargs.get("uri", idx.uri),
                    path_env=kwargs.get("path_env", idx.path_env),
                )
                indices[i] = updated
                self._indices = indices
                self._write_config()
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
        """Load indices from config.yaml."""
        config = load_config(self.config_path)
        return [
            IndexSpec(
                name=idx["name"],
                description=idx.get("description", ""),
                paths=idx.get("paths", []),
                uri=idx.get("uri"),
                path_env=idx.get("path_env"),
            )
            for idx in config.get("indices", [])
        ]

    def _write_config(self) -> None:
        """Update indices in config.yaml, preserving other keys."""
        config = load_config(self.config_path)
        config["indices"] = [
            self._index_to_dict(idx) for idx in (self._indices or [])
        ]
        write_yaml(self.config_path, config)

    @staticmethod
    def _index_to_dict(idx: IndexSpec) -> dict:
        """Convert IndexSpec to config.yaml dict format."""
        d: dict = {
            "name": idx.name,
            "uri": idx.uri or f"./smak/{idx.name}",
            "description": idx.description,
            "paths": idx.paths,
        }
        if idx.path_env:
            d["path_env"] = idx.path_env
        return d
