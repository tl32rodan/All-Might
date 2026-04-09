"""Graph Intelligence — high-level insights on top of KnowledgeGraph.

Provides god-node detection, path finding, symbol explanation,
community detection, and markdown report generation.
"""

from __future__ import annotations

from collections import defaultdict

from .analyzer import KnowledgeGraph


class GraphIntel:
    """Graph-level intelligence built on a KnowledgeGraph.

    All methods are pure computation over the already-built graph —
    no file I/O or SMAK calls.
    """

    def __init__(self, graph: KnowledgeGraph) -> None:
        self.graph = graph
        # Pre-compute adjacency for fast lookups
        self._out: dict[str, list[str]] = defaultdict(list)
        self._in: dict[str, list[str]] = defaultdict(list)
        self._node_map: dict[str, object] = {}
        for node in graph.nodes:
            self._node_map[node.uid] = node
        for edge in graph.edges:
            self._out[edge.source_uid].append(edge.target_uid)
            self._in[edge.target_uid].append(edge.source_uid)

    # ------------------------------------------------------------------
    # God Nodes — symbols with the most connections (in + out)
    # ------------------------------------------------------------------

    def god_nodes(self, top_n: int = 10) -> list[tuple[str, int]]:
        """Return the top-N nodes by total degree (in-degree + out-degree).

        These are the "god nodes" — central symbols that everything depends on.
        """
        degree: dict[str, int] = defaultdict(int)
        for uid in self._node_map:
            degree[uid] = len(self._out.get(uid, [])) + len(self._in.get(uid, []))
        ranked = sorted(degree.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_n]

    # ------------------------------------------------------------------
    # Path Finding — BFS shortest path between two symbols
    # ------------------------------------------------------------------

    def find_path(self, source_uid: str, target_uid: str) -> list[str] | None:
        """Find the shortest path from source to target (BFS, undirected).

        Returns the list of UIDs from source to target, or None if no path.
        """
        if source_uid == target_uid:
            return [source_uid]

        all_uids = set(self._node_map.keys())
        # Also include external nodes that appear only in edges
        for edge in self.graph.edges:
            all_uids.add(edge.target_uid)

        if source_uid not in all_uids or target_uid not in all_uids:
            return None

        # Build undirected adjacency
        adj: dict[str, set[str]] = defaultdict(set)
        for edge in self.graph.edges:
            adj[edge.source_uid].add(edge.target_uid)
            adj[edge.target_uid].add(edge.source_uid)

        # BFS
        visited = {source_uid}
        queue: list[list[str]] = [[source_uid]]
        while queue:
            path = queue.pop(0)
            current = path[-1]
            for neighbor in adj.get(current, set()):
                if neighbor == target_uid:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])

        return None

    # ------------------------------------------------------------------
    # Explain — full context for a single symbol
    # ------------------------------------------------------------------

    def explain(self, uid: str) -> dict:
        """Return full graph context for a symbol.

        Returns dict with: uid, name, file_path, index, intent,
        outgoing, incoming, degree, is_god_node, cluster_id.
        """
        node = self._node_map.get(uid)
        if node is None:
            return {"error": f"Symbol '{uid}' not found in graph."}

        outgoing = self._out.get(uid, [])
        incoming = self._in.get(uid, [])
        degree = len(outgoing) + len(incoming)

        # Check if this is a god node (top 10 by degree)
        gods = {u for u, _ in self.god_nodes(10)}

        # Find which community this node belongs to
        communities = self.communities()
        cluster_id = -1
        for i, community in enumerate(communities):
            if uid in community:
                cluster_id = i
                break

        return {
            "uid": node.uid,
            "name": node.name,
            "file_path": node.file_path,
            "index": node.index,
            "intent": node.intent if node.has_intent else None,
            "outgoing": outgoing,
            "incoming": incoming,
            "degree": degree,
            "is_god_node": uid in gods,
            "cluster_id": cluster_id,
        }

    # ------------------------------------------------------------------
    # Communities — connected components
    # ------------------------------------------------------------------

    def communities(self) -> list[list[str]]:
        """Return connected components as lists of UIDs.

        Uses union-find over undirected edges. Returns components
        sorted by size (largest first).
        """
        parent: dict[str, str] = {}
        for uid in self._node_map:
            parent[uid] = uid
        for edge in self.graph.edges:
            if edge.target_uid not in parent:
                parent[edge.target_uid] = edge.target_uid

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for edge in self.graph.edges:
            union(edge.source_uid, edge.target_uid)

        groups: dict[str, list[str]] = defaultdict(list)
        for uid in parent:
            groups[find(uid)].append(uid)

        # Sort by size descending
        return sorted(groups.values(), key=len, reverse=True)

    # ------------------------------------------------------------------
    # Report — markdown summary
    # ------------------------------------------------------------------

    def report(self) -> str:
        """Generate a markdown report of graph-level insights."""
        m = self.graph.metrics
        lines = [
            "# Knowledge Graph Report",
            "",
            "## Overview",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Nodes | {m.total_nodes} |",
            f"| Total Edges | {m.total_edges} |",
            f"| Nodes with Intent | {m.nodes_with_intent} |",
            f"| Orphan Nodes | {m.orphan_nodes} |",
            f"| Connected Components | {m.clusters} |",
            f"| Graph Density | {m.density:.6f} |",
            "",
        ]

        # God Nodes
        gods = self.god_nodes(10)
        if gods:
            lines.extend([
                "## God Nodes (Most Connected)",
                "",
                "| Rank | Symbol | Degree |",
                "|------|--------|--------|",
            ])
            for i, (uid, degree) in enumerate(gods, 1):
                if degree == 0:
                    break
                name = uid.split("::")[-1] if "::" in uid else uid
                lines.append(f"| {i} | `{name}` (`{uid}`) | {degree} |")
            lines.append("")

        # Communities
        comms = self.communities()
        if comms:
            lines.extend([
                "## Communities (Connected Components)",
                "",
                f"Total communities: {len(comms)}",
                "",
            ])
            for i, community in enumerate(comms):
                size = len(community)
                sample = community[:5]
                sample_str = ", ".join(f"`{u.split('::')[-1]}`" for u in sample)
                suffix = f" ... and {size - 5} more" if size > 5 else ""
                lines.append(f"- **Cluster {i}** ({size} nodes): {sample_str}{suffix}")
            lines.append("")

        # Orphan nodes
        connected = set()
        for edge in self.graph.edges:
            connected.add(edge.source_uid)
            connected.add(edge.target_uid)
        orphans = [n for n in self.graph.nodes if n.uid not in connected]
        if orphans:
            lines.extend([
                "## Orphan Nodes (No Relations)",
                "",
                f"Total orphans: {len(orphans)}",
                "",
            ])
            for node in orphans[:20]:
                intent_mark = " (has intent)" if node.has_intent else ""
                lines.append(f"- `{node.uid}`{intent_mark}")
            if len(orphans) > 20:
                lines.append(f"- ... and {len(orphans) - 20} more")
            lines.append("")

        # Cross-index edges
        cross_index: list[tuple[str, str, str, str]] = []
        node_index = {n.uid: n.index for n in self.graph.nodes}
        for edge in self.graph.edges:
            src_idx = node_index.get(edge.source_uid, "?")
            tgt_idx = node_index.get(edge.target_uid, "?")
            if src_idx != tgt_idx and tgt_idx != "?":
                cross_index.append((edge.source_uid, edge.target_uid, src_idx, tgt_idx))
        if cross_index:
            lines.extend([
                "## Cross-Index Relations",
                "",
                f"Total cross-index edges: {len(cross_index)}",
                "",
                "| Source | Target | From Index | To Index |",
                "|--------|--------|------------|----------|",
            ])
            for src, tgt, si, ti in cross_index[:20]:
                lines.append(f"| `{src}` | `{tgt}` | {si} | {ti} |")
            if len(cross_index) > 20:
                lines.append(f"\n... and {len(cross_index) - 20} more")
            lines.append("")

        return "\n".join(lines)
