"""Shared-agent mode: project-root and role resolution.

Single source of truth for two opt-in env vars that let an All-Might
project be used by many users from any directory:

* ``ALLMIGHT_PROJECT_ROOT`` — absolute path to the shared project root.
  Plugins and hooks consult it before falling back to OpenCode's
  ``directory`` plugin-context value, ``CLAUDE_PROJECT_DIR``, or
  ``process.cwd()`` / ``os.getcwd()``. When unset, behaviour is
  unchanged from single-user mode.

* ``ALLMIGHT_ROLE`` — ``user`` (read-only) or ``owner`` (read-write).
  When unset, treated as ``owner`` so single-user setups keep writing.
  ``user`` causes write-bearing hooks (memory-history snapshot,
  reflection re-prime) to short-circuit cleanly instead of producing
  EACCES noise when the shared dir is mode-locked.

Per the dual-platform invariant in ``CLAUDE.md``, both the TypeScript
plugins and the Python hooks consume the **same** resolution shape via
the snippet helpers below — never hand-roll a second copy.
"""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT_ENV = "ALLMIGHT_PROJECT_ROOT"
ROLE_ENV = "ALLMIGHT_ROLE"
ROLE_USER = "user"
ROLE_OWNER = "owner"


def resolve_project_root_py() -> Path:
    """Return the project root for the current Python process.

    Precedence: ``ALLMIGHT_PROJECT_ROOT`` → ``CLAUDE_PROJECT_DIR`` →
    ``os.getcwd()``. The two env-var checks are independent: a Claude
    Code hook running outside the shared-agent setup still resolves via
    ``CLAUDE_PROJECT_DIR`` as it always did.
    """
    return Path(
        os.environ.get(PROJECT_ROOT_ENV)
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or os.getcwd()
    )


def is_read_only_py() -> bool:
    """Return True iff ``ALLMIGHT_ROLE`` is ``user``."""
    return os.environ.get(ROLE_ENV) == ROLE_USER


# ---------------------------------------------------------------------------
# Emitted snippets — keep TS and Python in lockstep.
# ---------------------------------------------------------------------------


# TS shape: same precedence as resolve_project_root_py, minus
# CLAUDE_PROJECT_DIR (TS plugins don't run under Claude Code). The
# ``directory`` parameter is OpenCode's plugin-context value.
TS_RESOLVE_CWD_EXPR = (
    "(process.env.ALLMIGHT_PROJECT_ROOT) "
    "|| (directory as string | undefined) "
    "|| process.cwd()"
)


# TS predicate: read-only role check.
TS_IS_READ_ONLY_EXPR = 'process.env.ALLMIGHT_ROLE === "user"'


# Python snippet for hooks: assigns ``cwd`` from the resolved root.
# Inlined verbatim so hooks stay self-contained (no all-might import).
PY_RESOLVE_CWD_SNIPPET = (
    'Path(os.environ.get("ALLMIGHT_PROJECT_ROOT") '
    'or os.environ.get("CLAUDE_PROJECT_DIR") '
    "or os.getcwd())"
)


# Python predicate for hooks: read-only role check (boolean).
PY_IS_READ_ONLY_EXPR = 'os.environ.get("ALLMIGHT_ROLE") == "user"'


# Bash prefix for command bodies. Expands to ``.`` (cwd) when the env
# var is unset, so single-user mode stays cwd-relative; in shared
# mode it expands to the absolute project root.
BASH_PROJECT_ROOT_PREFIX = "${ALLMIGHT_PROJECT_ROOT:-.}"
