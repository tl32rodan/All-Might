"""``scheduling`` skill body — agent how-to for periodic All-Might work.

Read at install time from ``templates/skills/scheduling/SKILL.md``.
Kept as a separate, plain text file so editors highlight the
Markdown body and so the wrapper here stays a 5-line lookup.

Naming convention: the slug for every job All-Might owns starts
with ``am-`` so user-managed jobs on the same scope are
distinguishable. See proposal P-3 in
``docs/schedule-proposal.md``.
"""

from __future__ import annotations

from pathlib import Path

_SKILL_MD = (
    Path(__file__).parent / "templates" / "skills" / "scheduling" / "SKILL.md"
)


SCHEDULING_SKILL_DESCRIPTION = (
    "Set up periodic All-Might tasks (curator audit, plugin status "
    "roll-up, L3 size sanity, etc.). Decision tree between "
    "opencode-scheduler MCP tools (OpenCode), Claude Code /loop or "
    "Desktop scheduled tasks, and external cron. Slugs use the "
    "prefix `am-<personality>-<task>` so allmight-owned jobs are "
    "distinguishable from user-managed ones on the same scope."
)


def build_scheduling_skill_md() -> str:
    """Return the body (no frontmatter) of the ``scheduling`` skill."""
    return _SKILL_MD.read_text()
