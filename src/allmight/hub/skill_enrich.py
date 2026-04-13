"""Enrich skill — know-how injection into a workspace's .claude/ layer.

Template source: ``templates/skills/enrich/SKILL.md``
"""

from pathlib import Path

_SKILL_MD = Path(__file__).parent / "templates" / "skills" / "enrich" / "SKILL.md"


def build_enrich_skill_md() -> str:
    """Return the complete SKILL.md content for enrich."""
    return _SKILL_MD.read_text()
