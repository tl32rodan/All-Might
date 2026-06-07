"""Knowledge MCP wiring (Framework B, slice 2).

``allmight init`` registers the project-wide knowledge MCP server on
both surfaces: ``opencode.json#/mcp`` (OpenCode) and ``.mcp.json``
(Claude Code). Both point at ``allmight.mcp.knowledge_server`` and use
``setdefault`` semantics so a user-customised entry survives re-init.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from allmight.core.claude_bridge import (
    MCP_SERVER_NAME,
    claude_mcp_entry,
    opencode_mcp_entry,
    write_claude_bridge,
)
from allmight.core.personalities import write_init_scaffold


@pytest.fixture
def scaffolded(tmp_path: Path) -> Path:
    write_init_scaffold(tmp_path)
    return tmp_path


class TestOpencodeMcpBlock:
    def test_opencode_json_has_knowledge_server(self, scaffolded: Path) -> None:
        cfg = json.loads((scaffolded / ".opencode" / "opencode.json").read_text())
        entry = cfg["mcp"][MCP_SERVER_NAME]
        assert entry["type"] == "local"
        assert entry["command"] == ["python", "-m", "allmight.mcp.knowledge_server"]
        assert entry["enabled"] is True

    def test_schema_still_set(self, scaffolded: Path) -> None:
        cfg = json.loads((scaffolded / ".opencode" / "opencode.json").read_text())
        assert cfg["$schema"] == "https://opencode.ai/config.json"

    def test_user_customised_entry_survives_reinit(self, scaffolded: Path) -> None:
        path = scaffolded / ".opencode" / "opencode.json"
        cfg = json.loads(path.read_text())
        cfg["mcp"][MCP_SERVER_NAME]["command"] = ["my-python", "-m", "x"]
        cfg["mcp"]["user-server"] = {"type": "local", "command": ["foo"]}
        path.write_text(json.dumps(cfg))

        write_init_scaffold(scaffolded)  # re-init

        cfg2 = json.loads(path.read_text())
        # setdefault must not clobber the user's edit, and must preserve
        # their own server entry.
        assert cfg2["mcp"][MCP_SERVER_NAME]["command"] == ["my-python", "-m", "x"]
        assert cfg2["mcp"]["user-server"] == {"type": "local", "command": ["foo"]}


class TestClaudeMcpJson:
    def test_mcp_json_has_knowledge_server(self, scaffolded: Path) -> None:
        data = json.loads((scaffolded / ".mcp.json").read_text())
        entry = data["mcpServers"][MCP_SERVER_NAME]
        assert entry["type"] == "stdio"
        assert entry["command"] == "python"
        assert entry["args"] == ["-m", "allmight.mcp.knowledge_server"]

    def test_preserves_user_servers_and_edits(self, tmp_path: Path) -> None:
        path = tmp_path / ".mcp.json"
        path.write_text(json.dumps({"mcpServers": {
            "other": {"type": "stdio", "command": "node"},
            MCP_SERVER_NAME: {"type": "stdio", "command": "edited"},
        }}))
        write_claude_bridge(tmp_path)
        data = json.loads(path.read_text())
        assert data["mcpServers"]["other"]["command"] == "node"
        assert data["mcpServers"][MCP_SERVER_NAME]["command"] == "edited"


class TestEntryBuildersAreSingleSource:
    def test_both_surfaces_point_at_same_module(self) -> None:
        assert opencode_mcp_entry()["command"][-1] == "allmight.mcp.knowledge_server"
        assert claude_mcp_entry()["args"][-1] == "allmight.mcp.knowledge_server"
