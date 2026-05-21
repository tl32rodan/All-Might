"""Bundled OpenCode reference — framework-level, not capability-owned.

We frequently generate ``.opencode/plugins/*.ts``, ``.opencode/agents/
<name>.md`` and slash-command files. The Python test suite verifies
**what strings we wrote**, not whether the result is a well-shaped
OpenCode artefact (see *Discipline When Generating Third-Party
Integrations* in CLAUDE.md). Agents that author or modify those files
need an offline reminder of the API conventions; this module bundles
that reminder.

Architecture:

* Cheat-sheet content lives as **plain markdown** under
  ``data/opencode_reference/`` next to this module. ``write_init_
  scaffold`` reads each one, substitutes ``__OPENCODE_VERSION__``,
  prepends the All-Might marker, and writes the result under
  ``.opencode/reference/opencode/``. Editing the cheat-sheets is
  pure markdown — no Python string escaping, no f-string traps.
* A companion skill at ``.opencode/skills/opencode-ref/SKILL.md``
  exists so the agent has an autoload-discoverable pointer back at
  the cheat-sheets when a relevant task arises. Its body lives at
  ``data/opencode_reference/_skill_body.md`` (the leading underscore
  marks it as "not a user-facing cheat-sheet").
* A short section gets stitched into ``AGENTS.md`` by
  ``_AGENTS_MD_FRAMEWORK_PRIMER`` (in ``core/personalities.py``) so
  the pointer is visible from the highest-level surface, not buried
  in a skill that may not load.

This module is framework-level (called from
``personalities.write_init_scaffold``) and therefore does not live
under ``capabilities/`` — no personality owns it, no per-personality
data dir is created. Re-init refreshes the markered files via
``write_guarded``; user-edited (marker-removed) versions are
preserved exactly like ``role-load.ts`` / ``reflection.ts``.
"""

from __future__ import annotations

from pathlib import Path

from .markers import ALLMIGHT_MARKER_MD
from .safe_write import write_guarded
from .skill_io import install_skill


OPENCODE_VERSION = "1.14.28"
"""The upstream OpenCode version the cheat-sheets were authored against.

Surfaced verbatim in the bundled ``README.md`` so a reader can decide
whether to cross-check upstream when something looks off. We do not
runtime-check the installed OpenCode against this — the cheat-sheets
focus on shapes that have been stable across the 1.x line, and a
stale snapshot is still a better starting point than guessing.
"""


_VERSION_PLACEHOLDER = "__OPENCODE_VERSION__"
"""Token the markdown sources use where ``OPENCODE_VERSION`` belongs.

Sentinel-style (``__NAME__``) matches the convention used elsewhere
in the codebase for content-to-substitute (see ``plugin_telemetry.py``
shared-constant injection into generated ``.ts``).
"""


_DATA_DIR = Path(__file__).parent / "data" / "opencode_reference"
"""Directory holding the markdown sources.

Resolves correctly under both editable installs (where the source
tree is the install location) and hatchling-built wheels (where
``packages = ["src/allmight"]`` includes every file under that path,
so the wheel ships the ``.md`` files next to this module).
"""


_CHEAT_SHEET_FILES: tuple[str, ...] = (
    "README.md",
    "plugins.md",
    "agents.md",
    "skills-commands.md",
    "config.md",
)
"""Explicit list of cheat-sheet sources copied to ``.opencode/reference/opencode/``.

Hardcoded rather than discovered by ``glob`` so adding a new
cheat-sheet is intentional (and visible in code review) instead of a
side-effect of dropping a file in the data directory.
"""

_SKILL_BODY_FILE = "_skill_body.md"
"""The ``/opencode-ref`` skill body.

Lives in the same data dir as the cheat-sheets — the leading
underscore distinguishes it so :data:`_CHEAT_SHEET_FILES` can stay
explicit without accidentally sweeping the skill body into the
user-facing reference directory.
"""


_OPENCODE_REF_SKILL_DESCRIPTION = (
    "Use BEFORE authoring or modifying any file under `.opencode/` "
    "(plugins, agents, slash commands, opencode.json). Points at the "
    "bundled OpenCode cheat-sheets at `.opencode/reference/opencode/`."
)


def _read_md(filename: str) -> str:
    """Load a markdown source from the data dir with version substitution.

    The placeholder :data:`_VERSION_PLACEHOLDER` is replaced wherever
    it appears in the source. Substitution is unconditional — sources
    that do not use the placeholder pass through unchanged at zero
    cost (Python's ``str.replace`` is a no-op when the needle is
    absent).
    """
    raw = (_DATA_DIR / filename).read_text(encoding="utf-8")
    return raw.replace(_VERSION_PLACEHOLDER, OPENCODE_VERSION)


def write_opencode_reference(project_root: Path) -> None:
    """Write the OpenCode reference bundle + the `/opencode-ref` skill.

    Framework-level — called from
    :func:`allmight.core.personalities.write_init_scaffold`. Both fresh
    init and re-init invoke this; ``write_guarded`` preserves files
    the user has deliberately un-markered. Marker-kept files refresh
    in place — same trade-off as ``role-load.ts`` / ``reflection.ts``
    and the other framework scaffold files.

    No staging path: this is a "reminder" bundle whose content is
    framework-owned, not a per-project artefact. If we add new
    upstream content, every project picks it up at next ``allmight
    init`` without `/sync` ceremony. Users who want a private copy
    just clear the marker on the affected file.
    """
    ref_dir = project_root / ".opencode" / "reference" / "opencode"
    ref_dir.mkdir(parents=True, exist_ok=True)

    for filename in _CHEAT_SHEET_FILES:
        write_guarded(
            ref_dir / filename,
            _read_md(filename),
            ALLMIGHT_MARKER_MD,
        )

    install_skill(
        project_root,
        name="opencode-ref",
        description=_OPENCODE_REF_SKILL_DESCRIPTION,
        skill_body=_read_md(_SKILL_BODY_FILE),
    )
