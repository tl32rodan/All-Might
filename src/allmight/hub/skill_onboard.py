"""Onboard skill — hub identity discovery via casual conversation.

Template source: ``templates/skills/onboard/SKILL.md``
"""

from pathlib import Path

_SKILL_MD = Path(__file__).parent / "templates" / "skills" / "onboard" / "SKILL.md"


def build_onboard_skill_md() -> str:
    """Return the complete SKILL.md content for onboard."""
    return _SKILL_MD.read_text()
