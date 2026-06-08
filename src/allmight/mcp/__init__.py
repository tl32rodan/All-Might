"""All-Might MCP runtime servers.

Spawned per-project by OpenCode / Claude Code via the ``mcp`` /
``mcpServers`` config that ``allmight init`` writes. These are *runtime*
components (like ``bridge/``), not capability templates and not ``core``.
They may import ``smak``; ``core`` must never import them.
"""
