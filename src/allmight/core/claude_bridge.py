"""Claude Code compatibility bridge.

OpenCode is the canonical agent surface — All-Might emits
``.opencode/{commands,skills,plugins}/`` from each capability template.
This module mirrors what is mirrorable into ``.claude/`` so Claude
Code consumes the same project without forking the source of truth:

* **Markdown surface** — ``.claude/commands`` and ``.claude/skills``
  become directory-level symlinks into ``.opencode/``. New
  commands/skills written by capability templates show up on both
  sides without re-running anything.

* **Agent context** — root ``CLAUDE.md`` ``@``-imports the same
  ``AGENTS.md`` and ``MEMORY.md`` that OpenCode reads directly.
  Editing those root files updates both editors immediately.

* **Runtime hooks** — OpenCode ``.opencode/plugins/*.ts`` are not
  portable to Claude Code; their behavior is mirrored as
  ``.claude/hooks/*.py`` shell-callable scripts and registered in
  ``.claude/settings.json``. Each hook's content is a Python rewrite
  of the corresponding TS plugin; **changes to one require changes
  to the other** (see All-Might ``CLAUDE.md`` -> Editor
  Compatibility).

The role-load hook lives here because role-load.ts is also project-
level (one entry, lists every personality's ROLE.md). Memory-load is
written by the memory capability initializer, alongside its OpenCode
plugin sibling.
"""

from __future__ import annotations

import json
from pathlib import Path

from .safe_write import write_guarded


CLAUDE_HOOK_MARKER = "# all-might generated"


_CLAUDE_MD_MARKER = "<!-- all-might generated -->"

_CLAUDE_MD_CONTENT = (
    f"{_CLAUDE_MD_MARKER}\n"
    "<!--\n"
    "  Claude Code reads this file. OpenCode reads AGENTS.md directly.\n"
    "  Both surfaces stay in sync because this file just @-imports the\n"
    "  same root files OpenCode already loads.\n"
    "-->\n"
    "@AGENTS.md\n"
    "@MEMORY.md\n"
)


