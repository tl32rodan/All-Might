"""Panorama Analyzer — builds the knowledge graph from sidecar data.

Scans all sidecar YAML files, constructs a graph of symbols (nodes)
and relations (edges), and computes graph-level metrics.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..core.domain import GraphEdge, GraphNode, IndexSpec


@dataclass
class GraphMetrics:
    """Summary metrics for the knowledge graph."""

    total_nodes: int = 0
    total_edges: int = 0
    nodes_with_intent: int = 0
    orphan_nodes: int = 0  # nodes with no edges
    clusters: int = 0  # connected components
    density: float = 0.0  # edges / (nodes * (nodes-1))


@dataclass
class KnowledgeGraph:
    """The complete knowledge graph extracted from sidecars."""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    metrics: GraphMetrics = field(default_factory=GraphMetrics)


class PanoramaAnalyzer:
    """Builds and analyzes the knowledge graph from sidecar files."""

    def analyze(self, config_path: Path) -> KnowledgeGraph:
        """Build the knowledge graph and compute metrics.

        Args:
            config_path: Path to all-might/config.yaml

        Returns:
            A KnowledgeGraph with nodes, edges, and metrics.
        """
        config = self._load_config(config_path)
        root = Path(config.get("project", {}).get("root", config_path.parent.parent))
        smak_config_path = config.get("smak", {}).get("config_path", "workspace_config.yaml")
        indices = self._load_indices(root / smak_config_path)

        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        node_uids: set[str] = set()

        for idx in indices:
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

                    file_path = self._sidecar_to_source(sidecar)
                    rel_path = str(Path(file_path).relative_to(root)) if file_path.startswith(str(root)) else file_path

                    for sym in data.get("symbols", []):
                        name = sym.get("name", "")
                        intent = sym.get("intent", "")
                        relations = sym.get("relations", [])
                        uid = f"{rel_path}::{name}"

                        nodes.append(GraphNode(
                            uid=uid,
                            name=name,
                            file_path=rel_path,
                            index=idx.name,
                            has_intent=bool(intent),
                            intent=intent,
                        ))
                        node_uids.add(uid)

                        for target_uid in relations:
                            edges.append(GraphEdge(
                                source_uid=uid,
                                target_uid=self._normalize_uid(target_uid),
                                source_index=idx.name,
                            ))

        # Compute metrics
        node_set = set(n.uid for n in nodes)
        edge_sources = set(e.source_uid for e in edges)
        edge_targets = set(e.target_uid for e in edges)
        connected = edge_sources | edge_targets
        orphans = node_set - connected

        n = len(nodes)
        e = len(edges)
        density = e / (n * (n - 1)) if n > 1 else 0.0
        clusters = self._count_components(nodes, edges)

        metrics = GraphMetrics(
            total_nodes=n,
            total_edges=e,
            nodes_with_intent=sum(1 for node in nodes if node.has_intent),
            orphan_nodes=len(orphans),
            clusters=clusters,
            density=density,
        )

        return KnowledgeGraph(nodes=nodes, edges=edges, metrics=metrics)

    def _count_components(self, nodes: list[GraphNode], edges: list[GraphEdge]) -> int:
        """Count connected components using union-find."""
        if not nodes:
            return 0

        parent: dict[str, str] = {n.uid: n.uid for n in nodes}
        # Also add edge targets that might be external nodes
        for e in edges:
            if e.target_uid not in parent:
                parent[e.target_uid] = e.target_uid

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for e in edges:
            union(e.source_uid, e.target_uid)

        # Count unique roots among our nodes only
        roots = set(find(n.uid) for n in nodes)
        return len(roots)

    def _normalize_uid(self, uid: str) -> str:
        """Normalize a UID by removing ./ prefix from path component."""
        if "::" in uid:
            path, symbol = uid.rsplit("::", 1)
            path = path.removeprefix("./")
            return f"{path}::{symbol}"
        return uid.removeprefix("./")

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
