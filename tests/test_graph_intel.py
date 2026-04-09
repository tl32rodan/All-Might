"""Tests for GraphIntel — graph-level intelligence."""

from __future__ import annotations

import unittest

from allmight.core.domain import GraphEdge, GraphNode
from allmight.panorama.analyzer import GraphMetrics, KnowledgeGraph
from allmight.panorama.graph_intel import GraphIntel


def _make_graph(
    nodes: list[GraphNode] | None = None,
    edges: list[GraphEdge] | None = None,
) -> KnowledgeGraph:
    """Build a KnowledgeGraph with pre-computed metrics."""
    nodes = nodes or []
    edges = edges or []

    node_set = {n.uid for n in nodes}
    connected = set()
    for e in edges:
        connected.add(e.source_uid)
        connected.add(e.target_uid)
    orphans = node_set - connected
    n = len(nodes)
    e_count = len(edges)
    density = e_count / (n * (n - 1)) if n > 1 else 0.0

    metrics = GraphMetrics(
        total_nodes=n,
        total_edges=e_count,
        nodes_with_intent=sum(1 for nd in nodes if nd.has_intent),
        orphan_nodes=len(orphans),
        clusters=0,
        density=density,
    )
    return KnowledgeGraph(nodes=nodes, edges=edges, metrics=metrics)


def _node(uid: str, index: str = "src", has_intent: bool = False, intent: str = "") -> GraphNode:
    """Shorthand for creating a GraphNode."""
    name = uid.split("::")[-1] if "::" in uid else uid
    file_path = uid.split("::")[0] if "::" in uid else "unknown"
    return GraphNode(uid=uid, name=name, file_path=file_path, index=index,
                     has_intent=has_intent, intent=intent)


def _edge(src: str, tgt: str, index: str = "src") -> GraphEdge:
    return GraphEdge(source_uid=src, target_uid=tgt, source_index=index)


class TestGraphIntelEmpty(unittest.TestCase):
    """Edge case: empty graph."""

    def setUp(self) -> None:
        self.intel = GraphIntel(_make_graph())

    def test_god_nodes_empty(self) -> None:
        self.assertEqual(self.intel.god_nodes(), [])

    def test_communities_empty(self) -> None:
        self.assertEqual(self.intel.communities(), [])

    def test_report_empty(self) -> None:
        report = self.intel.report()
        self.assertIn("Knowledge Graph Report", report)
        self.assertIn("Total Nodes | 0", report)

    def test_find_path_empty(self) -> None:
        self.assertIsNone(self.intel.find_path("a::x", "b::y"))

    def test_explain_missing(self) -> None:
        result = self.intel.explain("nonexistent::sym")
        self.assertIn("error", result)


