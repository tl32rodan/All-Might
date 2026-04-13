"""Detroit-SMAK skill — precision strike via sub-agent.

Template source: ``templates/skills/detroit-smak/SKILL.md``
"""

from pathlib import Path

_SKILL_MD = Path(__file__).parent / "templates" / "skills" / "detroit-smak" / "SKILL.md"


def build_detroit_smak_skill_md() -> str:
    """Return the complete SKILL.md content for detroit-smak."""
    return _SKILL_MD.read_text()
