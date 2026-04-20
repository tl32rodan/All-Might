"""Marker-bounded writer for ``.claude/settings.json`` hook entries.

All-Might needs to register its hooks (``memory-cap.sh``,
``memory-nudge.sh``, ``memory-load.sh``) without clobbering whatever
the user has already placed in ``settings.json``.

Contract:

- Each entry All-Might writes carries ``"_allmight_managed": true``.
- ``merge_hooks`` drops any *existing* managed entry before inserting
  the fresh set, so upgrades cleanly replace outdated commands.
- Entries without the flag are considered user-owned and preserved.
- Top-level keys outside ``"hooks"`` are never touched.
- Malformed input is treated as an empty config so init never crashes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MANAGED_FLAG = "_allmight_managed"


def _load(settings_path: Path) -> dict[str, Any]:
    if not settings_path.exists():
        return {}
    try:
        return json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def merge_hooks(settings_path: Path, hooks: dict[str, list[dict[str, Any]]]) -> None:
    """Merge *hooks* into ``settings.json`` under the ``hooks`` key.

    *hooks* maps event name (``"Stop"``, ``"UserPromptSubmit"``, ...) to
    a list of hook entries (each at minimum ``{"command": "..."}``).
    Every entry is stamped with :data:`MANAGED_FLAG` before it lands in
    the file.

    Running this function twice with the same *hooks* produces a
    byte-identical file.
    """
    settings = _load(settings_path)
    existing_hooks: dict[str, list[dict[str, Any]]] = settings.get("hooks") or {}

    merged: dict[str, list[dict[str, Any]]] = {}

    all_events = set(existing_hooks) | set(hooks)
    for event in sorted(all_events):
        user_entries = [
            entry
            for entry in existing_hooks.get(event, [])
            if not entry.get(MANAGED_FLAG)
        ]
        managed_entries = [
            {**entry, MANAGED_FLAG: True}
            for entry in hooks.get(event, [])
        ]
        combined = user_entries + managed_entries
        if combined:
            merged[event] = combined

    settings["hooks"] = merged

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")


__all__ = ["merge_hooks", "MANAGED_FLAG"]
