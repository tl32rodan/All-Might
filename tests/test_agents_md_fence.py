"""Unit tests for the AGENTS.md fence primitives.

``compose_agents_md`` is exercised end-to-end elsewhere
(``test_init_is_additive.py``, ``test_compose_command.py``). These
tests pin :func:`allmight.core.agents_md.splice` itself — the pure
merge function — including the shapes that only show up on
hand-mangled files.
"""

from __future__ import annotations

import pytest

from allmight.core.agents_md import (
    FENCE_BEGIN,
    FENCE_END,
    FENCE_OPT_OUT,
    fence_bounds,
    removes_content,
    render_fenced,
    splice,
)

BODY = "<!-- all-might generated -->\n# demo\n\n## About All-Might\nprimer\n"


def _interior(text: str) -> str:
    start = text.index(FENCE_BEGIN) + len(FENCE_BEGIN)
    return text[start:text.rindex(FENCE_END)].strip()


class TestSpliceActions:

    def test_no_file_creates_fenced_block(self):
        text, action = splice(None, BODY)
        assert action == "created"
        assert text == render_fenced(BODY)
        assert text.endswith("\n")

    def test_user_file_gets_block_appended(self):
        user = "# mine\nkeep me\n"
        text, action = splice(user, BODY)
        assert action == "appended"
        assert text.startswith(user)
        assert _interior(text) == BODY.strip()

    def test_second_pass_replaces_only_the_interior(self):
        user_before = "# top\n\n"
        user_after = "\n\n# bottom\n"
        first, _ = splice(user_before.rstrip("\n"), BODY)
        existing = first.rstrip("\n") + user_after
        text, action = splice(existing, "NEW BODY")
        assert action == "replaced"
        assert text.startswith(user_before.rstrip("\n"))
        assert text.endswith(user_after)
        assert _interior(text) == "NEW BODY"
        assert text.count(FENCE_BEGIN) == 1

    def test_identical_recompose_is_unchanged(self):
        first, _ = splice(None, BODY)
        text, action = splice(first, BODY)
        assert action == "unchanged"
        assert text == first

    def test_dangling_opener_is_repaired_not_duplicated(self):
        """Hand-deleted END marker: our region ran to EOF, so replace it."""
        mangled = f"# mine\n\n{FENCE_BEGIN}\nhalf-deleted junk\n"
        text, action = splice(mangled, BODY)
        assert action == "replaced"
        assert text.count(FENCE_BEGIN) == 1
        assert text.count(FENCE_END) == 1
        assert "half-deleted junk" not in text
        assert text.startswith("# mine")

    def test_duplicate_fences_collapse_to_one(self):
        doubled = (
            f"{FENCE_BEGIN}\nold one\n{FENCE_END}\n"
            f"\n{FENCE_BEGIN}\nold two\n{FENCE_END}\n"
        )
        text, action = splice(doubled, BODY)
        assert action == "replaced"
        assert text.count(FENCE_BEGIN) == 1
        assert "old one" not in text and "old two" not in text

    def test_unfenced_prior_composition_migrates_in_place(self):
        existing = f"{BODY}\n## my notes\nkeep\n"
        text, action = splice(existing, BODY)
        assert action == "migrated"
        assert "## my notes" in text
        assert text.count(FENCE_BEGIN) == 1
        assert _interior(text) == BODY.strip()

    def test_pre_part_c_legacy_section_is_cut_and_reported(self):
        existing = "# my heading\n\n<!-- ALL-MIGHT -->\nlegacy body\n"
        text, action = splice(existing, BODY)
        assert action == "legacy-cut"
        assert removes_content(action), "caller must back this up"
        assert text.startswith("# my heading")
        assert "legacy body" not in text
        assert FENCE_BEGIN in text

    @pytest.mark.parametrize(
        "existing",
        [
            f"{FENCE_OPT_OUT}\n# mine\n",
            f"# mine\n\n{FENCE_OPT_OUT}\n",
        ],
    )
    def test_opt_out_anywhere_outside_the_fence_wins(self, existing):
        text, action = splice(existing, BODY)
        assert action == "opted-out"
        assert text == existing

    def test_opt_out_inside_our_own_block_is_ignored(self):
        """Our block documents the opt-out; that must not freeze it.

        A literal opt-out token in the generated header made every
        later recompose a no-op — the file stayed on the first
        composition forever.
        """
        body_that_explains = BODY + f"\nto disable, add {FENCE_OPT_OUT}\n"
        first, _ = splice(None, body_that_explains)
        text, action = splice(first, "NEW BODY")
        assert action == "replaced"
        assert _interior(text) == "NEW BODY"

    def test_force_overrides_opt_out(self):
        text, action = splice(f"{FENCE_OPT_OUT}\nmine\n", BODY, force=True)
        assert action == "forced"
        assert removes_content(action)
        assert text == render_fenced(BODY)

    def test_force_still_preserves_content_around_a_fence(self):
        """``--force`` overwrites *our share*, which is the fence."""
        existing = f"# top\n\n{FENCE_BEGIN}\nold\n{FENCE_END}\n\n# bottom\n"
        text, action = splice(existing, BODY, force=True)
        assert action == "replaced"
        assert text.startswith("# top")
        assert text.rstrip().endswith("# bottom")

    def test_empty_file_is_treated_as_no_content(self):
        text, action = splice("", BODY)
        assert action == "appended"
        assert text == render_fenced(BODY)

    def test_result_always_ends_with_a_newline(self):
        for existing in (None, "", "# mine", f"{FENCE_BEGIN}\nx\n{FENCE_END}"):
            text, _ = splice(existing, BODY)
            assert text.endswith("\n"), repr(existing)


class TestFenceBounds:

    def test_none_without_fence(self):
        assert fence_bounds("# plain\n") is None

    def test_bounds_cover_markers_inclusively(self):
        text = f"a\n{FENCE_BEGIN}\nb\n{FENCE_END}\nc\n"
        start, end = fence_bounds(text)
        assert text[start:end].startswith(FENCE_BEGIN)
        assert text[start:end].endswith(FENCE_END)

    def test_dangling_opener_runs_to_eof(self):
        text = f"a\n{FENCE_BEGIN}\nb\n"
        start, end = fence_bounds(text)
        assert end == len(text)
