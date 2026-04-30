"""Plugin runtime iteration over personalities/*/.

Part-D commit 4 contract: TS plugins that write per-personality
memory data must discover the memory dirs by iterating
``personalities/*/memory/`` at runtime. Adding a new personality
should not require a plugin code change.

Rationale: pre-Part-D the plugins hardcoded ``cwd/memory/...``,
which only worked for single-instance projects. Part-D supports N
personalities each with their own memory dir; plugins must adapt.

The 5 generated plugins split across two responsibilities:

* **No memory-data writes** — ``memory-load.ts`` reads project-root
  ``MEMORY.md`` only; ``role-load.ts`` already iterates
  ``personalities/*/ROLE.md``; ``remember-trigger.ts`` keeps
  in-memory state only. These need no change.
* **Per-personality memory writes** — ``usage-logger.ts``,
  ``todo-curator.ts``, ``trajectory-writer.ts`` all need to
  resolve which personality's ``memory/`` dir to write into. They
  iterate ``personalities/*/`` at runtime.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from allmight.capabilities.memory.initializer import MemoryInitializer


# Plugins that produce per-personality memory writes.
DATA_WRITER_PLUGINS = (
    "usage-logger.ts",
    "todo-curator.ts",
    "trajectory-writer.ts",
)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    return tmp_path


def _plugin(project_root: Path, name: str) -> str:
    f = project_root / ".opencode" / "plugins" / name
    assert f.exists(), f"plugin {name} not generated"
    return f.read_text()


class TestDataWriterPluginsIteratePersonalities:
    def test_plugins_reference_personalities_dir(self, project_root: Path) -> None:
        """Each data-writer plugin must mention ``personalities/``,
        proving it knows about the per-personality tree."""
        MemoryInitializer().initialize(project_root)
        for name in DATA_WRITER_PLUGINS:
            content = _plugin(project_root, name)
            assert "personalities" in content, (
                f"{name} must reference the personalities/ tree to discover "
                f"per-instance memory dirs at runtime."
            )

    def test_plugins_iterate_via_readdirsync(self, project_root: Path) -> None:
        """Iteration uses ``readdirSync`` over the personalities dir at
        runtime — not a static list baked at install time."""
        MemoryInitializer().initialize(project_root)
        for name in DATA_WRITER_PLUGINS:
            content = _plugin(project_root, name)
            assert re.search(r"readdirSync\(", content), (
                f"{name} must call readdirSync to iterate personalities/ at runtime."
            )

    def test_plugins_do_not_hardcode_concrete_personality_in_string_literal(
        self, project_root: Path,
    ) -> None:
        """A plugin must not hardcode a concrete personality name as a
        string literal anchored at ``personalities/``.

        Allowed: agent-readable placeholders like ``personalities/<X>/``
        used inside narrative comments (the angle brackets prove it's a
        placeholder).

        Rejected: literal ``"personalities/knowledge/"`` etc., which is
        the pre-Part-D anti-pattern this commit eliminates.
        """
        MemoryInitializer().initialize(project_root)
        # Match a string literal segment ``personalities/<token>/``
        # where token is a word starting with a lowercase letter and
        # not containing template-bracket characters.
        offender_re = re.compile(r'"personalities/([a-z][a-z0-9_]*)/')
        for name in DATA_WRITER_PLUGINS:
            content = _plugin(project_root, name)
            offenders = [m.group(0) for m in offender_re.finditer(content)]
            assert not offenders, (
                f"{name} hardcodes personality name in string literal: {offenders}"
            )

    def test_plugins_resolve_to_per_personality_memory_dirs(
        self, project_root: Path,
    ) -> None:
        """Plugins build per-personality memory paths via
        ``join(personalitiesDir, name, "memory", ...)``."""
        MemoryInitializer().initialize(project_root)
        canonical_re = re.compile(
            r'join\([^)]*personalities[^)]*"memory"', re.DOTALL,
        )
        for name in DATA_WRITER_PLUGINS:
            content = _plugin(project_root, name)
            assert canonical_re.search(content), (
                f"{name} must build per-personality memory paths via "
                f"join(personalitiesDir, name, \"memory\", …) at runtime."
            )
