"""``/onboard`` skill content (Track A rewrite).

Track A reshapes ``/onboard`` so it does NOT free-form ROLE.md.
Instead the skill:

* Asks the user a single purpose question.
* Reads the suggestion catalog at
  ``.allmight/suggestions/personalities/*.yaml`` (seeded by init).
* Shells out to ``allmight add`` for each chosen suggestion so
  ROLE.md, the marker, the capability table, and the registry row
  are written deterministically by Python.

These are content-level assertions on the constant string body —
the body is the single source of truth the agent reads at runtime.
The length cap (lines 40 in the old part-D body, 154 lines, was the
chief weak-model UX problem) is asserted as a regression guard.
"""

from __future__ import annotations

from allmight.capabilities.database.onboard_skill_content import (
    ONBOARD_COMMAND_BODY,
    ONBOARD_SKILL_BODY,
)


class TestOnboardSkillBody:
    def test_mentions_role_md(self) -> None:
        assert "ROLE.md" in ONBOARD_SKILL_BODY

    def test_mentions_memory_md_project_map(self) -> None:
        assert "MEMORY.md" in ONBOARD_SKILL_BODY
        assert "Project Map" in ONBOARD_SKILL_BODY

    def test_mentions_default_personality_callout(self) -> None:
        """The leading-callout format
        (``> **Default personality**: <name>``) is the single agreed
        routing-hint shape — body must teach it verbatim."""
        assert "**Default personality**" in ONBOARD_SKILL_BODY

    def test_shells_out_to_allmight_add(self) -> None:
        """Track A: ROLE.md is written by `allmight add`, not by the
        agent free-form. Skill body must instruct the shell-out."""
        assert "allmight add" in ONBOARD_SKILL_BODY
        assert "--capabilities" in ONBOARD_SKILL_BODY

    def test_references_suggestion_catalog(self) -> None:
        """Suggestions live at ``.allmight/suggestions/personalities/``
        (NOT ``.allmight/templates/`` — that's the /sync staging area)."""
        assert ".allmight/suggestions/personalities" in ONBOARD_SKILL_BODY

    def test_uses_part_d_capability_shape(self) -> None:
        """References to the personality data model must use
        ``capabilities`` (Part-D), never the legacy
        ``template``/``instance`` pair."""
        assert "capabilities" in ONBOARD_SKILL_BODY
        assert "template: " not in ONBOARD_SKILL_BODY
        assert "instance: " not in ONBOARD_SKILL_BODY

    def test_does_not_mention_legacy_corpus_memory_classification(self) -> None:
        """Old onboard asked the user to classify folders as corpus or
        memory. Part-D dropped that; Track A doesn't reintroduce it."""
        body = ONBOARD_SKILL_BODY
        assert "classify" not in body.lower() or "folder" not in body.lower(), (
            "onboard skill should not classify folders as corpus/memory anymore"
        )

    def test_asks_user_about_purpose(self) -> None:
        """Single open-ended question driving the catalog match."""
        body_lower = ONBOARD_SKILL_BODY.lower()
        assert "purpose" in body_lower

    def test_marks_onboarded_true(self) -> None:
        assert "onboarded: true" in ONBOARD_SKILL_BODY

    def test_skill_body_under_length_cap(self) -> None:
        """Regression guard against re-bloating. Track A target is
        ~50 lines (was 154 in the Part-D rewrite). 100 lines gives
        breathing room for inline examples without inviting the
        prose-heavy shape that confuses Kimi K2.5 / Minimax-M2.5."""
        line_count = len(ONBOARD_SKILL_BODY.splitlines())
        assert line_count < 100, (
            f"onboard skill body ballooned to {line_count} lines; "
            f"Track A target is ~50 with a 100-line cap."
        )


class TestOnboardCommandBody:
    def test_mentions_skill(self) -> None:
        """Command body should hand off to the skill for the procedure."""
        assert "onboard" in ONBOARD_COMMAND_BODY.lower()

    def test_mentions_allmight_add(self) -> None:
        """The user-facing command body should mention the underlying
        mechanic (``allmight add``) so the user understands what's
        happening even before they read the skill."""
        assert "allmight add" in ONBOARD_COMMAND_BODY
