"""Overwrite-guarded file writer.

Used by the initializer to make ``allmight init`` safe to run inside a
populated directory (e.g. ``$HOME``).  A generated marker is prepended
to every emitted file; on a subsequent write, an existing path whose
contents do not contain the marker is left untouched and a warning is
printed.
"""

from __future__ import annotations

import sys
from pathlib import Path


def write_guarded(
    path: Path, content: str, marker: str, force: bool = False
) -> bool:
    """Write *content* to *path*, skipping if *path* exists without our marker.

    The *marker* line is prepended to *content* if not already present so
    that subsequent writes can recognize the file as ours.

    Returns ``True`` if the file was written, ``False`` if it was skipped
    because the existing file lacks the marker (i.e. it isn't ours).

    Pass ``force=True`` to bypass the guard — used by ``allmight init
    --force`` to deliberately overwrite even user-modified files.
    """
    if marker not in content:
        content = marker + "\n" + content
    if not force and path.exists():
        try:
            existing = path.read_text()
        except OSError:
            existing = ""
        if marker not in existing:
            print(
                f"warn: skipping {path} — exists without All-Might marker; "
                f"delete or rename to allow regeneration",
                file=sys.stderr,
            )
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return True
