"""Self-improving skill — hub-level audit and evolution.

Template source: ``templates/skills/self-improving/SKILL.md``
"""

from pathlib import Path

_SKILL_MD = Path(__file__).parent / "templates" / "skills" / "self-improving" / "SKILL.md"


def build_self_improving_skill_md() -> str:
    """Return the complete SKILL.md content for self-improving."""
    return _SKILL_MD.read_text()
