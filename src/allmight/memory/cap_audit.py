"""L1 cap-audit entry point — invoked by hooks as a script.

Thin module so external runtimes (OpenCode plugin, ad-hoc Stop hooks)
can call ``python3 -m allmight.memory.cap_audit <project_dir>`` without
importing the broader ``l1_rewriter`` surface. The actual auditing logic
lives in ``l1_rewriter``; this module only exposes it as a CLI.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .l1_rewriter import audit_and_update_sentinel

__all__ = ["audit_and_update_sentinel", "main"]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python -m allmight.memory.cap_audit <project_dir>", file=sys.stderr)
        return 2
    project_dir = Path(args[0])
    audit_and_update_sentinel(project_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
