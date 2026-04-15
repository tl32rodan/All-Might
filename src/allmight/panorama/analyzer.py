"""Panorama Analyzer — builds the knowledge graph from sidecar data.

Scans all sidecar YAML files, constructs a graph of symbols (nodes)
and relations (edges), and computes graph-level metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..core.domain import GraphEdge, GraphNode, IndexSpec
from ..utils.yaml_io import load_config, load_indices, resolve_path, sidecar_to_source


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
            config_path: Path to config.yaml

        Returns:
            A KnowledgeGraph with nodes, edges, and metrics.
        """
        config = load_config(config_path)
        root = Path(config.get("project", {}).get("root", config_path.parent))
        indices = load_indices(config_path)

        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        node_uids: set[str] = set()

        for idx in indices:
            for path_str in idx.paths:
                search_path = resolve_path(root, path_str)
                if not search_path.is_dir():
                    continue

                for sidecar in search_path.rglob(".*.sidecar.yaml"):
                    try:
                        with open(sidecar) as f:
                            data = yaml.safe_load(f) or {}
                    except Exception:
                        continue

                    file_path = sidecar_to_source(sidecar)
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

    def analyze_with_memory(self, config_path: Path) -> KnowledgeGraph:
        """Build the knowledge graph including semantic memory facts.

        Extends :meth:`analyze` by injecting semantic facts as nodes
        and their source-episode links as edges.  This creates a
        unified view of code knowledge + agent memory.
        """
        graph = self.analyze(config_path)

        root = Path(
            (load_config(config_path)).get("project", {}).get(
                "root", config_path.parent
            )
        )
        facts_dir = root / "memory" / "semantic"
        if not facts_dir.is_dir():
            return graph

        for fact_file in facts_dir.glob("*.fact.yaml"):
            try:
                with open(fact_file) as f:
                    data = yaml.safe_load(f) or {}
            except Exception:
                continue

            fact_id = data.get("id", fact_file.stem)
            content = data.get("content", "")
            category = data.get("category", "")

            # Add fact as a graph node
            uid = f"memory::{fact_id}"
            graph.nodes.append(GraphNode(
                uid=uid,
                name=f"[{category}] {content[:60]}",
                file_path="memory/semantic",
                index="semantic_memory",
                has_intent=True,
                intent=content,
            ))

            # Link fact to its source episodes
            for ep_id in data.get("source_episodes", []):
                ep_uid = f"memory::{ep_id}"
                graph.edges.append(GraphEdge(
                    source_uid=uid,
                    target_uid=ep_uid,
                    source_index="semantic_memory",
                ))

            # Link to superseded fact
            supersedes = data.get("supersedes")
            if supersedes:
                graph.edges.append(GraphEdge(
                    source_uid=uid,
                    target_uid=f"memory::{supersedes}",
                    source_index="semantic_memory",
                ))

        # Recompute metrics
        n = len(graph.nodes)
        e = len(graph.edges)
        node_set = set(nd.uid for nd in graph.nodes)
        edge_connected = set()
        for edge in graph.edges:
            edge_connected.add(edge.source_uid)
            edge_connected.add(edge.target_uid)
        orphans = node_set - edge_connected

        graph.metrics = GraphMetrics(
            total_nodes=n,
            total_edges=e,
            nodes_with_intent=sum(1 for nd in graph.nodes if nd.has_intent),
            orphan_nodes=len(orphans),
            clusters=self._count_components(graph.nodes, graph.edges),
            density=e / (n * (n - 1)) if n > 1 else 0.0,
        )

        return graph

    def _normalize_uid(self, uid: str) -> str:
        """Normalize a UID by removing ./ prefix from path component."""
        if "::" in uid:
            path, symbol = uid.rsplit("::", 1)
            path = path.removeprefix("./")
            return f"{path}::{symbol}"
        return uid.removeprefix("./")

