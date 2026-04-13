"""Hub-level CLAUDE.md generator.

Renders ``templates/CLAUDE.md.j2`` with workspace registry data to produce
the hub's top-level CLAUDE.md — the "One For All" constitution.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).parent / "templates"

MARKER = "<!-- ALL-MIGHT-HUB -->"


def build_hub_claude_md(
    *,
    hub_name: str,
    workspace_count: int,
    workspace_table: str,
    user_preferences: str = "",
) -> str:
    """Render the hub CLAUDE.md from the Jinja2 template.

    Parameters
    ----------
    hub_name:
        Human-readable name for this hub (e.g. "CAD Flow Knowledge Hub").
    workspace_count:
        Number of managed workspaces.
    workspace_table:
        Markdown table of workspaces (``| Name | Path | Description |`` ...).
    user_preferences:
        Optional markdown block for user preferences (autonomy, language, etc.).
        Omitted from the output when empty.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape([]),
        keep_trailing_newline=True,
    )
    template = env.get_template("CLAUDE.md.j2")
    return template.render(
        hub_name=hub_name,
        workspace_count=workspace_count,
        workspace_table=workspace_table,
        user_preferences=user_preferences,
    )
