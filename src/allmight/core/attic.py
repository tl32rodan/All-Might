"""Quarantine instead of delete.

``allmight init`` is additive: it writes new files and refreshes files
that carry an All-Might marker. When the framework stops shipping
something (a renamed plugin, a retired slash command), the stale file
does have to leave ``.opencode/`` — otherwise OpenCode keeps loading it
forever. But *deleting* it is the wrong move:

* the marker only proves All-Might wrote the file once, not that the
  bytes are still ours — copying one of our plugins as a starting point
  for your own copies the marker with it;
* an unrecoverable delete during a routine ``init`` is exactly the class
  of surprise this framework promises not to spring on you.

So retired files are **moved** to ``.allmight/attic/<original path>``
and reported. ``/sync`` teaches recovery; nothing is ever lost, and the
live agent surface still ends up clean.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ATTIC_DIRNAME = "attic"


def attic_root(project_root: Path) -> Path:
    """Return ``.allmight/attic/`` for *project_root*."""
    return project_root / ".allmight" / ATTIC_DIRNAME


def quarantine(project_root: Path, path: Path) -> Path | None:
    """Move *path* into the attic, mirroring its project-relative location.

    Returns the destination path, or ``None`` when the move failed or
    *path* does not exist. A pre-existing destination is never
    overwritten — ``.1``, ``.2``, … are appended instead, so repeated
    re-inits accumulate rather than clobber.

    Errors are swallowed: failing to retire a stale file must never
    break ``allmight init``.
    """
    try:
        if not path.exists() and not path.is_symlink():
            return None
        try:
            rel = path.relative_to(project_root)
        except ValueError:
            rel = Path(path.name)
        dest = attic_root(project_root) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            n = 1
            while True:
                candidate = dest.with_name(f"{dest.name}.{n}")
                if not candidate.exists() and not candidate.is_symlink():
                    dest = candidate
                    break
                n += 1
        shutil.move(str(path), str(dest))
        return dest
    except OSError:
        return None
