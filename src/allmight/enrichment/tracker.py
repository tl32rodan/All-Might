"""Power Level Tracker — calculates and persists coverage metrics.

Scans sidecar files to compute the project's "戰力值" (Power Level) —
the knowledge graph maturity indicator.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..core.domain import IndexSpec, PowerLevel


class PowerTracker:
    """Calculates Power Level from sidecar data and persists to tracker.yaml."""

    def calculate(self, config_path: Path) -> PowerLevel:
        """Calculate current Power Level and update tracker.yaml.

        Args:
            config_path: Path to all-might/config.yaml

        Returns:
            The calculated PowerLevel.
        """
        config = self._load_config(config_path)
        root = Path(config.get("project", {}).get("root", config_path.parent.parent))
        smak_config_path = config.get("smak", {}).get("config_path", "workspace_config.yaml")
        indices = self._load_indices(root / smak_config_path)

        total_symbols = 0
        enriched_symbols = 0
        total_relations = 0
        all_files: set[str] = set()
        files_with_sidecars: set[str] = set()
        by_index: dict[str, float] = {}

        for idx in indices:
            idx_total = 0
            idx_enriched = 0

            for path_str in idx.paths:
                search_path = self._resolve_path(root, path_str)
                if not search_path.is_dir():
                    continue

                for sidecar in search_path.rglob(".*.sidecar.yaml"):
                    try:
                        with open(sidecar) as f:
                            data = yaml.safe_load(f) or {}
                    except Exception:
                        continue

                    source_file = self._sidecar_to_source(sidecar)
                    files_with_sidecars.add(source_file)

                    for sym in data.get("symbols", []):
                        idx_total += 1
                        intent = sym.get("intent", "")
                        relations = sym.get("relations", [])
                        if intent:
                            idx_enriched += 1
                        total_relations += len(relations)

                # Count source files for coverage denominator
                for f in search_path.rglob("*"):
                    if f.is_file() and not f.name.startswith("."):
                        all_files.add(str(f))

            total_symbols += idx_total
            enriched_symbols += idx_enriched
            by_index[idx.name] = (idx_enriched / idx_total * 100) if idx_total > 0 else 0.0

        coverage = (enriched_symbols / total_symbols * 100) if total_symbols > 0 else 0.0
        timestamp = datetime.now(timezone.utc).isoformat()

        level = PowerLevel(
            total_symbols=total_symbols,
            enriched_symbols=enriched_symbols,
            coverage_pct=coverage,
            by_index=by_index,
            total_files=len(all_files),
            files_with_sidecars=len(files_with_sidecars),
            total_relations=total_relations,
            timestamp=timestamp,
        )

        # Persist to tracker.yaml
        self._persist(config_path.parent / "enrichment" / "tracker.yaml", level)

        return level

    def _persist(self, tracker_path: Path, level: PowerLevel) -> None:
        """Write Power Level to tracker.yaml with history."""
        tracker_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing history
        history = []
        if tracker_path.exists():
            try:
                with open(tracker_path) as f:
                    existing = yaml.safe_load(f) or {}
                history = existing.get("history", [])
            except Exception:
                pass

        # Append current snapshot
        history.append({
            "timestamp": level.timestamp,
            "coverage_pct": level.coverage_pct,
            "enriched_symbols": level.enriched_symbols,
            "total_symbols": level.total_symbols,
            "total_relations": level.total_relations,
        })

        # Keep last 100 entries
        history = history[-100:]

        data = {
            "power_level": {
                "total_symbols": level.total_symbols,
                "enriched_symbols": level.enriched_symbols,
                "coverage_pct": round(level.coverage_pct, 2),
                "by_index": {k: round(v, 2) for k, v in level.by_index.items()},
                "total_files": level.total_files,
                "files_with_sidecars": level.files_with_sidecars,
                "total_relations": level.total_relations,
            },
            "history": history,
            "updated_at": level.timestamp,
        }

        with open(tracker_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def _load_config(self, config_path: Path) -> dict:
        if config_path.exists():
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        return {}

    def _load_indices(self, config_path: Path) -> list[IndexSpec]:
        if not config_path.exists():
            return []
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        return [
            IndexSpec(
                name=idx["name"],
                description=idx.get("description", ""),
                paths=idx.get("paths", []),
                path_env=idx.get("path_env"),
            )
            for idx in config.get("indices", [])
        ]

    def _resolve_path(self, root: Path, path_str: str) -> Path:
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

    def _sidecar_to_source(self, sidecar: Path) -> str:
        name = sidecar.name
        if name.startswith(".") and name.endswith(".sidecar.yaml"):
            source_name = name[1 : -len(".sidecar.yaml")]
            return str(sidecar.parent / source_name)
        return str(sidecar)
