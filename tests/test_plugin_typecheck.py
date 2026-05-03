"""Static type-check the generated TS plugins via ``tsc --noEmit``.

The Python tests under ``tests/test_memory_init.py`` and
``tests/test_plugin_runtime_iteration.py`` assert *that the right
strings get written* into the generated ``.ts`` files. They do not
catch type errors. Plugin authors today only learn about a typing
mistake when OpenCode tries to load the plugin under Bun and crashes
— a slow feedback loop.

This file closes that gap: it runs ``allmight init`` against a fresh
``tmp_path``, then drives ``npm install`` + ``npx tsc --noEmit``
against the generated ``.opencode/`` tree. Any type or syntax error
in the emitted ``.ts`` body fails the test.

The test is **skipped** (not failed) when ``npm`` and ``npx`` aren't
on PATH, so contributors without a Node toolchain can still run
``pytest tests/`` cleanly. CI runners (which install Node) catch the
drift.

Performance note: ``npm install`` against a fresh directory takes
~30 seconds the first time. To amortise across the few tests in
this file, the install is performed once per pytest session via a
``session``-scoped fixture and the populated ``node_modules`` is
copied into each test's tmp_path.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from allmight.capabilities.memory.initializer import MemoryInitializer


_NODE_TOOLCHAIN_AVAILABLE = bool(shutil.which("npm")) and bool(shutil.which("npx"))

pytestmark = pytest.mark.skipif(
    not _NODE_TOOLCHAIN_AVAILABLE,
    reason="npm/npx not on PATH; type-check tests skipped",
)


@pytest.fixture(scope="session")
def _node_modules_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One-time ``npm install`` against a fresh ``.opencode/`` so each
    individual test only has to copy the tree (fast) instead of
    re-downloading.
    """
    cache_root = tmp_path_factory.mktemp("typecheck-cache")
    project = cache_root / "seed"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("def f(): pass\n")
    (project / "pyproject.toml").write_text("[project]\nname='seed'\n")
    MemoryInitializer().initialize(project)

    opencode = project / ".opencode"
    proc = subprocess.run(
        ["npm", "install", "--silent"],
        cwd=str(opencode),
        capture_output=True, text=True, timeout=240,
    )
    assert proc.returncode == 0, (
        f"npm install (one-time) failed: "
        f"{proc.stderr[-1500:] or proc.stdout[-1500:]}"
    )
    return opencode


@pytest.fixture
def initted_project(tmp_path: Path, _node_modules_cache: Path) -> Path:
    """A fresh init'd project whose ``.opencode/node_modules`` is
    seeded from the session-scoped cache."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def f(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    MemoryInitializer().initialize(tmp_path)

    # Copy node_modules + lockfile from the cache so we don't pay
    # network cost per test. The cache and the test dir agree on
    # package.json content (same allmight version), so its
    # node_modules content is valid here.
    src_modules = _node_modules_cache / "node_modules"
    dst_modules = tmp_path / ".opencode" / "node_modules"
    if src_modules.is_dir():
        shutil.copytree(src_modules, dst_modules, symlinks=True)
    pkg_lock = _node_modules_cache / "package-lock.json"
    if pkg_lock.is_file():
        shutil.copy2(pkg_lock, tmp_path / ".opencode" / "package-lock.json")

    return tmp_path


def _run_tsc(opencode_dir: Path) -> subprocess.CompletedProcess:
    """Run ``npx tsc --noEmit -p tsconfig.json`` in ``opencode_dir``."""
    return subprocess.run(
        [
            "npx", "-y", "-p", "typescript@5.4",
            "tsc", "--noEmit", "-p", "tsconfig.json",
        ],
        cwd=str(opencode_dir),
        capture_output=True, text=True, timeout=180,
    )


class TestPluginTypeCheck:
    def test_generated_plugins_typecheck_cleanly(
        self, initted_project: Path,
    ) -> None:
        """The .opencode/plugins/*.ts emitted by init must pass
        ``tsc --noEmit`` against the shipped tsconfig + @types/node."""
        proc = _run_tsc(initted_project / ".opencode")
        if proc.returncode != 0:
            pytest.fail(
                "tsc --noEmit reported errors in the generated TS:\n\n"
                + (proc.stdout[-3000:] or proc.stderr[-3000:])
            )

    def test_tsc_catches_a_synthetic_error(
        self, initted_project: Path,
    ) -> None:
        """Sanity meta-test: if we *introduce* a type error into a
        generated plugin, ``tsc --noEmit`` must fail.

        Without this check, a silently-broken type-check pipeline
        would let real bugs through with a green CI.
        """
        plugin = (
            initted_project / ".opencode" / "plugins" / "memory-load.ts"
        )
        original = plugin.read_text()
        # A type error tsc will reject: assigning a string to a number
        # variable. Append, don't replace, so the plugin still parses.
        plugin.write_text(
            original
            + "\n\n// injected by test_tsc_catches_a_synthetic_error\n"
            + "const __test_should_fail: number = 'oops';\n",
        )
        try:
            proc = _run_tsc(initted_project / ".opencode")
        finally:
            plugin.write_text(original)
        assert proc.returncode != 0, (
            "tsc returned 0 on a deliberately broken file — the "
            "type-check pipeline is not actually checking. "
            f"stdout:\n{proc.stdout[-1000:]}"
        )
