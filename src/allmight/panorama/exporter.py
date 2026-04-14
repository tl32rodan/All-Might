"""Panorama Exporter — exports the knowledge graph in various formats.

Supports JSON, Mermaid diagrams, and Obsidian vault exports.
"""

from __future__ import annotations

import json
from pathlib import Path

from .analyzer import KnowledgeGraph, PanoramaAnalyzer


class PanoramaExporter:
    """Exports the knowledge graph to various formats."""

    def __init__(self) -> None:
        self.analyzer = PanoramaAnalyzer()

    def export(self, config_path: Path, fmt: str = "json", output_dir: Path | None = None) -> Path:
        """Export the knowledge graph.

        Args:
            config_path: Path to config.yaml
            fmt: Export format — "json", "mermaid", or "obsidian"
            output_dir: Output directory (defaults to panorama/)

        Returns:
            Path to the primary output file.
        """
        graph = self.analyzer.analyze(config_path)

        if output_dir is None:
            output_dir = config_path.parent / "panorama"
        output_dir.mkdir(parents=True, exist_ok=True)

        exporters = {
            "json": self._export_json,
            "mermaid": self._export_mermaid,
            "obsidian": self._export_obsidian,
        }

        exporter = exporters.get(fmt)
        if not exporter:
            raise ValueError(f"Unknown format: {fmt}. Use one of: {', '.join(exporters)}")

        return exporter(graph, output_dir)

    def _export_json(self, graph: KnowledgeGraph, output_dir: Path) -> Path:
        """Export as JSON graph format."""
        data = {
            "metrics": {
                "total_nodes": graph.metrics.total_nodes,
                "total_edges": graph.metrics.total_edges,
                "nodes_with_intent": graph.metrics.nodes_with_intent,
                "orphan_nodes": graph.metrics.orphan_nodes,
                "clusters": graph.metrics.clusters,
                "density": round(graph.metrics.density, 6),
            },
            "nodes": [
                {
                    "uid": n.uid,
                    "name": n.name,
                    "file_path": n.file_path,
                    "index": n.index,
                    "has_intent": n.has_intent,
                    "intent": n.intent,
                }
                for n in graph.nodes
            ],
            "edges": [
                {
                    "source": e.source_uid,
                    "target": e.target_uid,
                    "source_index": e.source_index,
                }
                for e in graph.edges
            ],
        }

        output = output_dir / "graph.json"
        with open(output, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return output

    def _export_mermaid(self, graph: KnowledgeGraph, output_dir: Path) -> Path:
        """Export as Mermaid flowchart diagram.

        Focuses on connected nodes — omits orphans for clarity.
        """
        lines = ["graph LR"]

        # Collect connected nodes (those with edges)
        connected_uids = set()
        for e in graph.edges:
            connected_uids.add(e.source_uid)
            connected_uids.add(e.target_uid)

        # Node definitions
        node_ids: dict[str, str] = {}
        counter = 0
        for node in graph.nodes:
            if node.uid in connected_uids:
                node_id = f"N{counter}"
                node_ids[node.uid] = node_id
                label = node.name
                if node.has_intent:
                    short_intent = node.intent[:40] + "..." if len(node.intent) > 40 else node.intent
                    lines.append(f'    {node_id}["{label}<br/><small>{short_intent}</small>"]')
                else:
                    lines.append(f'    {node_id}["{label}"]')
                counter += 1

        # Also add external targets (from relations pointing outside our nodes)
        for e in graph.edges:
            if e.target_uid not in node_ids:
                node_id = f"N{counter}"
                node_ids[e.target_uid] = node_id
                # External node — extract name from UID
                name = e.target_uid.split("::")[-1] if "::" in e.target_uid else e.target_uid
                lines.append(f'    {node_id}["{name}"]:::external')
                counter += 1

        # Edge definitions
        for e in graph.edges:
            src = node_ids.get(e.source_uid)
            tgt = node_ids.get(e.target_uid)
            if src and tgt:
                lines.append(f"    {src} --> {tgt}")

        # Style for external nodes
        lines.append('    classDef external fill:#f9f,stroke:#333,stroke-dasharray: 5 5')

        output = output_dir / "overview.mermaid"
        output.write_text("\n".join(lines) + "\n")
        return output

    def _export_obsidian(self, graph: KnowledgeGraph, output_dir: Path) -> Path:
        """Export as Obsidian vault — one .md file per symbol."""
        vault_dir = output_dir / "obsidian"
        vault_dir.mkdir(exist_ok=True)

        # Build a reverse lookup for incoming edges
        incoming: dict[str, list[str]] = {}
        for e in graph.edges:
            incoming.setdefault(e.target_uid, []).append(e.source_uid)

        for node in graph.nodes:
            safe_name = node.name.replace("/", "_").replace("::", "_")
            md_lines = [
                f"# {node.name}",
                "",
                f"**File**: `{node.file_path}`",
                f"**Index**: `{node.index}`",
                "",
            ]

            if node.has_intent:
                md_lines.extend([
                    "## Intent",
                    "",
                    node.intent,
                    "",
                ])

            # Outgoing relations
            outgoing = [e for e in graph.edges if e.source_uid == node.uid]
            if outgoing:
                md_lines.extend(["## Relations (outgoing)", ""])
                for e in outgoing:
                    target_name = e.target_uid.split("::")[-1] if "::" in e.target_uid else e.target_uid
                    md_lines.append(f"- [[{target_name}]]")
                md_lines.append("")

            # Incoming relations
            inc = incoming.get(node.uid, [])
            if inc:
                md_lines.extend(["## Referenced by (incoming)", ""])
                for src_uid in inc:
                    src_name = src_uid.split("::")[-1] if "::" in src_uid else src_uid
                    md_lines.append(f"- [[{src_name}]]")
                md_lines.append("")

            (vault_dir / f"{safe_name}.md").write_text("\n".join(md_lines))

        return vault_dir
