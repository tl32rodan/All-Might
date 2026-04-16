"""One For All Generator — produces SKILL.md from project state.

Reads the project configuration, SMAK workspace config, and sidecar files
to dynamically generate a SKILL.md that captures the current state of the
knowledge graph. Each regeneration makes the One For All stronger.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..core.domain import IndexSpec, SymbolInfo
from ..utils.yaml_io import load_config, load_indices, resolve_path, sidecar_to_source

# Template directory is relative to this module
_TEMPLATE_DIR = Path(__file__).parent / "templates"


class OneForAllGenerator:
    """Generates One For All SKILL.md from current project state."""

    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(self, config_path: Path) -> str:
        """Generate the One For All SKILL.md content.

        Args:
            config_path: Path to config.yaml

        Returns:
            The generated SKILL.md content as a string.
            Also writes the file to .claude/skills/one-for-all/SKILL.md.
        """
        config = load_config(config_path)
        root = Path(config.get("project", {}).get("root", config_path.parent))
        indices = load_indices(config_path)

        # Scan sidecar files for enriched symbols
        symbols = self._scan_sidecars(root, indices)

        # Find key symbols (most enriched / most connected)
        key_symbols = self._find_key_symbols(symbols)

        # Render template
        template = self.env.get_template("skill-base.md.j2")
        content = template.render(
            project_name=config.get("project", {}).get("name", "Unknown"),
            languages=config.get("project", {}).get("languages", []),
            frameworks=config.get("project", {}).get("frameworks", []),
            indices=indices,
            key_symbols=key_symbols,
            smak_config_path="config.yaml",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Write to .claude/skills/one-for-all/SKILL.md
        skill_path = root / ".claude" / "skills" / "one-for-all" / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(content)

        return content

    def _scan_sidecars(self, root: Path, indices: list[IndexSpec]) -> list[SymbolInfo]:
        """Scan all sidecar YAML files and extract symbol information."""
        symbols: list[SymbolInfo] = []

        for idx in indices:
            for path_str in idx.paths:
                # Resolve path (handle environment variables)
                search_path = resolve_path(root, path_str)
                if not search_path.is_dir():
                    continue

                for sidecar in search_path.rglob(".*.sidecar.yaml"):
                    try:
                        with open(sidecar) as f:
                            data = yaml.safe_load(f) or {}
                        file_path = sidecar_to_source(sidecar)
                        for sym in data.get("symbols", []):
                            intent = sym.get("intent", "")
                            relations = sym.get("relations", [])
                            symbols.append(SymbolInfo(
                                name=sym["name"],
                                file_path=file_path,
                                index=idx.name,
                                has_intent=bool(intent),
                                has_relations=bool(relations),
                                intent=intent,
                                relation_count=len(relations),
                            ))
                    except Exception:
                        continue

        return symbols

    def _find_key_symbols(self, symbols: list[SymbolInfo], limit: int = 20) -> list[SymbolInfo]:
        """Find the most important enriched symbols.

        Ranked by: has_intent + relation_count (more connections = more important).
        """
        enriched = [s for s in symbols if s.has_intent]
        return sorted(enriched, key=lambda s: s.relation_count, reverse=True)[:limit]

