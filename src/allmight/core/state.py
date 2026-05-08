"""Centralized read/write for ``.allmight/*.yaml`` state files.

Two state files live under ``.allmight/``:

* ``onboard.yaml`` — captured by ``allmight init`` and consumed by
  the agent-side ``/onboard`` skill. Records the personalities the
  CLI prompt collected (or ``[]`` when init defers to ``/onboard``)
  plus the ``onboarded: bool`` flag. Functions: :func:`read_onboard`,
  :func:`write_onboard`.
* ``personalities.yaml`` — the registry of installed personalities
  consumed by ``allmight list`` and the agent-side routing logic.
  Functions: :func:`read_registry`, :func:`write_registry` (defined
  in :mod:`allmight.core.personalities` and re-exported here so all
  state I/O can be imported from one place).

The two functions in this module wrap a few lines of YAML I/O. The
goal is colocation, not abstraction — adding a new state file is
"add a path constant + read/write pair here" rather than scattering
inline ``yaml.safe_load`` calls across modules.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .personalities import read_registry, write_registry  # noqa: F401  (re-export)

__all__ = [
    "onboard_path",
    "read_onboard",
    "write_onboard",
    "read_registry",
    "write_registry",
]


def onboard_path(project_root: Path) -> Path:
    """Return the path to ``<project_root>/.allmight/onboard.yaml``."""
    return project_root / ".allmight" / "onboard.yaml"


def read_onboard(project_root: Path) -> dict | None:
    """Return the captured onboarding state, or ``None`` if absent or unreadable.

    Always normalises the returned dict to have the three keys
    ``onboarded`` (bool), ``personalities`` (list), ``folders`` (list)
    so callers don't have to ``setdefault`` themselves.
    """
    path = onboard_path(project_root)
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (yaml.YAMLError, OSError):
        return None
    data.setdefault("onboarded", False)
    data.setdefault("personalities", [])
    data.setdefault("folders", [])
    return data


def write_onboard(project_root: Path, data: dict) -> None:
    """Persist onboarding state for the agent-side ``/onboard`` skill."""
    path = onboard_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
