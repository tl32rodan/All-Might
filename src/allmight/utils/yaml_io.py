"""Shared YAML / config helpers used across All-Might modules.

Extracted from the duplicated implementations in generator.py,
tracker.py, planner.py, and analyzer.py.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from allmight.core.domain import IndexSpec


def load_config(path: Path) -> dict:
    """Load an All-Might or SMAK config YAML file.

    Returns an empty dict when the file doesn't exist.
    """
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def load_indices(config_path: Path) -> list[IndexSpec]:
    """Load SMAK indices from a config YAML file."""
    if not config_path.exists():
        return []
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}
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


def resolve_path(root: Path, path_str: str) -> Path:
    """Resolve a path string relative to *root*, with ``$ENV_VAR`` support."""
    if path_str.startswith("$"):
        parts = path_str.split("/", 1)
        env_var = parts[0][1:]
        env_val = os.environ.get(env_var, "")
        if env_val and len(parts) > 1:
            return Path(env_val) / parts[1]
        elif env_val:
            return Path(env_val)
    if path_str.startswith("./"):
        return root / path_str[2:]
    if path_str.startswith("/"):
        return Path(path_str)
    return root / path_str


def write_yaml(path: Path, data: dict) -> None:
    """Write *data* as YAML to *path*, creating parent dirs if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def sidecar_to_source(sidecar_path: Path) -> str:
    """Convert a sidecar YAML path to its source file path string.

    ``.foo.sidecar.yaml`` → ``<parent>/foo``
    """
    name = sidecar_path.name
    if name.startswith(".") and name.endswith(".sidecar.yaml"):
        source_name = name[1 : -len(".sidecar.yaml")]
        return str(sidecar_path.parent / source_name)
    return str(sidecar_path)
