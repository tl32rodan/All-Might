"""Generic command-body invariant.

Part-D commit 3 contract: emitted command/skill bodies must not
embed the literal personality (instance) name. Bodies use the
placeholder ``personalities/<active>/<capability>/...``; the agent
resolves ``<active>`` at runtime by reading the project map at the
top of ``MEMORY.md``.

The test inits a project with a distinctive personality name and
greps every emitted body for that name. Any occurrence is a
regression — the path got baked at install time instead of being
left as a runtime placeholder.

Companion contract: the renamed on-disk capability data dir is
``database/`` (not the legacy ``knowledge_graph/``). Once Part-D
is complete, no body or filesystem path references the old name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from allmight.capabilities.database.initializer import ProjectInitializer
from allmight.capabilities.database.scanner import ProjectScanner
from allmight.capabilities.memory.initializer import MemoryInitializer


# A name distinctive enough that it cannot appear by coincidence in a
# template literal. Any leak from instance_root substitution shows up
# verbatim in the generated body.
DISTINCTIVE = "stdcell_owner_uniq_xyz"


@pytest.fixture
def initted_project(tmp_path: Path) -> Path:
    """Init a writable project rooted at ``tmp_path`` with the
    distinctive personality name."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

    instance_root = tmp_path / "personalities" / DISTINCTIVE
    scanner = ProjectScanner()
    manifest = scanner.scan(tmp_path)
    ProjectInitializer().initialize(
        manifest, instance_root=instance_root, writable=True,
    )
    MemoryInitializer().initialize(tmp_path, instance_root=instance_root)
    return tmp_path


def _iter_bodies(root: Path):
    """Yield (path, content) for every emitted .md file we own.

    Walks both ``.opencode/`` (globally-shared after this commit) and
    the per-instance dir (where bodies still land in transitional
    Part-D scaffolding) so the assertion holds regardless of which
    half the writer has been refactored already.
    """
    candidates = [root / ".opencode"]
    candidates.extend((root / "personalities").glob("*"))
    for base in candidates:
        if not base.exists():
            continue
        for sub in ("commands", "skills"):
            d = base / sub
            if not d.exists() or d.is_symlink():
                continue
            for path in d.rglob("*.md"):
                yield path, path.read_text()


class TestNoConcretePersonalityName:
    def test_bodies_do_not_embed_personality_name(self, initted_project: Path) -> None:
        """No emitted body may contain the personality (instance) name.

        The agent resolves the active personality at runtime; baking
        a name into the body defeats the routing contract.
        """
        offenders: list[tuple[str, str]] = []
        for path, body in _iter_bodies(initted_project):
            if DISTINCTIVE in body:
                rel = path.relative_to(initted_project)
                # Quote the offending lines so the failure is debuggable.
                bad_lines = [ln for ln in body.splitlines() if DISTINCTIVE in ln]
                offenders.append((str(rel), "\n".join(bad_lines)))
        assert not offenders, (
            f"Command/skill bodies leak the personality name {DISTINCTIVE!r}. "
            f"Bodies must use the `personalities/<active>/<capability>/…` "
            f"placeholder. Offenders:\n"
            + "\n".join(f"  {path}:\n    {lines}" for path, lines in offenders)
        )

    def test_bodies_reference_active_placeholder(self, initted_project: Path) -> None:
        """At least one body must teach the agent the routing pattern."""
        joined = "\n".join(body for _, body in _iter_bodies(initted_project))
        assert "<active>" in joined, (
            "Generic bodies must reference the `<active>` placeholder so "
            "the agent knows to resolve the personality from MEMORY.md."
        )


class TestDatabaseDirName:
    def test_capability_data_dir_is_database(self, initted_project: Path) -> None:
        """On-disk capability data dir is ``database/`` (Part-D),
        not the legacy ``knowledge_graph/``."""
        instance = initted_project / "personalities" / DISTINCTIVE
        assert (instance / "database").is_dir(), (
            "Database capability must materialise its data dir at "
            "personalities/<name>/database/ in Part-D."
        )
        assert not (instance / "knowledge_graph").exists(), (
            "Legacy `knowledge_graph/` directory must not be created."
        )

    def test_bodies_reference_database_not_knowledge_graph(self, initted_project: Path) -> None:
        """Bodies address the renamed dir."""
        for path, body in _iter_bodies(initted_project):
            assert "knowledge_graph/" not in body, (
                f"{path.relative_to(initted_project)} still references "
                f"the legacy 'knowledge_graph/' dir name."
            )
