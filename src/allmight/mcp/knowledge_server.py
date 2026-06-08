"""All-Might Knowledge MCP server — offline substitute for web_search / context7.

Exposes two intent-named tools the model invokes **autonomously** (push,
not the pull surface of a slash command):

* ``project_knowledge_search(query, top_k=8)`` — semantic search across
  every personality's ``database`` workspace (source code **and** its
  documentation, linked by SMAK's 1-hop mesh). The offline analog of
  ``web_search`` / ``context7`` for library/tool/code lookups.
* ``memory_recall(query, personality=None, top_k=5)`` — recall the
  agent's own past observations from a personality's L3 journal. Scoped
  to the default personality (the MEMORY.md callout) unless overridden,
  to preserve per-personality memory isolation.

Design (see ``docs/offline-reference-proposal.md``):

- **Thin wrapper over ``smak.core_ops``.** SMAK's own MCP server is not
  wired directly — its tools require a per-call ``config`` path and use
  generic names. This server discovers the workspace configs from the
  project tree so the model passes only a query.
- **Lazy ``smak`` / ``mcp`` imports.** The discovery + resolution helpers
  stay importable and unit-testable without the heavy deps installed;
  ``smak`` is imported only inside the runtime functions, after the
  cheap deterministic guards (no-workspace / no-personality) have run.
- **Project root** arrives via ``ALLMIGHT_PROJECT_ROOT`` (default: cwd).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# ``> **Default personality**: <name>`` — the MEMORY.md routing callout.
_DEFAULT_PERSONALITY_RE = re.compile(
    r"^>\s*\*\*Default personality\*\*:\s*(.+?)\s*$", re.MULTILINE,
)

PROJECT_KNOWLEDGE_DESCRIPTION = (
    "Search the project's OFFLINE knowledge base — source code AND its "
    "documentation (manuals, library/API references), linked by a "
    "semantic mesh so a hit in one surfaces the related other. This is "
    "the offline replacement for web search / context7: when you would "
    "look up a library signature, a tool's flags, an API, or how some "
    "code works, call this INSTEAD — this environment is air-gapped and "
    "there is no live web. Write the query as a natural-language "
    "description of intent. If it returns nothing, say so; do not "
    "invent an answer."
)

MEMORY_RECALL_DESCRIPTION = (
    "Recall your own past observations, decisions, and gotchas from "
    "earlier sessions (the personality's journal). Use it for continuity "
    "— 'did we decide X', 'what went wrong last time', 'pick up where I "
    "left off'. Scoped to the active/default personality unless you pass "
    "`personality`. If it returns nothing, say so; do not invent."
)


# ---------------------------------------------------------------------------
# Pure discovery / resolution helpers (no smak, no mcp — unit-testable)
# ---------------------------------------------------------------------------


def find_project_root() -> Path:
    """Project root from ``ALLMIGHT_PROJECT_ROOT``, else the cwd."""
    return Path(os.environ.get("ALLMIGHT_PROJECT_ROOT") or os.getcwd()).resolve()


def discover_database_configs(root: Path) -> list[Path]:
    """Every ``personalities/*/database/*/config.yaml`` in the project.

    These are the SMAK workspace configs for the code + docs corpora.
    Sorted for deterministic ordering.
    """
    base = root / "personalities"
    if not base.is_dir():
        return []
    return sorted(base.glob("*/database/*/config.yaml"))


def list_personalities(root: Path) -> list[str]:
    """Names of all installed personalities (dirs under ``personalities/``)."""
    base = root / "personalities"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def resolve_default_personality(root: Path) -> str | None:
    """Read ``> **Default personality**: <name>`` from MEMORY.md.

    Returns the name, or ``None`` if MEMORY.md is absent / has no callout.
    """
    memory_md = root / "MEMORY.md"
    if not memory_md.is_file():
        return None
    match = _DEFAULT_PERSONALITY_RE.search(
        memory_md.read_text(encoding="utf-8", errors="ignore"),
    )
    return match.group(1).strip() if match else None


def discover_memory_config(root: Path, personality: str) -> Path | None:
    """The L3 journal SMAK config for one personality, if present."""
    cfg = root / "personalities" / personality / "memory" / "smak_config.yaml"
    return cfg if cfg.is_file() else None


# ---------------------------------------------------------------------------
# Runtime tool bodies (lazy smak import, after the cheap guards)
# ---------------------------------------------------------------------------


def _load_cfg(config_path: Path):
    """Load + embedding-init a SMAK config (lazy ``smak`` import)."""
    from smak.config import load_config, load_embedding_config
    from smak.factory import init_config

    return init_config(
        load_config(config_path),
        embedding_config=load_embedding_config(),
    )


def run_project_knowledge_search(
    root: Path, query: str, top_k: int = 8,
) -> dict:
    """Search every database workspace (code + docs + mesh), project-wide."""
    configs = discover_database_configs(root)
    if not configs:
        return {
            "empty": True,
            "reason": (
                "No database workspaces found. Tell the user the offline "
                "knowledge base is not indexed yet — do not guess."
            ),
        }
    from smak.core_ops import do_search_all  # lazy — heavy deps

    workspaces: list[dict] = []
    for cfg_path in configs:
        entry: dict = {"workspace": cfg_path.parent.name, "config": str(cfg_path)}
        try:
            entry["results"] = do_search_all(_load_cfg(cfg_path), query, top_k=top_k)
        except Exception as exc:  # never crash the tool — report per-workspace
            entry["error"] = str(exc)
        workspaces.append(entry)
    return {"query": query, "workspaces": workspaces}


def run_memory_recall(
    root: Path, query: str, personality: str | None = None, top_k: int = 5,
) -> dict:
    """Recall from one personality's L3 journal (default-personality scoped)."""
    name = personality or resolve_default_personality(root)
    if not name:
        return {
            "error": (
                "No personality resolved (MEMORY.md has no default and none "
                "was passed). Ask the user which personality, or pass "
                "`personality`."
            ),
            "available": list_personalities(root),
        }
    cfg_path = discover_memory_config(root, name)
    if cfg_path is None:
        return {
            "empty": True,
            "personality": name,
            "reason": (
                f"No memory index for personality '{name}'. Tell the user; "
                f"do not invent past context."
            ),
        }
    from smak.core_ops import do_search  # lazy — heavy deps

    return {
        "personality": name,
        "results": do_search(_load_cfg(cfg_path), query, index="journal", top_k=top_k),
    }


# ---------------------------------------------------------------------------
# FastMCP server (lazy mcp import) — mirrors SMAK's ``mcp.tool()(fn)`` pattern
# ---------------------------------------------------------------------------


def build_server():
    """Build the FastMCP instance with the two intent-named tools."""
    from mcp.server.fastmcp import FastMCP

    root = find_project_root()
    mcp = FastMCP("All-Might Knowledge")

    def project_knowledge_search(query: str, top_k: int = 8) -> dict:
        return run_project_knowledge_search(root, query, top_k=top_k)

    def memory_recall(
        query: str, personality: str | None = None, top_k: int = 5,
    ) -> dict:
        return run_memory_recall(root, query, personality=personality, top_k=top_k)

    # FastMCP reads the description from the function docstring (the
    # verified SMAK pattern). Set it from the single-source constants.
    project_knowledge_search.__doc__ = PROJECT_KNOWLEDGE_DESCRIPTION
    memory_recall.__doc__ = MEMORY_RECALL_DESCRIPTION

    mcp.tool()(project_knowledge_search)
    mcp.tool()(memory_recall)
    return mcp


def main() -> None:
    """Run the All-Might Knowledge MCP server over stdio transport."""
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
