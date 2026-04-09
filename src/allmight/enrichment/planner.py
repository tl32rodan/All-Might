"""Enrichment Planner — produces prioritized enrichment work lists.

Scans sidecar files, identifies symbols missing intent or relations,
and ranks them by importance for enrichment.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from ..core.domain import EnrichmentTask, IndexSpec
from ..utils.git import get_file_commit_count, is_git_repo


class EnrichmentPlanner:
    """Produces a prioritized list of enrichment tasks."""

    def plan(self, config_path: Path) -> list[EnrichmentTask]:
        """Generate an enrichment plan from current project state.

        Args:
            config_path: Path to all-might/config.yaml

        Returns:
            List of EnrichmentTasks sorted by priority (highest first).
        """
        config = self._load_config(config_path)
        root = Path(config.get("project", {}).get("root", config_path.parent.parent))
        smak_config_path = config.get("smak", {}).get("config_path", "workspace_config.yaml")
        indices = self._load_indices(root / smak_config_path)

        tasks: list[EnrichmentTask] = []
        use_git = is_git_repo(root)

        for idx in indices:
            for path_str in idx.paths:
                search_path = self._resolve_path(root, path_str)
                if not search_path.is_dir():
                    continue

                # Find all source files and their sidecars
                for source_file in self._find_source_files(search_path):
                    rel_path = str(source_file.relative_to(root))
                    sidecar = self._get_sidecar_path(source_file)

                    if not sidecar.exists():
                        # No sidecar at all — suggest creating one
                        commit_count = get_file_commit_count(root, rel_path) if use_git else 0
                        tasks.append(EnrichmentTask(
                            file_path=rel_path,
                            symbol="*",
                            index=idx.name,
                            reason="no_sidecar",
                            priority=self._calculate_priority(commit_count, "no_sidecar"),
                        ))
                        continue

                    # Sidecar exists — check each symbol
                    try:
                        with open(sidecar) as f:
                            data = yaml.safe_load(f) or {}
                    except Exception:
                        continue

                    commit_count = get_file_commit_count(root, rel_path) if use_git else 0

                    for sym in data.get("symbols", []):
                        name = sym.get("name", "")
                        intent = sym.get("intent", "")
                        relations = sym.get("relations", [])

                        if not intent:
                            tasks.append(EnrichmentTask(
                                file_path=rel_path,
                                symbol=name,
                                index=idx.name,
                                reason="missing_intent",
                                priority=self._calculate_priority(commit_count, "missing_intent"),
                            ))
                        elif not relations:
                            tasks.append(EnrichmentTask(
                                file_path=rel_path,
                                symbol=name,
                                index=idx.name,
                                reason="no_relations",
                                priority=self._calculate_priority(commit_count, "no_relations"),
                            ))

        # Sort by priority (highest first)
        tasks.sort(key=lambda t: t.priority, reverse=True)
        return tasks

    def _calculate_priority(self, commit_count: int, reason: str) -> float:
        """Calculate priority score based on reason and git activity.

        Higher score = more important to enrich.
        """
        base_scores = {
            "no_sidecar": 5.0,
            "missing_intent": 10.0,
            "no_relations": 3.0,
            "stale": 7.0,
        }
        base = base_scores.get(reason, 1.0)
        # Files with more commits are more important to enrich
        git_bonus = min(commit_count * 0.5, 10.0)
        return base + git_bonus

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

    def _find_source_files(self, directory: Path) -> list[Path]:
        """Find all source files (non-hidden, non-sidecar) in a directory."""
        source_files = []
        for f in directory.rglob("*"):
            if f.is_file() and not f.name.startswith(".") and not f.name.endswith(".sidecar.yaml"):
                source_files.append(f)
        return source_files

    def _get_sidecar_path(self, source_file: Path) -> Path:
        """Get the sidecar path for a source file."""
        return source_file.parent / f".{source_file.name}.sidecar.yaml"
