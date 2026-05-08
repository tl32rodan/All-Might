"""Shared helpers for installing OpenCode skills + their command files.

A skill installation in All-Might has a fixed shape:

* ``.opencode/skills/<name>/SKILL.md`` — frontmatter (``name``,
  ``description``) + the All-Might marker + the body. OpenCode reads
  the frontmatter for skill discovery; the marker tags the file as
  ours so re-init can refresh it without clobbering user edits.
* ``.opencode/commands/<name>.md`` — the slash-command body. Optional;
  capabilities that batch-write their command files (e.g. memory's
  ``remember``/``recall``/``recover``) skip this side.

These helpers exist so capability initializers don't repeat the
write_guarded + frontmatter assembly four times each.
"""

from __future__ import annotations

from pathlib import Path

from .markers import ALLMIGHT_MARKER_MD
from .safe_write import write_guarded


def write_skill_md(
    path: Path,
    *,
    name: str,
    description: str,
    body: str,
    disable_model_invocation: bool = False,
) -> None:
    """Write a ``SKILL.md`` with YAML frontmatter + All-Might marker + body."""
    frontmatter_lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
    ]
    if disable_model_invocation:
        frontmatter_lines.append("disable-model-invocation: true")
    frontmatter_lines.append("---")

    content = (
        "\n".join(frontmatter_lines)
        + "\n\n"
        + ALLMIGHT_MARKER_MD
        + "\n\n"
        + body
    )
    write_guarded(path, content, ALLMIGHT_MARKER_MD)


def install_skill(
    root: Path,
    *,
    name: str,
    description: str,
    skill_body: str,
    command_body: str | None = None,
    force: bool = False,
    disable_model_invocation: bool = False,
) -> None:
    """Install one project-wide skill (and optionally its command file).

    Writes ``.opencode/skills/<name>/SKILL.md``. If ``command_body`` is
    provided, also writes ``.opencode/commands/<name>.md``. Both writes
    go through ``write_guarded`` and carry ``ALLMIGHT_MARKER_MD``.
    """
    skills_dir = root / ".opencode" / "skills" / name
    skills_dir.mkdir(parents=True, exist_ok=True)
    write_skill_md(
        skills_dir / "SKILL.md",
        name=name,
        description=description,
        body=skill_body,
        disable_model_invocation=disable_model_invocation,
    )

    if command_body is not None:
        commands_dir = root / ".opencode" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        write_guarded(
            commands_dir / f"{name}.md",
            command_body,
            ALLMIGHT_MARKER_MD,
            force=force,
        )