class TestGraphIntelBasic(unittest.TestCase):
    """Graph with a few connected nodes."""

    def setUp(self) -> None:
        # A -> B -> C, A -> C  (triangle)
        # D is orphan
        self.graph = _make_graph(
            nodes=[
                _node("a.py::A", has_intent=True, intent="Entry point"),
                _node("b.py::B"),
                _node("c.py::C", has_intent=True, intent="Data model"),
                _node("d.py::D"),  # orphan
            ],
            edges=[
                _edge("a.py::A", "b.py::B"),
                _edge("b.py::B", "c.py::C"),
                _edge("a.py::A", "c.py::C"),
            ],
        )
        self.intel = GraphIntel(self.graph)

    def test_god_nodes(self) -> None:
        gods = self.intel.god_nodes(3)
        # A has degree 2 (out), C has degree 2 (in), B has degree 2 (in+out)
        uids = [uid for uid, _ in gods]
        # All of A, B, C have degree 2; D has 0
        self.assertNotIn("d.py::D", uids)
        # The top 3 should all have degree 2
        for _, degree in gods[:3]:
            self.assertEqual(degree, 2)

    def test_find_path_direct(self) -> None:
        path = self.intel.find_path("a.py::A", "b.py::B")
        self.assertEqual(path, ["a.py::A", "b.py::B"])

    def test_find_path_indirect(self) -> None:
        path = self.intel.find_path("b.py::B", "a.py::A")
        # BFS undirected: B-A is direct (edge A->B is undirected in path finding)
        self.assertIsNotNone(path)
        self.assertEqual(path[0], "b.py::B")
        self.assertEqual(path[-1], "a.py::A")

    def test_find_path_same_node(self) -> None:
        path = self.intel.find_path("a.py::A", "a.py::A")
        self.assertEqual(path, ["a.py::A"])

    def test_find_path_no_path(self) -> None:
        # D is orphan — no path from D to A
        path = self.intel.find_path("d.py::D", "a.py::A")
        self.assertIsNone(path)

    def test_explain(self) -> None:
        result = self.intel.explain("a.py::A")
        self.assertEqual(result["uid"], "a.py::A")
        self.assertEqual(result["name"], "A")
        self.assertEqual(result["intent"], "Entry point")
        self.assertEqual(result["degree"], 2)
        self.assertEqual(len(result["outgoing"]), 2)
        self.assertEqual(len(result["incoming"]), 0)
        self.assertIsInstance(result["cluster_id"], int)

    def test_explain_incoming(self) -> None:
        result = self.intel.explain("c.py::C")
        self.assertEqual(len(result["incoming"]), 2)  # from A and B
        self.assertEqual(len(result["outgoing"]), 0)

    def test_explain_missing_node(self) -> None:
        result = self.intel.explain("nonexistent")
        self.assertIn("error", result)

    def test_communities(self) -> None:
        comms = self.intel.communities()
        # A, B, C are connected; D is isolated
        self.assertEqual(len(comms), 2)
        sizes = sorted([len(c) for c in comms], reverse=True)
        self.assertEqual(sizes, [3, 1])

    def test_report_contains_sections(self) -> None:
        report = self.intel.report()
        self.assertIn("## Overview", report)
        self.assertIn("## God Nodes", report)
        self.assertIn("## Communities", report)
        self.assertIn("## Orphan Nodes", report)
        self.assertIn("d.py::D", report)  # orphan should be listed

    def test_report_god_node_skips_zero_degree(self) -> None:
        report = self.intel.report()
        # D has degree 0, should not appear in God Nodes table
        god_section_start = report.index("## God Nodes")
        god_section_end = report.index("## Communities")
        god_section = report[god_section_start:god_section_end]
        self.assertNotIn("d.py::D", god_section)


class TestGraphIntelCrossIndex(unittest.TestCase):
    """Graph with cross-index edges."""

    def setUp(self) -> None:
        self.graph = _make_graph(
            nodes=[
                _node("src/main.py::Main", index="source_code"),
                _node("tests/test_main.py::TestMain", index="tests"),
            ],
            edges=[
                _edge("tests/test_main.py::TestMain", "src/main.py::Main", index="tests"),
            ],
        )
        self.intel = GraphIntel(self.graph)

    def test_report_cross_index(self) -> None:
        report = self.intel.report()
        self.assertIn("## Cross-Index Relations", report)
        self.assertIn("source_code", report)
        self.assertIn("tests", report)


class TestGraphIntelExternalTargets(unittest.TestCase):
    """Edges pointing to UIDs not in the node list."""

    def setUp(self) -> None:
        self.graph = _make_graph(
            nodes=[_node("a.py::A")],
            edges=[_edge("a.py::A", "external.py::Ext")],
        )
        self.intel = GraphIntel(self.graph)

    def test_find_path_to_external(self) -> None:
        path = self.intel.find_path("a.py::A", "external.py::Ext")
        self.assertEqual(path, ["a.py::A", "external.py::Ext"])

    def test_god_nodes_includes_known_only(self) -> None:
        gods = self.intel.god_nodes()
        # Only a.py::A is a real node
        uids = [uid for uid, _ in gods]
        self.assertIn("a.py::A", uids)


if __name__ == "__main__":
    unittest.main()