_ROLE_LOAD_HOOK_CONTENT = '''\
#!/usr/bin/env python3
# all-might generated — DO NOT EDIT.
#
# Mirror of .opencode/plugins/role-load.ts. Changes here MUST land in
# the .ts plugin too; see All-Might CLAUDE.md -> Editor Compatibility.
"""Role-load hook for Claude Code (SessionStart, PreCompact).

Reads every ``personalities/*/ROLE.md`` and emits the concatenated
content as ``additionalContext`` so the agent has each role primed
before the first user turn — same role-stability guarantee the
OpenCode role-load plugin gives via ``chat.message`` injection.
"""
import json
import os
import sys
from pathlib import Path


def main() -> int:
    cwd = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    parts: list[str] = []
    personalities_dir = cwd / "personalities"
    if personalities_dir.is_dir():
        for entry in sorted(personalities_dir.iterdir()):
            role = entry / "ROLE.md"
            if not role.is_file():
                continue
            try:
                body = role.read_text(encoding="utf-8")
            except OSError:
                continue
            parts.append(f"--- Role: {entry.name} (ROLE.md) ---")
            parts.append(body.rstrip())
            parts.append(f"--- End Role: {entry.name} ---")
            parts.append("")
    text = "\\n".join(parts).strip()
    if not text:
        return 0

    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        payload = {}
    event = payload.get("hook_event_name") or "SessionStart"

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": text,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _hook_command(script_basename: str) -> str:
    """Shell command for settings.json that runs ``script_basename``."""
    return f"python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/{script_basename}"


_HOOK_SCRIPTS = ("memory_load.py", "role_load.py")


def _settings_payload() -> dict:
    """Return the hook config block this bridge owns.

    Returned shape matches what ``.claude/settings.json`` expects under
    the top-level ``"hooks"`` key. Both ``SessionStart`` and
    ``PreCompact`` register both scripts so memory and role context are
    re-primed when conversation history is summarised.
    """
    hook_entries = [
        {"type": "command", "command": _hook_command(name)}
        for name in _HOOK_SCRIPTS
    ]
    block = [{"hooks": hook_entries}]
    return {"SessionStart": block, "PreCompact": block}


def _merge_hook_config(existing: dict, owned: dict) -> dict:
    """Add owned hook entries to ``existing`` settings, preserving user hooks.

    User hooks for the same event stay untouched; we only ensure our
    own commands appear exactly once. Re-running ``init`` is therefore
    idempotent even after the user has hand-edited
    ``.claude/settings.json``.
    """
    merged = dict(existing) if isinstance(existing, dict) else {}
    hooks_section = merged.setdefault("hooks", {})
    if not isinstance(hooks_section, dict):
        hooks_section = {}
        merged["hooks"] = hooks_section
    owned_commands = {
        h["command"]
        for block in owned.values()
        for h in block[0]["hooks"]
    }
    for event, blocks in owned.items():
        existing_blocks = hooks_section.get(event)
        if not isinstance(existing_blocks, list):
            hooks_section[event] = list(blocks)
            continue
        # Remove any prior all-might entries (so re-init refreshes them)
        cleaned: list = []
        for block in existing_blocks:
            if not isinstance(block, dict):
                cleaned.append(block)
                continue
            inner = block.get("hooks")
            if not isinstance(inner, list):
                cleaned.append(block)
                continue
            kept = [
                h for h in inner
                if not (
                    isinstance(h, dict)
                    and h.get("command") in owned_commands
                )
            ]
            if kept:
                new_block = dict(block)
                new_block["hooks"] = kept
                cleaned.append(new_block)
        cleaned.extend(blocks)
        hooks_section[event] = cleaned
    return merged


def _write_root_claude_md(project_root: Path) -> None:
    """Write root CLAUDE.md if absent or All-Might-owned.

    The file is the agent context entry-point Claude Code loads
    automatically; OpenCode reads ``AGENTS.md`` directly. Keeping
    CLAUDE.md as a thin ``@``-import shim means a single edit to
    ``AGENTS.md`` or ``MEMORY.md`` updates both editors with no
    duplication. ``write_guarded`` preserves any user-authored
    CLAUDE.md without our marker.
    """
    write_guarded(project_root / "CLAUDE.md", _CLAUDE_MD_CONTENT, _CLAUDE_MD_MARKER)


def _write_claude_dir_symlinks(project_root: Path) -> None:
    """Project ``.opencode/{commands,skills}`` into ``.claude/`` via dir symlinks.

    Directory-level (not per-file) so any later command/skill written
    by a capability template appears on the Claude Code side without
    re-running anything. Idempotent — already-correct symlinks are
    left alone, and an existing non-symlink path is preserved (the
    user wrote it, we don't touch).
    """
    claude_dir = project_root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    for kind in ("commands", "skills"):
        link = claude_dir / kind
        target = Path("..") / ".opencode" / kind
        if link.is_symlink():
            if link.readlink() == target:
                continue
            link.unlink()
        elif link.exists():
            # User-authored; leave alone.
            continue
        link.symlink_to(target)


def _write_role_load_hook(project_root: Path) -> None:
    """Write the role-load Claude Code hook script."""
    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target = hooks_dir / "role_load.py"
    write_guarded(target, _ROLE_LOAD_HOOK_CONTENT, CLAUDE_HOOK_MARKER)
    target.chmod(0o755)


def _write_settings_json(project_root: Path) -> None:
    """Merge our hook registrations into ``.claude/settings.json``.

    Existing user-authored settings (model, env, permissions, ...)
    are preserved. Existing user-authored hooks under SessionStart /
    PreCompact are also preserved; only our own command lines are
    refreshed.
    """
    settings_path = project_root / ".claude" / "settings.json"
    settings_path.parent.mkdir(exist_ok=True)
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    else:
        existing = {}
    merged = _merge_hook_config(existing, _settings_payload())
    settings_path.write_text(json.dumps(merged, indent=2) + "\n")


def write_claude_bridge(project_root: Path) -> None:
    """Project-level Claude Code bridge — call once per ``allmight init``.

    Writes everything that does not belong to a specific capability:

    * ``CLAUDE.md`` (root) ``@``-import shim
    * ``.claude/commands`` and ``.claude/skills`` directory symlinks
    * ``.claude/hooks/role_load.py`` (mirrors role-load.ts)
    * ``.claude/settings.json`` hook registrations for both
      ``role_load.py`` and the memory capability's ``memory_load.py``

    The memory-load hook script itself is written by
    ``MemoryInitializer`` since its content is a Python rewrite of
    that capability's ``memory-load.ts`` plugin.
    """
    _write_root_claude_md(project_root)
    _write_claude_dir_symlinks(project_root)
    _write_role_load_hook(project_root)
    _write_settings_json(project_root)
