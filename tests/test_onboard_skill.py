"""``/onboard`` skill content (Part-D rewrite).

Commit 8 reshapes the bundled ``/onboard`` skill so it classifies
*personalities* (not folders) and writes ``personalities/<p>/ROLE.md``
plus the project-map + default-personality callout in ``MEMORY.md``.

These are content-level assertions on the constant string body —
the body is the single source of truth the agent reads at runtime.
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
        (``> **Default personality**: <name>``) is the
        single agreed routing-hint shape — body must teach it."""
        assert "**Default personality**" in ONBOARD_SKILL_BODY

    def test_uses_part_d_onboard_yaml_shape(self) -> None:
        """The example yaml block must use ``name`` + ``capabilities``,
        not the legacy ``template`` + ``instance`` pair."""
        assert "name:" in ONBOARD_SKILL_BODY
        assert "capabilities:" in ONBOARD_SKILL_BODY
        assert "template: " not in ONBOARD_SKILL_BODY
        assert "instance: " not in ONBOARD_SKILL_BODY

    def test_does_not_mention_legacy_corpus_memory_classification(self) -> None:
        """Old onboard asked the user to classify folders as corpus or
        memory. Part-D drops that — folder semantics live in
        ``MEMORY.md``'s project map per personality."""
        body = ONBOARD_SKILL_BODY
        # No phrasing about classifying folders into corpus/memory buckets.
        assert "classify" not in body.lower() or "folder" not in body.lower(), (
            "onboard skill should not classify folders as corpus/memory anymore"
        )

    def test_asks_user_about_role(self) -> None:
        """Body must instruct the agent to ask the user about the
        personality's role."""
        body_lower = ONBOARD_SKILL_BODY.lower()
        assert "role" in body_lower

    def test_marks_onboarded_true(self) -> None:
        assert "onboarded: true" in ONBOARD_SKILL_BODY


class TestOnboardCommandBody:
    def test_mentions_skill(self) -> None:
        """Command body should hand off to the skill for the procedure."""
        assert "onboard" in ONBOARD_COMMAND_BODY.lower()
