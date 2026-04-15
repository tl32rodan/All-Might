"""Memory configuration management.

Reads and writes ``memory/config.yaml`` which holds the memory subsystem
settings, separately from the main project ``config.yaml``.
"""

from __future__ import annotations

from pathlib import Path

from ..core.domain import MemoryConfig
from ..utils.yaml_io import load_config, write_yaml


_DEFAULTS = MemoryConfig()


class MemoryConfigManager:
    """Manages ``memory/config.yaml``."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.config_path = root / "memory" / "config.yaml"

    def load(self) -> MemoryConfig:
        """Load the memory config, falling back to defaults."""
        if not self.config_path.exists():
            return MemoryConfig()

        raw = load_config(self.config_path)
        mem = raw.get("memory", {})

        return MemoryConfig(
            working_memory_budget=mem.get(
                "working_memory_budget", _DEFAULTS.working_memory_budget
            ),
            episode_retention_days=mem.get(
                "episode_retention_days", _DEFAULTS.episode_retention_days
            ),
            decay_rate=mem.get("decay_rate", _DEFAULTS.decay_rate),
            consolidation_strategy=mem.get(
                "consolidation_strategy", _DEFAULTS.consolidation_strategy
            ),
            retrieval_weights=mem.get(
                "retrieval_weights", _DEFAULTS.retrieval_weights
            ),
        )

    def save(self, cfg: MemoryConfig) -> None:
        """Persist memory config."""
        data = {
            "memory": {
                "working_memory_budget": cfg.working_memory_budget,
                "episode_retention_days": cfg.episode_retention_days,
                "decay_rate": cfg.decay_rate,
                "consolidation_strategy": cfg.consolidation_strategy,
                "retrieval_weights": cfg.retrieval_weights,
            }
        }
        write_yaml(self.config_path, data)

    def initialize(self) -> MemoryConfig:
        """Create ``memory/config.yaml`` with defaults."""
        cfg = MemoryConfig()
        self.save(cfg)
        return cfg
