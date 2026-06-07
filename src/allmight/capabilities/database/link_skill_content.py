"""Bundled ``/link`` skill and command content.

``/link`` is the agent-driven **knowledge-mesh builder**: it connects a
code symbol to the documentation that explains it (and back) by writing
SMAK sidecar relations (``smak enrich-symbol --relation --bidirectional``).
This is how the offline knowledge base becomes navigable when internal
code has no formal API docs — the agent builds links as it discovers
them, so a later ``project_knowledge_search`` of code surfaces the doc
and vice versa (SMAK's 1-hop mesh).

Framework B of ``docs/offline-reference-proposal.md``. It is the
**enrichment** surface that narrows the database read-only stance:
relations + intent (sidecar metadata) are writable; indexed source
content is still never edited through the agent.

Bodies live in ``templates/{skills,commands}/`` so editors highlight the
Markdown and the wrappers stay thin (the ``schedule`` convention).
"""

from __future__ import annotations

from pathlib import Path

from ...core.routing import ROUTING_PREAMBLE

_SKILL_MD = Path(__file__).parent / "templates" / "skills" / "link" / "SKILL.md"
_COMMAND_MD = Path(__file__).parent / "templates" / "commands" / "link.md"


LINK_SKILL_DESCRIPTION = (
    "Link a code symbol to the documentation that explains it (and "
    "back), building the searchable code<->doc knowledge mesh. Use when "
    "you discover a doc section that documents a code symbol — "
    "especially for internal code that has no formal API docs."
)


def build_link_skill_md() -> str:
    """Return the body (no frontmatter) of the ``link`` skill."""
    return _SKILL_MD.read_text()


def build_link_command_body() -> str:
    """Return the ``/link`` command body with the routing preamble."""
    return ROUTING_PREAMBLE + _COMMAND_MD.read_text()
