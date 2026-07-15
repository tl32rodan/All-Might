"""Bundled working-discipline contract — framework-level, not capability-owned.

Air-gap deployments run on less-capable workstation models that
repeatedly cut the same corners: skipping TDD's RED stage, trusting a
built-in Grep/Glob surface that returns false "file not found",
forgetting user-aligned agreements after compaction, and narrowing
scope without saying so. The ``/whip-it`` skill is the user's whip —
a short, binding rule sheet the agent re-reads after every compaction
and on demand.

Architecture mirrors :mod:`allmight.core.opencode_reference`:

* The skill body lives as **plain markdown** at
  ``data/whip_it/_skill_body.md`` next to this module — editing the
  rules is pure markdown, no Python string escaping.
* :func:`write_whip_it` installs ``.opencode/skills/whip-it/SKILL.md``
  plus the ``/whip-it`` command via ``install_skill``. The command
  body references ``personalities/<active>/...`` paths, so it prepends
  ``ROUTING_PREAMBLE`` per the routing contract.
* A short section in ``_AGENTS_MD_FRAMEWORK_PRIMER``
  (``core/personalities.py``) keeps the pointer visible from the
  highest-level surface — the same surface rule 4 tells the agent to
  re-read after compaction, which closes the loop.

Framework-level (called from ``personalities.write_init_scaffold``):
no personality owns it and no per-personality data dir is created, so
it does not live under ``capabilities/``. No staging path — the rule
sheet is framework-owned reminder content, exactly like the OpenCode
reference bundle. Project-specific agreements (rule 3) belong in
``MEMORY.md`` / L2 memory, **not** in edits to this skill body; a user
who nevertheless wants a private copy clears the marker and re-init
preserves it.
"""

from __future__ import annotations

from pathlib import Path

from .routing import ROUTING_PREAMBLE
from .skill_io import install_skill


_DATA_DIR = Path(__file__).parent / "data" / "whip_it"
"""Directory holding the markdown source.

Resolves under both editable installs and hatchling-built wheels
(``packages = ["src/allmight"]`` ships every file under the path).
"""

_SKILL_BODY_FILE = "_skill_body.md"
"""The ``/whip-it`` skill body source (underscore = not user-facing
reference content, same convention as ``opencode_reference``)."""


WHIP_IT_SKILL_DESCRIPTION = (
    "Binding working-discipline contract — TDD-first (RED before any "
    "production code), native Unix search instead of built-in "
    "Grep/Glob, recorded agreements over general convention, "
    "post-compaction re-anchoring, full scope with real output. "
    "Load after every compaction and before starting development "
    "work; the user invokes /whip-it to re-assert it on demand."
)


def build_whip_it_skill_body() -> str:
    """Return the body (no frontmatter) of the ``whip-it`` skill."""
    return (_DATA_DIR / _SKILL_BODY_FILE).read_text(encoding="utf-8")


def build_whip_it_command_body() -> str:
    """Return the ``/whip-it`` command body (with routing preamble)."""
    return ROUTING_PREAMBLE + _WHIP_IT_COMMAND_BODY


_WHIP_IT_COMMAND_BODY = """\
Re-assert the project's working-discipline contract.

1. Read `.opencode/skills/whip-it/SKILL.md` in full.
2. Answer its "Self-check on /whip-it" questions against the current
   session, honestly, in one short block.
3. Re-anchor: re-read `AGENTS.md`, `MEMORY.md`,
   `personalities/<active>/ROLE.md`, and
   `personalities/<active>/memory/understanding/_index.md`.
4. Report every violation found, fix course, then continue the task
   that was in flight.

If the user named a specific rule when invoking the command, address
that rule first.
"""


def write_whip_it(project_root: Path) -> None:
    """Install the ``/whip-it`` skill + command.

    Framework-level — called from
    :func:`allmight.core.personalities.write_init_scaffold` on both
    fresh init and re-init. ``write_guarded`` refreshes marker-kept
    files and preserves user-un-markered ones.
    """
    install_skill(
        project_root,
        name="whip-it",
        description=WHIP_IT_SKILL_DESCRIPTION,
        skill_body=build_whip_it_skill_body(),
        command_body=build_whip_it_command_body(),
    )
