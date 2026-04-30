"""Deprecation shim — ``allmight.personalities`` was renamed to ``allmight.capabilities``.

The package was renamed in Part D to clarify the conceptual layering:
*personalities* are now user-facing role bundles under the project's
``personalities/`` directory, while *capabilities* (the Python templates
that know how to install ``database/`` and ``memory/`` data dirs) are a
framework-internal concept.

External code importing ``allmight.personalities`` (or any submodule)
keeps working through this shim — but emits a ``DeprecationWarning`` and
should migrate to ``allmight.capabilities`` before the shim is removed.

Implementation: a ``MetaPathFinder`` redirects every legacy import to
the new path so submodule classes/singletons remain identical across
both names. (A bare ``sys.modules[__name__] = _capabilities`` alias is
not enough — Python re-executes submodules under the alias and
produces distinct class objects, breaking ``isinstance`` checks.)
"""

from __future__ import annotations

import importlib
import sys
import warnings
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec

_LEGACY_PREFIX = "allmight.personalities"
_NEW_PREFIX = "allmight.capabilities"


class _RedirectLoader(Loader):
    """Resolve a legacy module name by importing the new one and aliasing."""

    def __init__(self, target_name: str) -> None:
        self._target_name = target_name

    def create_module(self, spec: ModuleSpec):  # type: ignore[override]
        target = importlib.import_module(self._target_name)
        sys.modules[spec.name] = target
        return target

    def exec_module(self, module) -> None:  # type: ignore[override]
        # Module is already initialised by the import in create_module.
        return None


class _LegacyPersonalitiesFinder(MetaPathFinder):
    """Redirect ``allmight.personalities[.X]*`` imports to the new path."""

    def find_spec(self, fullname: str, path=None, target=None):  # type: ignore[override]
        if fullname != _LEGACY_PREFIX and not fullname.startswith(_LEGACY_PREFIX + "."):
            return None
        target_name = _NEW_PREFIX + fullname[len(_LEGACY_PREFIX):]
        # Skip self-recursion if the new name is somehow already pending.
        if target_name == fullname:
            return None
        loader = _RedirectLoader(target_name)
        spec = ModuleSpec(fullname, loader)
        spec.submodule_search_locations = []  # treat as package so subimports route through us
        return spec


# Install the finder once. Idempotent across reloads.
if not any(isinstance(f, _LegacyPersonalitiesFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _LegacyPersonalitiesFinder())

warnings.warn(
    "allmight.personalities is deprecated; use allmight.capabilities. "
    "The shim re-exports submodules transparently and will be removed "
    "in a future release.",
    DeprecationWarning,
    stacklevel=2,
)

# Top-level alias so ``allmight.personalities`` returns the new package.
import allmight.capabilities as _capabilities  # noqa: E402

sys.modules[__name__] = _capabilities
