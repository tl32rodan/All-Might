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

from ..core.domain import IndexSpec, PowerLevel, SymbolInfo

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
            config_path: Path to all-might/config.yaml

        Returns:
            The generated SKILL.md content as a string.
            Also writes the file to .claude/skills/one-for-all/SKILL.md.
        """
        config = self._load_config(config_path)
        root = Path(config.get("project", {}).get("root", config_path.parent.parent))

        # Load SMAK workspace config
        smak_config_path = config.get("smak", {}).get("config_path", "workspace_config.yaml")
        indices = self._load_indices(root / smak_config_path)

        # Scan sidecar files for enriched symbols
        symbols = self._scan_sidecars(root, indices)

        # Calculate power level
        power_level = self._calculate_power_level(symbols, indices)

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
            power_level=power_level,
            smak_config_path=smak_config_path,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Write to .claude/skills/one-for-all/SKILL.md
        skill_path = root / ".claude" / "skills" / "one-for-all" / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(content)

        # Also generate enrichment protocol skill
        self._generate_enrichment_skill(root, indices, power_level)

        # Generate commands
        self._generate_commands(root, smak_config_path)

        return content

    def _load_config(self, config_path: Path) -> dict:
        """Load all-might/config.yaml."""
        if config_path.exists():
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        return {}

    def _load_indices(self, config_path: Path) -> list[IndexSpec]:
        """Load SMAK workspace_config.yaml and parse indices."""
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

    def _scan_sidecars(self, root: Path, indices: list[IndexSpec]) -> list[SymbolInfo]:
        """Scan all sidecar YAML files and extract symbol information."""
        symbols: list[SymbolInfo] = []

        for idx in indices:
            for path_str in idx.paths:
                # Resolve path (handle environment variables)
                search_path = self._resolve_path(root, path_str)
                if not search_path.is_dir():
                    continue

                for sidecar in search_path.rglob(".*.sidecar.yaml"):
                    try:
                        with open(sidecar) as f:
                            data = yaml.safe_load(f) or {}
                        file_path = self._sidecar_to_source_path(sidecar)
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

    def _calculate_power_level(
        self, symbols: list[SymbolInfo], indices: list[IndexSpec]
    ) -> PowerLevel:
        """Calculate Power Level from scanned symbols."""
        total = len(symbols)
        enriched = sum(1 for s in symbols if s.has_intent)
        coverage = (enriched / total * 100) if total > 0 else 0.0

        by_index: dict[str, float] = {}
        for idx in indices:
            idx_symbols = [s for s in symbols if s.index == idx.name]
            idx_enriched = sum(1 for s in idx_symbols if s.has_intent)
            by_index[idx.name] = (idx_enriched / len(idx_symbols) * 100) if idx_symbols else 0.0

        unique_files = len(set(s.file_path for s in symbols))
        files_with_enrichment = len(set(s.file_path for s in symbols if s.has_intent))
        total_relations = sum(s.relation_count for s in symbols)

        return PowerLevel(
            total_symbols=total,
            enriched_symbols=enriched,
            coverage_pct=coverage,
            by_index=by_index,
            total_files=unique_files,
            files_with_sidecars=files_with_enrichment,
            total_relations=total_relations,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _find_key_symbols(self, symbols: list[SymbolInfo], limit: int = 20) -> list[SymbolInfo]:
        """Find the most important enriched symbols.

        Ranked by: has_intent + relation_count (more connections = more important).
        """
        enriched = [s for s in symbols if s.has_intent]
        return sorted(enriched, key=lambda s: s.relation_count, reverse=True)[:limit]

    def _resolve_path(self, root: Path, path_str: str) -> Path:
        """Resolve a path that may contain environment variables."""
        import os

        if path_str.startswith("$"):
            parts = path_str.split("/", 1)
            env_var = parts[0][1:]  # Remove $
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

    def _sidecar_to_source_path(self, sidecar: Path) -> str:
        """Convert a sidecar path back to its source file path."""
        # .foo.py.sidecar.yaml → foo.py
        name = sidecar.name
        if name.startswith(".") and name.endswith(".sidecar.yaml"):
            source_name = name[1 : -len(".sidecar.yaml")]
            return str(sidecar.parent / source_name)
        return str(sidecar)

    def _generate_enrichment_skill(
        self, root: Path, indices: list[IndexSpec], power_level: PowerLevel
    ) -> None:
        """Regenerate the enrichment protocol skill."""
        template = self.env.get_template("enrichment-protocol.md.j2")
        content = template.render(
            indices=indices,
            power_level=power_level,
        )
        path = root / ".claude" / "skills" / "enrichment" / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def _generate_commands(self, root: Path, smak_config_path: str) -> None:
        """Regenerate command files."""
        commands_dir = root / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)

        for cmd_name in ("power-level", "regenerate", "panorama"):
            template = self.env.get_template(f"commands/{cmd_name}.md.j2")
            content = template.render(smak_config_path=smak_config_path)
            (commands_dir / f"{cmd_name}.md").write_text(content)
