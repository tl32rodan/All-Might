"""Sidecar-handling skill — SOS-based sidecar update SOP.

Template source: ``templates/skills/sidecar-handling/SKILL.md``
"""

from pathlib import Path

_SKILL_MD = Path(__file__).parent / "templates" / "skills" / "sidecar-handling" / "SKILL.md"


def build_sidecar_handling_skill_md() -> str:
    """Return the complete SKILL.md content for sidecar-handling."""
    return _SKILL_MD.read_text()
