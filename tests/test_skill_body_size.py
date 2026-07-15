"""Skill / command body size ratchet.

Each entry caps a generated body at its current size in lines.
Adding lines is a regression — trim or split first. When you
intentionally cut a body, **drop the cap accordingly** so the
ratchet keeps moving in one direction.

See ``CLAUDE.md`` § *Skill / Command Body Style Guide* for the
hard rules these caps enforce.
"""
from __future__ import annotations

import pytest

from allmight.capabilities.database.all_for_one_skill_content import (
    ALL_FOR_ONE_SKILL_BODY,
)
from allmight.capabilities.database.one_for_all_skill_content import (
    ONE_FOR_ALL_SKILL_BODY,
)
from allmight.capabilities.database.onboard_skill_content import (
    ONBOARD_SKILL_BODY,
)
from allmight.capabilities.database.link_skill_content import (
    build_link_skill_md,
)
from allmight.capabilities.database.sync_skill_content import SYNC_SKILL_BODY
from allmight.capabilities.memory.initializer import MemoryInitializer
from allmight.core.whip_it import (
    build_whip_it_command_body,
    build_whip_it_skill_body,
)


def _remember_body() -> str:
    return MemoryInitializer()._remember_command_body()


def _reflect_body() -> str:
    return MemoryInitializer()._reflect_command_body()


def _recall_body() -> str:
    return MemoryInitializer()._recall_command_body()


# (label, body_getter, max_lines)
# Caps reflect the current line count at the time of writing — the
# ratchet only moves downward. After a trim, lower the cap in the
# same PR so future regressions get caught.
BODY_BUDGETS: list[tuple[str, callable, int]] = [
    ("/remember (command)", _remember_body, 109),
    ("/reflect (command)", _reflect_body, 104),
    ("/recall (command)", _recall_body, 118),
    ("/onboard (skill)", lambda: ONBOARD_SKILL_BODY, 70),
    ("/link (skill)", build_link_skill_md, 37),
    ("/sync (skill)", lambda: SYNC_SKILL_BODY, 227),
    ("/one-for-all (skill)", lambda: ONE_FOR_ALL_SKILL_BODY, 174),
    ("/all-for-one (skill)", lambda: ALL_FOR_ONE_SKILL_BODY, 226),
    ("/whip-it (skill)", build_whip_it_skill_body, 109),
    ("/whip-it (command)", build_whip_it_command_body, 29),
]


@pytest.mark.parametrize("label,body_fn,max_lines", BODY_BUDGETS)
def test_skill_body_within_budget(label: str, body_fn, max_lines: int) -> None:
    body = body_fn()
    lines = len(body.splitlines())
    assert lines <= max_lines, (
        f"{label} grew to {lines} lines (cap {max_lines}). "
        f"Trim it or split it before raising the cap — see "
        f"CLAUDE.md § Skill / Command Body Style Guide."
    )
