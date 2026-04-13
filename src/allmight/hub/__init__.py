"""Hub-level content for multi-workspace All-Might instances.

An All-Might hub manages N SMAK workspaces of the same type.

Templates live in ``templates/`` as actual ``.md`` and ``.md.j2`` files:
- ``CLAUDE.md.j2`` — Jinja2 template for the hub constitution
- ``skills/*/SKILL.md`` — static SKILL.md files, ready to copy into ``.claude/skills/``

Each ``skill_*.py`` module provides a ``build_*_skill_md()`` function that
reads the template file and returns its content.
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
