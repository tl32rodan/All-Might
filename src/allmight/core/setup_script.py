"""``setup.cshrc`` generator — shared-agent mode entry point.

Users source the generated file (``source /path/to/project/setup.cshrc``)
to use a shared All-Might project from any directory. Sourcing sets
``ALLMIGHT_PROJECT_ROOT`` (consumed by plugins/hooks via
:mod:`allmight.core.project_root`) and aliases ``opencode`` / ``allmight``
so the user does not need to ``cd`` into the project tree.

Single-user mode is unaffected — the script is only ever sourced when
the deployment actually uses shared mode.
"""

from __future__ import annotations

from .markers import ALLMIGHT_MARKER_CSH
from .project_root import PROJECT_ROOT_ENV, ROLE_ENV, ROLE_USER


SETUP_CSHRC_FILENAME = "setup.cshrc"


def setup_cshrc_body(project_root) -> str:
    """Return the marker'd ``setup.cshrc`` body for ``project_root``.

    csh has no portable way to identify the path of the sourced script
    (no ``${{BASH_SOURCE[0]}}`` equivalent; ``$_`` only works for
    interactive shells and ``$0`` is the shell name). So the absolute
    project path is **embedded at init time**. Re-running
    ``allmight init`` (from inside the project) re-generates the file
    with the current path, which matches the framework's idempotent-
    re-init contract for every other generated artifact.

    Role defaults to ``user`` (read-only) — the safe default for a
    shared deployment. An owner overrides by setting
    ``setenv ALLMIGHT_ROLE owner`` before sourcing.
    """
    from pathlib import Path

    root = Path(project_root).resolve()
    return f"""\
{ALLMIGHT_MARKER_CSH}
# Source this file (`source setup.cshrc`) to use this shared All-Might
# project from any working directory. Plugins and hooks read
# {PROJECT_ROOT_ENV} to resolve personality / memory paths back to the
# shared project regardless of cwd. The absolute path below is baked in
# at `allmight init` time; re-run init if the project moves.

setenv {PROJECT_ROOT_ENV} "{root}"

# Default role is read-only. The shared project owner sets
# `setenv {ROLE_ENV} owner` in their shell rc before sourcing.
if (! $?{ROLE_ENV}) setenv {ROLE_ENV} {ROLE_USER}

# OpenCode walks up from cwd to find opencode.json. Passing the
# project root as positional arg short-circuits that walk so it
# always reads the shared project's config.
alias opencode 'opencode "$ALLMIGHT_PROJECT_ROOT"'

# The allmight CLI uses `Path(".").resolve()` for its project root, so
# wrap it to cd into the shared dir first. `\\!*` is csh history
# expansion for "all remaining args".
alias allmight '( cd "$ALLMIGHT_PROJECT_ROOT" && allmight \\!* )'

echo "All-Might shared mode: project=$ALLMIGHT_PROJECT_ROOT role=$ALLMIGHT_ROLE"
"""


def write_setup_cshrc(project_root) -> None:
    """Write ``setup.cshrc`` into ``project_root`` if absent or owned.

    Idempotent via ``ALLMIGHT_MARKER_CSH``; user-customised versions
    without the marker are preserved by :func:`write_guarded` and the
    framework's copy is staged at
    ``.allmight/templates/setup.cshrc`` for ``/sync`` to merge.
    """
    from pathlib import Path

    from .safe_write import write_guarded

    target = Path(project_root) / SETUP_CSHRC_FILENAME
    write_guarded(target, setup_cshrc_body(project_root), ALLMIGHT_MARKER_CSH)
