"""Tests for the shared context-injection budget.

Claude Code caps hook output — plain stdout, ``additionalContext`` and
``systemMessage`` alike — at 10,000 characters, and truncates past it
*silently*. ``role_load`` concatenates every personality's full
ROLE.md, so a multi-personality project cleared the cap and lost the
alphabetically-last roles with no error anywhere.

The fix degrades to a read-on-demand role index rather than cutting
mid-sentence, and applies the same budget to the OpenCode surface so
the two editors cannot disagree about which roles exist.

The old string-presence tests could not catch this: truncation
preserves the strings they assert on. These tests measure length and
role coverage instead.

See docs/compaction-reprime-proposal.md.
"""

import os
import subprocess
import sys

import pytest

from allmight.capabilities.memory.initializer import MemoryInitializer
from allmight.core import personalities as personalities_mod
from allmight.core.claude_bridge import _role_load_hook_content
from allmight.core.plugin_telemetry import HOOK_OUTPUT_BUDGET


def _write_hook(tmp_path):
    hook = tmp_path / "role_load.py"
    hook.write_text(_role_load_hook_content())
    return hook


def _make_project(tmp_path, count, filler_lines, name="proj"):
    root = tmp_path / name
    for i in range(count):
        role_dir = root / "personalities" / f"role{i:03d}_owner"
        role_dir.mkdir(parents=True)
        (role_dir / "ROLE.md").write_text(
            f"# role{i:03d}_owner\n\n"
            f"Owns the role{i:03d} flow end to end.\n"
            + ("filler line\n" * filler_lines)
        )
    return root


def _run(hook, root):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    result = subprocess.run(
        [sys.executable, str(hook)],
        input="", capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert not result.stderr, result.stderr
    return result.stdout


class TestRoleLoadBudget:
    """role_load must never exceed the budget, at any project size."""

    @pytest.mark.parametrize(
        "count,filler",
        [(1, 2), (3, 5), (3, 400), (12, 200), (200, 5)],
    )
    def test_never_exceeds_budget(self, tmp_path, count, filler):
        hook = _write_hook(tmp_path)
        root = _make_project(tmp_path, count, filler, name=f"p{count}_{filler}")
        out = _run(hook, root)
        assert len(out) <= HOOK_OUTPUT_BUDGET, (
            f"{count} roles x {filler} filler lines produced {len(out)} "
            f"chars, over the {HOOK_OUTPUT_BUDGET} budget"
        )

    def test_full_bodies_kept_when_they_fit(self, tmp_path):
        """No regression for the common case: small projects are verbatim."""
        hook = _write_hook(tmp_path)
        root = _make_project(tmp_path, 2, 3)
        out = _run(hook, root)
        assert "--- Role: role000_owner (ROLE.md) ---" in out
        assert "Owns the role000 flow end to end." in out
        assert "--- End Role: role001_owner ---" in out

    def test_degrades_to_index_not_truncation(self, tmp_path):
        """Over budget: an index, not a mid-sentence cut."""
        hook = _write_hook(tmp_path)
        root = _make_project(tmp_path, 8, 400)
        out = _run(hook, root)
        assert "Role bodies were omitted" in out
        # The index points at the file rather than inlining it.
        assert "personalities/role000_owner/ROLE.md" in out
        assert "filler line" not in out

    def test_index_lists_every_role(self, tmp_path):
        """The whole point: no role silently disappears.

        Blind truncation dropped the alphabetically-last roles. The
        index keeps every one discoverable.
        """
        hook = _write_hook(tmp_path)
        root = _make_project(tmp_path, 12, 300)
        out = _run(hook, root)
        for i in range(12):
            assert f"role{i:03d}_owner" in out, (
                f"role{i:03d}_owner vanished from the index"
            )

    def test_states_omission_when_even_index_overflows(self, tmp_path):
        """At pathological scale the drop is stated, never silent."""
        hook = _write_hook(tmp_path)
        root = _make_project(tmp_path, 400, 2)
        out = _run(hook, root)
        assert len(out) <= HOOK_OUTPUT_BUDGET
        assert "further role(s) not listed" in out
        # And the count is a real number, not the placeholder.
        assert "__N__" not in out

    def test_summary_prefers_prose_over_heading(self, tmp_path):
        """A leading `# <name>` just repeats the name we already print."""
        hook = _write_hook(tmp_path)
        root = _make_project(tmp_path, 10, 400)
        out = _run(hook, root)
        assert "Owns the role000 flow end to end." in out

    def test_silent_when_no_personalities(self, tmp_path):
        hook = _write_hook(tmp_path)
        root = tmp_path / "empty"
        root.mkdir()
        assert _run(hook, root) == ""


class TestBudgetSharedAcrossSurfaces:
    """Both surfaces must degrade identically.

    A role visible in one editor and absent in the other is exactly the
    "behaviour depends on which editor I open the project with" drift
    the dual-platform invariant exists to prevent — so the budget is
    shared even though OpenCode has no documented cap of its own.
    """

    def test_budget_constant_in_all_four_generators(self):
        mi = MemoryInitializer()
        generated = {
            "role_load.py": _role_load_hook_content(),
            "memory_load.py": mi._claude_memory_load_hook_content(),
            "role-load.ts": personalities_mod._role_load_plugin_content(),
            "memory-load.ts": mi._opencode_plugin_content(),
        }
        for name, content in generated.items():
            assert str(HOOK_OUTPUT_BUDGET) in content, (
                f"{name} does not carry the shared budget constant"
            )

    def test_index_notice_text_identical_on_both_surfaces(self):
        """Single-generator rule: one Python source for the user-visible string."""
        from allmight.core.plugin_telemetry import ROLE_INDEX_NOTICE

        py = _role_load_hook_content()
        ts = personalities_mod._role_load_plugin_content()
        assert ROLE_INDEX_NOTICE in py
        assert ROLE_INDEX_NOTICE in ts

    def test_truncation_notice_identical_on_both_surfaces(self):
        from allmight.core.plugin_telemetry import DOC_TRUNCATED_NOTICE

        mi = MemoryInitializer()
        assert DOC_TRUNCATED_NOTICE in mi._claude_memory_load_hook_content()
        assert DOC_TRUNCATED_NOTICE in mi._opencode_plugin_content()

    def test_ts_surface_has_the_index_fallback_too(self):
        ts = personalities_mod._role_load_plugin_content()
        assert "function buildIndex" in ts
        assert "fitBudget" in ts


class TestMemoryLoadBudget:
    """MEMORY.md is trimmed; the scope principle that follows is not."""

    def test_scope_principle_survives_a_huge_memory_md(self, tmp_path):
        hook = tmp_path / "memory_load.py"
        hook.write_text(
            MemoryInitializer()._claude_memory_load_hook_content()
        )
        root = tmp_path / "proj"
        root.mkdir()
        (root / "MEMORY.md").write_text("# Memory\n\n" + ("fact line\n" * 4000))

        out = _run(hook, root)
        assert len(out) <= HOOK_OUTPUT_BUDGET
        # The tail is short, always relevant, and must never be the
        # thing that gets cut.
        assert "Memory Scope-First Principle" in out
        assert "truncated to fit" in out
