"""Routing-contract preamble in generated command bodies.

Part-D commit 9: every command body that addresses a personality's
data dir (``database/`` or ``memory/``) starts with a routing
preamble teaching the agent how to resolve ``<active>`` —

  1. Explicit mention by the user
  2. Conversation context
  3. Default-personality callout at the top of ``MEMORY.md``:
     ``> **Default personality**: <name>``

The preamble is the contract the runtime agent depends on; every
``personalities/<active>/<capability>/...`` reference downstream is
meaningless without it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from allmight.cli import main


@pytest.fixture
def initted_project(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("def f(): pass\n")
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--writable", "--yes", str(project)])
    assert result.exit_code == 0, result.output
    return project


# Commands that read or write personality data and therefore need the
# routing preamble. ``onboard.md`` is omitted — it operates on the
# ``onboard.yaml`` itself, not on a single active personality's data.
ROUTED_COMMANDS = ("search.md", "enrich.md", "ingest.md", "remember.md", "recall.md")


def _command_body(project: Path, name: str) -> str:
    p = project / ".opencode" / "commands" / name
    assert p.exists(), f"missing generated command {name}"
    return p.read_text()


class TestRoutingPreamblePresence:
    def test_each_routed_command_has_routing_section(self, initted_project: Path) -> None:
        for name in ROUTED_COMMANDS:
            body = _command_body(initted_project, name)
            assert "## Routing" in body or "Routing — pick the active" in body, (
                f"{name} must start with a routing-contract preamble; "
                "the agent has nothing to substitute for <active> without it."
            )

    def test_each_body_references_memory_md_default_callout(
        self, initted_project: Path,
    ) -> None:
        for name in ROUTED_COMMANDS:
            body = _command_body(initted_project, name)
            assert "MEMORY.md" in body, f"{name} must reference MEMORY.md"
            assert "Default personality" in body, (
                f"{name} must teach the agent the leading-callout format"
            )

    def test_each_body_keeps_active_placeholder(self, initted_project: Path) -> None:
        """The placeholder ``<active>`` is what the agent substitutes
        once routing is resolved — so it must be there."""
        for name in ROUTED_COMMANDS:
            body = _command_body(initted_project, name)
            assert "<active>" in body, (
                f"{name} must use the <active> placeholder in paths"
            )

    def test_routing_preamble_lists_three_resolution_steps(
        self, initted_project: Path,
    ) -> None:
        """Body teaches: explicit mention -> context -> default."""
        for name in ROUTED_COMMANDS:
            body = _command_body(initted_project, name).lower()
            assert "explicit" in body, (
                f"{name} must mention 'explicit' as the first routing step"
            )
            assert "default" in body, (
                f"{name} must mention 'default' as the fallback"
            )
