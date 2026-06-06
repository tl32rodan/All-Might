"""Bundled ``/docs`` skill and command content.

``/docs`` is the offline documentation-lookup surface — the local
stand-in for ``web_search`` / ``context7`` when the workstation is
air-gapped. It searches a curated documentation corpus indexed as a
SMAK ``database`` workspace at
``personalities/<active>/database/docs/`` (manuals, library/API docs,
PDK files, internal wiki).

This is **Framework A** of the offline-reference design — skill-only,
no MCP wiring (Framework B adds the SMAK-backed MCP shim). The skill
description is deliberately
discovery-friendly so we can measure how often the model reaches for
``/docs`` on its own; that spontaneous-invocation rate is the
empirical gate before paying for the Framework B MCP shim (which
carries per-turn schema tokens + two-platform config drift). A
lightweight usage marker (``.allmight/usage/docs.log``, appended by
the body itself) records each invocation for that measurement —
touch-file simplicity, in the spirit of the plugin heartbeats.

Bodies live in ``templates/{skills,commands}/`` so editors highlight
the Markdown and the wrappers here stay thin lookups (the convention
the ``schedule`` capability established).
"""

from __future__ import annotations

from pathlib import Path

from ...core.routing import ROUTING_PREAMBLE

_SKILL_MD = Path(__file__).parent / "templates" / "skills" / "docs" / "SKILL.md"
_COMMAND_MD = Path(__file__).parent / "templates" / "commands" / "docs.md"


DOCS_SKILL_DESCRIPTION = (
    "Look up library/API signatures, tool flags, manuals, PDK files, "
    "or internal wiki content in the offline documentation corpus. Use "
    "this whenever you would otherwise web-search a fact or reach for "
    "context7 — this environment is air-gapped and this is their "
    "offline replacement for documentation."
)


def build_docs_skill_md() -> str:
    """Return the body (no frontmatter) of the ``docs`` skill."""
    return _SKILL_MD.read_text()


def build_docs_command_body() -> str:
    """Return the ``/docs`` command body with the routing preamble.

    The body uses the generic ``personalities/<active>/...`` placeholder;
    ``ROUTING_PREAMBLE`` teaches the agent how to resolve ``<active>``
    (same pattern as ``search.md``).
    """
    return ROUTING_PREAMBLE + _COMMAND_MD.read_text()
