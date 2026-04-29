"""Memory configuration management.

Reads and writes ``memory/config.yaml`` and generates
``memory/smak_config.yaml`` for SMAK vector search of the journal.
"""

from __future__ import annotations

from pathlib import Path

from ...core.domain import MemoryConfig, MemoryStoreSpec, _default_stores
from ...utils.yaml_io import load_config, write_yaml


class MemoryConfigManager:
    """Manages ``memory/config.yaml`` and derived ``memory/smak_config.yaml``."""

    def __init__(self, root: Path, memory_root: Path | None = None) -> None:
        self.root = root
        # ``memory_root`` is where ``config.yaml``/``smak_config.yaml``
        # plus the journal/store directories actually live. Defaults
        # to ``root / "memory"`` for legacy callers.
        self.memory_root = memory_root if memory_root is not None else root / "memory"
        self.config_path = self.memory_root / "config.yaml"
        self.smak_config_path = self.memory_root / "smak_config.yaml"

    def load(self) -> MemoryConfig:
        """Load the memory config, falling back to defaults."""
        if not self.config_path.exists():
            return MemoryConfig()

        raw = load_config(self.config_path)
        stores_raw = raw.get("stores", {})

        stores: dict[str, MemoryStoreSpec] = {}
        for name, spec in stores_raw.items():
            stores[name] = MemoryStoreSpec(
                name=name,
                path=spec.get("path", ""),
                store_uri=spec.get("store_uri", ""),
            )

        # Fall back to defaults for missing stores
        defaults = _default_stores()
        for name, default_spec in defaults.items():
            if name not in stores:
                stores[name] = default_spec

        reminder = raw.get("reminder_every_turns", MemoryConfig().reminder_every_turns)
        return MemoryConfig(stores=stores, reminder_every_turns=int(reminder))

    def save(self, cfg: MemoryConfig) -> None:
        """Persist memory config and regenerate smak_config."""
        stores_dict: dict[str, dict] = {}
        for name, spec in cfg.stores.items():
            stores_dict[name] = {
                "path": spec.path,
                "store_uri": spec.store_uri,
            }

        data = {
            "stores": stores_dict,
            "reminder_every_turns": cfg.reminder_every_turns,
        }
        write_yaml(self.config_path, data)
        self._write_smak_config(cfg)

    def initialize(self) -> MemoryConfig:
        """Create the memory config with defaults and generate smak_config.

        Stores resolve to absolute paths so SMAK and the agent never
        depend on the caller's cwd to find the journal.
        """
        abs_mem = self.memory_root.resolve()
        journal = MemoryStoreSpec(
            name="journal",
            path=str(abs_mem / "journal"),
            store_uri=str(abs_mem / "store" / "journal"),
        )
        cfg = MemoryConfig(stores={"journal": journal})
        self.save(cfg)
        return cfg

    def _write_smak_config(self, cfg: MemoryConfig) -> None:
        """Generate ``memory/smak_config.yaml`` for journal search."""
        indices = []
        for name, spec in cfg.stores.items():
            indices.append({
                "name": name,
                "uri": spec.store_uri,
                "description": f"Memory store: {name}",
                "paths": [spec.path],
            })

        data = {"indices": indices}
        write_yaml(self.smak_config_path, data)
