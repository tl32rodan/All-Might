"""Touch-file heartbeats for All-Might plugins.

This module is the source of truth for the simplest-possible plugin
observability: each plugin / Claude hook touches a marker file when
it fires, and ``allmight plugin status`` reads the marker mtimes.

The Python helpers are used by:
  * the CLI (``allmight plugin status``) — reads ``heartbeats/`` and
    pretty-prints "fired N ago" lines;
  * tests — assert that a plugin or hook wrote a heartbeat.

The string snippets (`TS_HEARTBEAT_SNIPPET`, `PY_HEARTBEAT_SNIPPET`)
are inlined verbatim into generated TS plugins and Python hooks. They
are intentionally short and self-contained so each plugin keeps its
own copy — no cross-plugin module import, no shared runtime.

See ``docs/plugin-observability.md`` for the design rationale.
"""

from __future__ import annotations

import os
from pathlib import Path


SURFACE_OPENCODE = "oc"
SURFACE_CLAUDE = "cc"


def heartbeats_root(project_root: Path) -> Path:
    """Return the heartbeats directory for ``project_root``."""
    return project_root / ".allmight" / "plugins" / "heartbeats"


def emit_heartbeat(
    name: str,
    surface: str = SURFACE_CLAUDE,
    root: Path | None = None,
) -> None:
    """Touch ``heartbeats/<surface>/<name>``. Used by tests + helpers.

    Errors are swallowed: a heartbeat write failure must never break
    the caller. The CLI will simply show "never fired" for the plugin.
    """
    try:
        base = root or Path(
            os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        )
        d = heartbeats_root(base) / surface
        d.mkdir(parents=True, exist_ok=True)
        (d / name).touch()
    except Exception:
        pass


def read_heartbeats(project_root: Path) -> dict[str, dict[str, float]]:
    """Return ``{surface: {name: mtime}}`` for the project.

    Empty surfaces return empty maps. The CLI uses this to print the
    status table.
    """
    out: dict[str, dict[str, float]] = {
        SURFACE_OPENCODE: {},
        SURFACE_CLAUDE: {},
    }
    base = heartbeats_root(project_root)
    if not base.is_dir():
        return out
    for surface_dir in sorted(base.iterdir()):
        if not surface_dir.is_dir():
            continue
        entries = out.setdefault(surface_dir.name, {})
        for entry in surface_dir.iterdir():
            if entry.is_file():
                try:
                    entries[entry.name] = entry.stat().st_mtime
                except OSError:
                    continue
    return out


KNOWN_OPENCODE_PLUGINS: tuple[str, ...] = (
    "role-load",
    "reflection",
    "memory-load",
    "memory-history",
    "remember-trigger",
    "todo-curator",
    "trajectory-writer",
    "usage-logger",
)

KNOWN_CLAUDE_HOOKS: tuple[str, ...] = (
    "role_load",
    "reflection",
    "memory_load",
    "memory_history",
)


TS_HEARTBEAT_SNIPPET = """\
// --- All-Might plugin heartbeat (do not edit) ---
import { mkdirSync as __hb_mkdir, utimesSync as __hb_utimes, openSync as __hb_open, closeSync as __hb_close } from "node:fs";
import { join as __hb_join } from "node:path";

function emitHeartbeat(name: string, cwd?: string): void {
  try {
    const base = cwd ?? process.cwd();
    const dir = __hb_join(base, ".allmight", "plugins", "heartbeats", "oc");
    __hb_mkdir(dir, { recursive: true });
    const p = __hb_join(dir, name);
    const now = new Date();
    try {
      __hb_utimes(p, now, now);
    } catch {
      __hb_close(__hb_open(p, "w"));
    }
  } catch {
    // heartbeats must never throw
  }
}
// --- end heartbeat ---
"""


PY_HEARTBEAT_SNIPPET = '''\
# --- All-Might plugin heartbeat (do not edit) ---
def _hb(name):
    try:
        import os as _hb_os
        from pathlib import Path as _hb_Path
        base = _hb_Path(_hb_os.environ.get("CLAUDE_PROJECT_DIR") or _hb_os.getcwd())
        d = base / ".allmight" / "plugins" / "heartbeats" / "cc"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).touch()
    except Exception:
        pass  # heartbeats must never throw
# --- end heartbeat ---
'''
