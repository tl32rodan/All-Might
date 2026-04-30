"""Verify the deprecation shim at ``allmight.personalities`` works.

The package was renamed to ``allmight.capabilities`` in Part D. The
old import path stays usable for one release via a shim that
re-exports the new package's contents and emits a
``DeprecationWarning``. The tests below pin both halves of that
contract so a future regression doesn't silently re-break older
imports.
"""

from __future__ import annotations

import importlib
import sys
import warnings


def _purge(mod_prefix: str) -> None:
    """Drop cached imports starting with ``mod_prefix`` so the shim re-runs."""
    for key in [k for k in sys.modules if k == mod_prefix or k.startswith(mod_prefix + ".")]:
        del sys.modules[key]


def test_legacy_import_emits_deprecation_warning() -> None:
    _purge("allmight.personalities")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("allmight.personalities")
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("allmight.personalities" in str(w.message) for w in deprecations), \
        "shim must emit DeprecationWarning naming the old package"


def test_legacy_submodule_import_resolves_to_new_path() -> None:
    """`from allmight.personalities.corpus_keeper.scanner import X` still works.

    Python's import machinery creates a distinct module record for
    each name, so legacy and new modules aren't the *same* object —
    but they must back the same file and expose the same attributes.
    """
    _purge("allmight.personalities")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        legacy = importlib.import_module("allmight.personalities.corpus_keeper.scanner")
        new = importlib.import_module("allmight.capabilities.corpus_keeper.scanner")
    assert legacy.__file__ == new.__file__, \
        "shim must route legacy submodule imports to the new package's files"
    assert getattr(legacy, "ProjectScanner") is getattr(new, "ProjectScanner"), \
        "symbols imported via the legacy path must be identical to those at the new path"


def test_new_path_works_without_warning() -> None:
    _purge("allmight.capabilities")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("allmight.capabilities")
    deprecations = [
        w for w in caught
        if issubclass(w.category, DeprecationWarning)
        and "allmight.personalities" in str(w.message)
    ]
    assert not deprecations, "importing the new path must not warn"
