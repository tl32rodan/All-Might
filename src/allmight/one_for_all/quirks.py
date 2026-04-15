"""Agent Quirks — per-agent capability adaptation.

Different agents have different "quirks" (capabilities), like context window
size, tool call patterns, and native integrations. This module provides
agent-specific recommendations for SKILL.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentQuirk:
    """Capability profile for a specific agent type."""

    name: str
    context_window: int  # in tokens
    max_tool_calls: int  # per session
    supports_subagents: bool
    supports_skills: bool  # Claude Code native skills
    notes: list[str]


# Known agent profiles
QUIRKS: dict[str, AgentQuirk] = {
    "claude-code": AgentQuirk(
        name="Claude Code",
        context_window=200_000,
        max_tool_calls=500,
        supports_subagents=True,
        supports_skills=True,
        notes=[
            "Native skill loading from .claude/skills/",
            "Slash commands from .claude/commands/",
            "Can spawn sub-agents for parallel work",
            "Use Agent tool for heavy exploration tasks",
        ],
    ),
    "kimi": AgentQuirk(
        name="Kimi 2.5",
        context_window=256_000,
        max_tool_calls=300,
        supports_subagents=True,
        supports_skills=False,
        notes=[
            "256K context — can ingest entire SKILL.md + large files",
            "Agent Swarm up to 100 parallel sub-agents",
            "Read SKILL.md manually at session start",
            "MCP server connection required for knowledge graph tools",
        ],
    ),
    "gpt": AgentQuirk(
        name="GPT (OpenAI)",
        context_window=128_000,
        max_tool_calls=100,
        supports_subagents=False,
        supports_skills=False,
        notes=[
            "128K context — may need summarized SKILL.md for large projects",
            "Read SKILL.md manually at session start",
            "MCP server connection required for knowledge graph tools",
            "Be more selective with search — fewer tool calls available",
        ],
    ),
}


def get_quirk(agent_type: str) -> AgentQuirk | None:
    """Get the quirk profile for a known agent type."""
    return QUIRKS.get(agent_type.lower())


def get_agent_notes(agent_type: str) -> list[str]:
    """Get agent-specific notes for embedding in SKILL.md."""
    quirk = get_quirk(agent_type)
    if quirk:
        return quirk.notes
    return ["Unknown agent type — follow the general guidelines in this skill."]
