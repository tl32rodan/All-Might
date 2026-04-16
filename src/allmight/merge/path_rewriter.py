"""SMAK config path classifier and rewriter.

After copying a workspace from one All-Might project to another, the
paths in config.yaml may no longer be valid.  This module classifies
each path and warns about ones that likely need manual adjustment.
"""

from __future__ import annotations

from pathlib import Path

import yaml


class PathRewriter:
    """Classify and audit paths in a SMAK workspace config.yaml."""

    def classify(self, path_str: str) -> str:
        """Classify a single path string.

        Returns one of:
          - ``"env_var"`` — starts with ``$`` (e.g. ``$DDI_ROOT_PATH/…``)
          - ``"workspace_relative"`` — starts with ``./`` (safe after copy)
          - ``"external_relative"`` — starts with ``../`` (likely broken)
          - ``"absolute"`` — starts with ``/`` (likely wrong on new machine)
        """
        if path_str.startswith("$"):
            return "env_var"
        if path_str.startswith("./"):
            return "workspace_relative"
        if path_str.startswith(".."):
            return "external_relative"
        if path_str.startswith("/"):
            return "absolute"
        # Bare relative (no ./ prefix) — treat as external
        return "external_relative"

    def rewrite_config(self, config_path: Path) -> list[str]:
        """Audit paths in a SMAK config.yaml.  Returns a list of warnings.

        Env-var and workspace-relative paths are safe and left untouched.
        External-relative and absolute paths generate warnings so the
        agent (via ``/sync``) can help the user fix them.
        """
        text = config_path.read_text()
        data = yaml.safe_load(text)

        warnings: list[str] = []
        indices = data.get("indices") or []

        for idx in indices:
            for p in idx.get("paths") or []:
                kind = self.classify(p)
                if kind in ("external_relative", "absolute"):
                    warnings.append(
                        f"{config_path.name}: path '{p}' in index "
                        f"'{idx.get('name', '?')}' may need adjustment "
                        f"(type: {kind})"
                    )

        return warnings
