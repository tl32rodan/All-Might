"""F1.5 — module entry for the Stop hook.

Invoked from ``.claude/hooks/memory-cap.sh`` as::

    python3 -m allmight.memory.cap_audit <project_dir>

Runs an L1 audit and writes/removes the ``memory/.l1-over-cap`` sentinel
based on whether MEMORY.md's body exceeds the cap. Never modifies
MEMORY.md. Must never block Stop — errors go to stderr, exit code stays
informational.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .l1_rewriter import audit_and_update_sentinel


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python3 -m allmight.memory.cap_audit <project_dir>",
              file=sys.stderr)
        return 2

    project_dir = Path(args[0])
    if not project_dir.is_dir():
        print(f"cap_audit: not a directory: {project_dir}", file=sys.stderr)
        return 2

    audit_and_update_sentinel(project_dir)
    return 0


# Re-export for direct imports (tests hit this path).
__all__ = ["main", "audit_and_update_sentinel"]


if __name__ == "__main__":
    raise SystemExit(main())
