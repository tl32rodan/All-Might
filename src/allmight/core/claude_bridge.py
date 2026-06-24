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
level (one entry, lists every personality's ROLE.md). Feedback-check
(``feedback-check.ts`` / ``feedback_check.py``, renamed from the
misleading ``reflection``) lives here for the same reason — one
prompt, fires on every user turn regardless of which personalities
are installed. Memory-load is written by the memory capability
initializer, alongside its OpenCode plugin sibling.
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


def _feedback_check_hook_content() -> str:
    """Return the feedback-check Claude Code hook script body.

    Built from the same ``FEEDBACK_CHECK_PROMPT`` text the OpenCode
    feedback-check plugin uses, so behaviour stays identical across
    editors.
    """
    # Imported lazily to avoid an import cycle: personalities imports
    # claude_bridge at the bottom of write_init_scaffold, and the
    # prompt constant lives in personalities so it can stay near the
    # plugin template that consumes it.
    from .personalities import FEEDBACK_CHECK_PROMPT
    from .plugin_telemetry import PY_HEARTBEAT_SNIPPET

    return (
        _FEEDBACK_CHECK_HOOK_TEMPLATE
        .replace(
            "__FEEDBACK_CHECK_PROMPT__",
            # Triple-quoted Python literal — escape backslashes and the
            # closing-triple-quote sequence so we don't break the string.
            FEEDBACK_CHECK_PROMPT.replace("\\", "\\\\").replace('"""', '\\"""'),
        )
        .replace("__PY_HEARTBEAT_SNIPPET__", PY_HEARTBEAT_SNIPPET)
    )


_FEEDBACK_CHECK_HOOK_TEMPLATE = '''\
#!/usr/bin/env python3
# all-might generated — DO NOT EDIT.
#
# Mirror of .opencode/plugins/feedback-check.ts. Changes here MUST land
# in the .ts plugin too; see All-Might CLAUDE.md -> Editor Compatibility.
"""Feedback-check hook for Claude Code (UserPromptSubmit).

Injects a brief instruction asking the agent to glance at the user's
latest message and, if it points out a mistake, do a 2-3 sentence
retrospective (what / why / how to avoid) before proceeding. Positive
or neutral feedback skips it. Same content the OpenCode
feedback-check plugin injects via chat.message.

NOT the periodic self-reflection surface — that is the /reflect
command.
"""
import json
import sys


FEEDBACK_CHECK_PROMPT = """__FEEDBACK_CHECK_PROMPT__"""


__PY_HEARTBEAT_SNIPPET__

def main() -> int:
    _hb("feedback_check")
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        payload = {}
    event = payload.get("hook_event_name") or "UserPromptSubmit"

    _hb("feedback_check.injected")
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": FEEDBACK_CHECK_PROMPT,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _offline_reference_hook_content() -> str:
    """Return the offline-reference Claude Code hook body.

    Built from the same ``OFFLINE_REFERENCE_NOTICE`` the OpenCode plugin
    uses (single source in ``personalities``), so both surfaces inject
    identical text.
    """
    from .personalities import OFFLINE_REFERENCE_NOTICE
    from .plugin_telemetry import PY_HEARTBEAT_SNIPPET

    return (
        _OFFLINE_REFERENCE_HOOK_TEMPLATE
        .replace(
            "__OFFLINE_REFERENCE_NOTICE__",
            OFFLINE_REFERENCE_NOTICE.replace("\\", "\\\\").replace('"""', '\\"""'),
        )
        .replace("__PY_HEARTBEAT_SNIPPET__", PY_HEARTBEAT_SNIPPET)
    )


_OFFLINE_REFERENCE_HOOK_TEMPLATE = '''\
#!/usr/bin/env python3
# all-might generated — DO NOT EDIT.
#
# Mirror of .opencode/plugins/offline-reference.ts. Changes here MUST
# land in the .ts plugin too; see All-Might CLAUDE.md -> Editor
# Compatibility.
"""Offline-reference hook for Claude Code (UserPromptSubmit).

Injects a short notice that the environment is air-gapped (no
web_search / context7) and to use the project_knowledge_search /
memory_recall MCP tools instead. Same content the OpenCode
offline-reference plugin injects via chat.message.
"""
import json
import sys


OFFLINE_REFERENCE_NOTICE = """__OFFLINE_REFERENCE_NOTICE__"""


__PY_HEARTBEAT_SNIPPET__

def main() -> int:
    _hb("offline_reference")
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        payload = {}
    event = payload.get("hook_event_name") or "UserPromptSubmit"

    _hb("offline_reference.injected")
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": OFFLINE_REFERENCE_NOTICE,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _role_load_hook_content() -> str:
    from .plugin_telemetry import PY_HEARTBEAT_SNIPPET
    return _ROLE_LOAD_HOOK_TEMPLATE.replace(
        "__PY_HEARTBEAT_SNIPPET__", PY_HEARTBEAT_SNIPPET,
    )


_ROLE_LOAD_HOOK_TEMPLATE = '''\
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


__PY_HEARTBEAT_SNIPPET__

def main() -> int:
    _hb("role_load")
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

    _hb("role_load.injected")
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


# Reload-on-context-rebuild scripts: re-prime MEMORY.md + ROLE.md
# at SessionStart and after PreCompact so the agent's context is
# never "cold" after a compaction.
_RELOAD_SCRIPTS = ("memory_load.py", "role_load.py")

# Turn-end scripts: fire after the agent stops responding. Used for
# bookkeeping that must capture each turn (memory-history snapshot).
_TURN_END_SCRIPTS = ("memory_history.py",)

# Turn-start scripts: fire when the user submits a prompt, before the
# model sees it. Used to inject per-turn instructions (feedback
# check on user friction). Claude Code analogue of OpenCode's
# chat.message hook.
_USER_PROMPT_SCRIPTS = ("feedback_check.py", "offline_reference.py")

# Union — used by tests and by the merge logic to identify our owned
# hook commands across all events.
_HOOK_SCRIPTS = _RELOAD_SCRIPTS + _TURN_END_SCRIPTS + _USER_PROMPT_SCRIPTS

# Hook scripts the bridge USED to ship under a different name. Their
# settings.json registrations are stripped on every bridge write
# (removal-only — never re-added) and a marker'd script file is
# deleted, so a rename never leaves a dangling registration behind.
# A dangling Stop/UserPromptSubmit hook is the OMO failure cascade
# CLAUDE.md warns about: missing script -> stderr fed back as the
# next user prompt.
_LEGACY_HOOK_SCRIPTS = ("reflection.py",)


def _settings_payload() -> dict:
    """Return the hook config block this bridge owns.

    Returned shape matches what ``.claude/settings.json`` expects under
    the top-level ``"hooks"`` key. ``SessionStart`` and ``PreCompact``
    re-prime memory + role context; ``Stop`` triggers the per-turn
    memory-history snapshot; ``UserPromptSubmit`` injects the
    feedback-check prompt before each user turn.
    """
    def _block(scripts: tuple[str, ...]) -> list:
        return [{"hooks": [
            {"type": "command", "command": _hook_command(name)}
            for name in scripts
        ]}]

    reload_block = _block(_RELOAD_SCRIPTS)
    return {
        "SessionStart": reload_block,
        "PreCompact": reload_block,
        "Stop": _block(_TURN_END_SCRIPTS),
        "UserPromptSubmit": _block(_USER_PROMPT_SCRIPTS),
    }


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
    # Legacy commands are removal-only: stripped from every event the
    # same way owned commands are, but never re-added.
    legacy_commands = {_hook_command(name) for name in _LEGACY_HOOK_SCRIPTS}
    drop_commands = owned_commands | legacy_commands
    for event in list(hooks_section.keys()):
        if event in owned:
            continue
        existing_blocks = hooks_section.get(event)
        if not isinstance(existing_blocks, list):
            continue
        cleaned = _strip_commands(existing_blocks, legacy_commands)
        hooks_section[event] = cleaned
    for event, blocks in owned.items():
        existing_blocks = hooks_section.get(event)
        if not isinstance(existing_blocks, list):
            hooks_section[event] = list(blocks)
            continue
        # Remove any prior all-might entries (so re-init refreshes
        # them) plus legacy-named ones (so renames don't dangle).
        cleaned = _strip_commands(existing_blocks, drop_commands)
        cleaned.extend(blocks)
        hooks_section[event] = cleaned
    return merged


def _strip_commands(blocks: list, commands: set[str]) -> list:
    """Return ``blocks`` minus any hook whose command is in ``commands``.

    Blocks that end up empty are dropped; non-dict noise is preserved
    untouched (user-authored settings shapes we don't understand).
    """
    cleaned: list = []
    for block in blocks:
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
                and h.get("command") in commands
            )
        ]
        if kept:
            new_block = dict(block)
            new_block["hooks"] = kept
            cleaned.append(new_block)
    return cleaned


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
    write_guarded(target, _role_load_hook_content(), CLAUDE_HOOK_MARKER)
    target.chmod(0o755)


def _write_feedback_check_hook(project_root: Path) -> None:
    """Write the feedback-check Claude Code hook script.

    Mirrors ``.opencode/plugins/feedback-check.ts``. The settings.json
    registration is added by ``_write_settings_json`` under
    ``UserPromptSubmit``.
    """
    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target = hooks_dir / "feedback_check.py"
    write_guarded(target, _feedback_check_hook_content(), CLAUDE_HOOK_MARKER)
    target.chmod(0o755)


def _prune_legacy_hooks(project_root: Path) -> None:
    """Delete marker'd hook scripts the bridge no longer ships.

    Only files listed in ``_LEGACY_HOOK_SCRIPTS`` AND carrying
    ``CLAUDE_HOOK_MARKER`` are removed — a user-authored script with
    the same name is preserved. Pairs with the removal-only strip in
    ``_merge_hook_config`` so neither the file nor its settings.json
    registration survives a rename.
    """
    hooks_dir = project_root / ".claude" / "hooks"
    for name in _LEGACY_HOOK_SCRIPTS:
        target = hooks_dir / name
        try:
            if target.is_file() and CLAUDE_HOOK_MARKER in target.read_text(
                encoding="utf-8", errors="replace"
            )[:4096]:
                target.unlink()
        except OSError:
            continue


def _write_offline_reference_hook(project_root: Path) -> None:
    """Write the offline-reference Claude Code hook script.

    Mirrors ``.opencode/plugins/offline-reference.ts``. The settings.json
    registration is added by ``_write_settings_json`` under
    ``UserPromptSubmit``.
    """
    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target = hooks_dir / "offline_reference.py"
    write_guarded(target, _offline_reference_hook_content(), CLAUDE_HOOK_MARKER)
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


# ---------------------------------------------------------------------------
# Knowledge MCP server wiring (project-level, both surfaces)
#
# The offline substitute for web_search / context7: a single local
# stdio server (``allmight.mcp.knowledge_server``) exposing
# project_knowledge_search + memory_recall. It is project-level scaffold
# infra (one server over every personality's database + memory), not a
# capability template — hence wired here, next to the other scaffold
# bridge writes, with no import from ``capabilities/``.
#
# Both ``opencode.json#/mcp`` and ``.mcp.json`` are NEW write targets;
# the documented exception lives in CLAUDE.md "Interface Isolation".
# Both use ``setdefault`` semantics (like opencode.json's $schema) so a
# user-customised entry survives re-init.
# ---------------------------------------------------------------------------

MCP_SERVER_NAME = "allmight-knowledge"
_MCP_SERVER_MODULE = "allmight.mcp.knowledge_server"


def opencode_mcp_entry() -> dict:
    """The OpenCode ``mcp.<name>`` local-server entry (single source)."""
    return {
        "type": "local",
        "command": ["python", "-m", _MCP_SERVER_MODULE],
        "enabled": True,
    }


def claude_mcp_entry() -> dict:
    """The Claude Code ``mcpServers.<name>`` stdio entry (single source)."""
    return {
        "type": "stdio",
        "command": "python",
        "args": ["-m", _MCP_SERVER_MODULE],
    }


def _write_claude_mcp_json(project_root: Path) -> None:
    """Merge our knowledge server into ``.mcp.json`` (setdefault)."""
    path = project_root / ".mcp.json"
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        data = {}
    servers = data.setdefault("mcpServers", {})
    servers.setdefault(MCP_SERVER_NAME, claude_mcp_entry())
    path.write_text(json.dumps(data, indent=2) + "\n")


def write_claude_bridge(project_root: Path) -> None:
    """Project-level Claude Code bridge — call once per ``allmight init``.

    Writes everything that does not belong to a specific capability:

    * ``CLAUDE.md`` (root) ``@``-import shim
    * ``.claude/commands`` and ``.claude/skills`` directory symlinks
    * ``.claude/hooks/role_load.py`` (mirrors role-load.ts)
    * ``.claude/hooks/feedback_check.py`` (mirrors feedback-check.ts)
    * ``.claude/settings.json`` hook registrations for both
      ``role_load.py`` and the memory capability's ``memory_load.py``,
      plus ``feedback_check.py`` under ``UserPromptSubmit``
    * ``.mcp.json`` registration of the knowledge MCP server

    Legacy-named hooks (``_LEGACY_HOOK_SCRIPTS``) are pruned: the
    marker'd script file is deleted and its settings.json entry is
    stripped, so renames never leave a dangling registration.

    The memory-load hook script itself is written by
    ``MemoryInitializer`` since its content is a Python rewrite of
    that capability's ``memory-load.ts`` plugin.
    """
    _write_root_claude_md(project_root)
    _write_claude_dir_symlinks(project_root)
    _write_role_load_hook(project_root)
    _write_feedback_check_hook(project_root)
    _write_offline_reference_hook(project_root)
    _prune_legacy_hooks(project_root)
    _write_settings_json(project_root)
    _write_claude_mcp_json(project_root)
