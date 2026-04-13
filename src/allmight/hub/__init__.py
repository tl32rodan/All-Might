"""Hub-level content for multi-workspace All-Might instances.

An All-Might hub manages N SMAK workspaces of the same type.
This package holds the CLAUDE.md and skill content that defines
the hub agent's worldview, delegation patterns, and self-improvement loop.

Each skill module provides:
- ``*_SKILL_NAME``: skill identifier (used as /slash-command name)
- ``*_SKILL_DESCRIPTION``: agent-facing description (for auto-invocation)
- ``*_SKILL_FRONTMATTER``: complete YAML frontmatter block (``--- ... ---``)
- ``*_SKILL_BODY``: markdown body content
- ``build_*_skill_md()``: assembles frontmatter + body into a complete SKILL.md
"""

from allmight.hub.claude_md_content import build_hub_claude_md
from allmight.hub.skill_detroit_smak import build_detroit_smak_skill_md
from allmight.hub.skill_enrich import build_enrich_skill_md
from allmight.hub.skill_self_improving import build_self_improving_skill_md
from allmight.hub.skill_sidecar_handling import build_sidecar_handling_skill_md

__all__ = [
    "build_hub_claude_md",
    "build_detroit_smak_skill_md",
    "build_enrich_skill_md",
    "build_self_improving_skill_md",
    "build_sidecar_handling_skill_md",
]
