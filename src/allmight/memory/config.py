"""Memory configuration management.

Reads and writes ``memory/config.yaml`` which holds the memory subsystem
settings and store definitions, **separately** from the main project
``config.yaml``.  Also generates ``memory/smak_config.yaml`` — an
internal file consumed by SmakBridge for vector search.
"""

from __future__ import annotations

from pathlib import Path

from ..core.domain import MemoryConfig, MemoryStoreSpec, _default_stores
from ..utils.yaml_io import load_config, write_yaml


class MemoryConfigManager:
    """Manages ``memory/config.yaml`` and derived ``memory/smak_config.yaml``."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.config_path = root / "memory" / "config.yaml"
        self.smak_config_path = root / "memory" / "smak_config.yaml"

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def load(self) -> MemoryConfig:
        """Load the memory config, falling back to defaults."""
        if not self.config_path.exists():
            return MemoryConfig()

        raw = load_config(self.config_path)
        mem = raw.get("memory", {})
        stores_raw = raw.get("stores", {})

        # Parse stores
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

        return MemoryConfig(
            working_memory_budget=mem.get("working_memory_budget", 4000),
            episode_retention_days=mem.get("episode_retention_days", 90),
            decay_rate=mem.get("decay_rate", 0.05),
            consolidation_strategy=mem.get("consolidation_strategy", "async"),
            retrieval_weights=mem.get("retrieval_weights", {
                "recency": 0.3, "importance": 0.3, "relevance": 0.4,
            }),
            stores=stores,
        )

    def save(self, cfg: MemoryConfig) -> None:
        """Persist memory config and regenerate smak_config."""
        stores_dict: dict[str, dict] = {}
        for name, spec in cfg.stores.items():
            stores_dict[name] = {
                "path": spec.path,
                "store_uri": spec.store_uri,
            }

        data = {
            "memory": {
                "working_memory_budget": cfg.working_memory_budget,
                "episode_retention_days": cfg.episode_retention_days,
                "decay_rate": cfg.decay_rate,
                "consolidation_strategy": cfg.consolidation_strategy,
                "retrieval_weights": cfg.retrieval_weights,
            },
            "stores": stores_dict,
        }
        write_yaml(self.config_path, data)

        # Keep the internal smak config in sync
        self._write_smak_config(cfg)

    # ------------------------------------------------------------------
    # Store management
    # ------------------------------------------------------------------

    def add_store(
        self,
        name: str,
        path: str,
        store_uri: str,
    ) -> MemoryStoreSpec:
        """Add a store definition.  Idempotent — skips if already present."""
        cfg = self.load()
        if name in cfg.stores:
            return cfg.stores[name]
        spec = MemoryStoreSpec(name=name, path=path, store_uri=store_uri)
        cfg.stores[name] = spec
        self.save(cfg)
        return spec

    def get_store(self, name: str) -> MemoryStoreSpec | None:
        """Retrieve a single store by name."""
        return self.load().stores.get(name)

    def list_stores(self) -> list[MemoryStoreSpec]:
        """List all store definitions."""
        return list(self.load().stores.values())

    # ------------------------------------------------------------------
    # Initialise
    # ------------------------------------------------------------------

    def initialize(self) -> MemoryConfig:
        """Create ``memory/config.yaml`` with defaults and generate smak_config."""
        cfg = MemoryConfig()
        self.save(cfg)
        return cfg

    # ------------------------------------------------------------------
    # Internal: SMAK-compatible config generation
    # ------------------------------------------------------------------

    def _write_smak_config(self, cfg: MemoryConfig) -> None:
        """Generate ``memory/smak_config.yaml`` for SmakBridge consumption.

        This file is an **internal implementation detail** — users never
        see or interact with it.  It translates memory store definitions
        into the index format the search engine CLI expects.
        """
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
