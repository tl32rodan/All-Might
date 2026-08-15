"""Touch-file heartbeats for All-Might plugins.

This module is the source of truth for the simplest-possible plugin
observability: each plugin / Claude hook touches a marker file when
it fires, and ``allmight plugin status`` reads the marker mtimes.

The Python helpers are used by:
  * the CLI (``allmight plugin status``) — reads ``heartbeats/`` and
    pretty-prints "fired N ago" lines;
  * tests — assert that a plugin or hook wrote a heartbeat.

The string snippets (`TS_HEARTBEAT_SNIPPET`, `PY_HEARTBEAT_SNIPPET`)
are inlined verbatim into generated TS plugins and Python hooks. They
are intentionally short and self-contained so each plugin keeps its
own copy — no cross-plugin module import, no shared runtime.

See ``docs/plugin-observability.md`` for the design rationale.
"""

from __future__ import annotations

import os
from pathlib import Path


SURFACE_OPENCODE = "oc"
SURFACE_CLAUDE = "cc"


def heartbeats_root(project_root: Path) -> Path:
    """Return the heartbeats directory for ``project_root``."""
    return project_root / ".allmight" / "plugins" / "heartbeats"


def emit_heartbeat(
    name: str,
    surface: str = SURFACE_CLAUDE,
    root: Path | None = None,
) -> None:
    """Touch ``heartbeats/<surface>/<name>``. Used by tests + helpers.

    Errors are swallowed: a heartbeat write failure must never break
    the caller. The CLI will simply show "never fired" for the plugin.
    """
    try:
        base = root or Path(
            os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        )
        d = heartbeats_root(base) / surface
        d.mkdir(parents=True, exist_ok=True)
        (d / name).touch()
    except Exception:
        pass


def prune_stale_plugins(project_root: Path) -> list[Path]:
    """Retire All-Might-generated plugins that are no longer shipped.

    Sweeps ``.opencode/plugins/*.ts`` and the re-init staging dir
    ``.allmight/templates/*.ts``. A file is retired only when BOTH hold:

    * its basename is not ``<name>.ts`` for any name in
      ``KNOWN_OPENCODE_PLUGINS`` (i.e. the framework stopped shipping
      it — deleted or renamed), and
    * its head carries ``ALLMIGHT_MARKER_TS`` (we wrote it; a
      user-authored plugin without the marker is never touched).

    Retired files are **moved to ``.allmight/attic/``**, not deleted —
    the marker only proves All-Might wrote the file once. Copying one of
    our plugins as a template for your own copies the marker too, and
    that fork used to vanish on the next ``allmight init`` with no way
    back. See :mod:`allmight.core.attic`.

    Returns the *original* paths so ``allmight init`` can report them.
    Errors are swallowed per-file — a prune failure must never break
    init.
    """
    from .attic import quarantine
    from .markers import ALLMIGHT_MARKER_TS

    current = {f"{name}.ts" for name in KNOWN_OPENCODE_PLUGINS}
    pruned: list[Path] = []
    sweep_dirs = (
        project_root / ".opencode" / "plugins",
        project_root / ".allmight" / "templates",
    )
    for d in sweep_dirs:
        if not d.is_dir():
            continue
        for entry in sorted(d.glob("*.ts")):
            if entry.name in current:
                continue
            try:
                head = entry.read_text(encoding="utf-8", errors="replace")[:4096]
            except OSError:
                continue
            if ALLMIGHT_MARKER_TS not in head:
                continue
            if quarantine(project_root, entry) is not None:
                pruned.append(entry)
    return pruned


def read_heartbeats(project_root: Path) -> dict[str, dict[str, float]]:
    """Return ``{surface: {name: mtime}}`` for the project.

    Empty surfaces return empty maps. The CLI uses this to print the
    status table.
    """
    out: dict[str, dict[str, float]] = {
        SURFACE_OPENCODE: {},
        SURFACE_CLAUDE: {},
    }
    base = heartbeats_root(project_root)
    if not base.is_dir():
        return out
    for surface_dir in sorted(base.iterdir()):
        if not surface_dir.is_dir():
            continue
        entries = out.setdefault(surface_dir.name, {})
        for entry in surface_dir.iterdir():
            if entry.is_file():
                try:
                    entries[entry.name] = entry.stat().st_mtime
                except OSError:
                    continue
    return out


KNOWN_OPENCODE_PLUGINS: tuple[str, ...] = (
    "role-load",
    "feedback-check",
    "offline-reference",
    "memory-load",
    "memory-history",
    "remember-trigger",
    "todo-curator",
    "session-evidence",
)


# ---------------------------------------------------------------------------
# Capability Manifest — see docs/plan.md work item A'.
#
# Declarative replacement for the hand-maintained plugin↔hook mirror
# table. Each plugin lists the platform capabilities it needs; the
# manifest decides whether a Claude Code mirror is structurally
# possible. Three update rules:
#
#   1. Any user-visible string both surfaces emit must originate from a
#      single Python generator function (see ``_reminder_nudge_text``).
#   2. New plugin → declare requirements before writing the TS plugin.
#      The required-capability list determines whether
#      ``claude_code_mirror`` can be non-None.
#   3. Promotion (OC-only → dual) requires all ``requires`` entries
#      available on Claude Code + Python implementation + test parity.
# ---------------------------------------------------------------------------

PLATFORM_CAPABILITIES: dict[str, dict[str, bool]] = {
    # Available on both platforms — anything that lands at session
    # boundaries or wraps a user prompt.
    "session_start_inject":      {"opencode": True, "claude_code": True},
    "session_stop_inject":       {"opencode": True, "claude_code": True},
    "pre_compact_inject":        {"opencode": True, "claude_code": True},
    "user_prompt_inject":        {"opencode": True, "claude_code": True},
    # OpenCode-only structurally — Claude Code's hook system has no
    # equivalent. Not a TODO; not a stub candidate.
    "session_idle_counter":      {"opencode": True, "claude_code": False},
    "cross_turn_plugin_state":   {"opencode": True, "claude_code": False},
    "mid_turn_message_inject":   {"opencode": True, "claude_code": False},
    "tool_execute_after_inject": {"opencode": True, "claude_code": False},
    # Observe (not mutate) tool results, including error outcomes.
    # OpenCode: message.part.updated events carry ToolPart.state
    # ("error" status + error text). Claude Code: PostToolUse receives
    # tool_response. Distinct from tool_execute_after_inject, which is
    # about mutating the result — unavailable on Claude Code.
    "tool_result_observe":       {"opencode": True, "claude_code": True},
}


PLUGIN_MANIFEST: dict[str, dict] = {
    "memory-load": {
        "requires": ["session_start_inject", "pre_compact_inject"],
        "claude_code_mirror": "memory_load.py",
        "purpose": "Inject MEMORY.md + scope-first principle at session start; drain L3 ingest if pending",
    },
    "memory-history": {
        "requires": ["session_stop_inject"],
        "claude_code_mirror": "memory_history.py",
        "purpose": "Snapshot memory data after every turn; mark L3 ingest pending if journal changed",
    },
    "role-load": {
        "requires": ["session_start_inject"],
        "claude_code_mirror": "role_load.py",
        "purpose": "Inject the active personality's ROLE.md at session start",
    },
    "feedback-check": {
        "requires": ["user_prompt_inject"],
        "claude_code_mirror": "feedback_check.py",
        "purpose": "Per-turn friction-jot cue: on tool dead-end / user correction / broken assumption, append one line to .allmight/feedback/notes.md (consolidated by /reflect)",
    },
    "offline-reference": {
        "requires": ["user_prompt_inject"],
        "claude_code_mirror": "offline_reference.py",
        "purpose": "Tell the agent it is air-gapped: use project_knowledge_search / memory_recall instead of web_search / context7",
    },
    "remember-trigger": {
        "requires": ["session_idle_counter", "mid_turn_message_inject"],
        "claude_code_mirror": None,
        "purpose": "Throttled /remember nudge; escalates to /reflect when .allmight/feedback/ friction entries accumulate, and queues the post-compaction /reflect ask",
    },
    "todo-curator": {
        "requires": ["cross_turn_plugin_state", "mid_turn_message_inject"],
        "claude_code_mirror": None,
        "purpose": "Cross-turn TODO ledger curation",
    },
    "session-evidence": {
        "requires": ["tool_result_observe"],
        "claude_code_mirror": "session_evidence.py",
        "purpose": "Append tool-error records to .allmight/feedback/auto-<date>.jsonl — the deterministic backstop for the feedback-check jot; consolidated by /reflect",
    },
}


def is_cc_mirrored(plugin_name: str) -> bool:
    """True if the OpenCode plugin has a Claude Code mirror declared."""
    entry = PLUGIN_MANIFEST.get(plugin_name)
    if not entry:
        return False
    return entry.get("claude_code_mirror") is not None


def cc_unavailable_reasons(plugin_name: str) -> list[str]:
    """Return the required capabilities that block a Claude Code mirror.

    Empty list means every ``requires`` entry is available on Claude
    Code — at which point ``claude_code_mirror=None`` is a TODO, not a
    structural impossibility. The :class:`MirrorCoherence` tests pin
    both directions.
    """
    entry = PLUGIN_MANIFEST.get(plugin_name)
    if not entry:
        return []
    blocking: list[str] = []
    for cap in entry.get("requires", []):
        if not PLATFORM_CAPABILITIES.get(cap, {}).get("claude_code", False):
            blocking.append(cap)
    return blocking


def format_compatibility_matrix() -> str:
    """Render the plugin × platform matrix as a markdown table.

    Single source of truth for the README's compatibility block.
    Run ``allmight plugin matrix`` to regenerate after changing the
    manifest.
    """
    lines = [
        "| Plugin | OpenCode | Claude Code | Notes |",
        "|--------|----------|-------------|-------|",
    ]
    for name in sorted(PLUGIN_MANIFEST):
        entry = PLUGIN_MANIFEST[name]
        oc = "✓" if name in KNOWN_OPENCODE_PLUGINS else "—"
        mirror = entry.get("claude_code_mirror")
        if mirror:
            cc = "✓"
            note = entry.get("purpose", "")
        else:
            cc = "—"
            blockers = cc_unavailable_reasons(name)
            if blockers:
                note = f"OpenCode-only — requires `{', '.join(blockers)}`"
            else:
                note = "OpenCode-only"
        lines.append(f"| `{name}` | {oc} | {cc} | {note} |")
    return "\n".join(lines)


def _derive_known_claude_hooks() -> tuple[str, ...]:
    """Derive ``KNOWN_CLAUDE_HOOKS`` from the manifest.

    A Python file ``<stem>.py`` declared as ``claude_code_mirror``
    contributes ``<stem>`` to the known set. Keeps the legacy tuple
    in sync with the manifest without a second source of truth.
    """
    names: list[str] = []
    for entry in PLUGIN_MANIFEST.values():
        mirror = entry.get("claude_code_mirror")
        if mirror:
            stem = mirror[:-3] if mirror.endswith(".py") else mirror
            names.append(stem)
    return tuple(sorted(names))


KNOWN_CLAUDE_HOOKS: tuple[str, ...] = _derive_known_claude_hooks()


TS_HEARTBEAT_SNIPPET = """\
// --- All-Might plugin heartbeat (do not edit) ---
import { mkdirSync as __hb_mkdir, utimesSync as __hb_utimes, openSync as __hb_open, closeSync as __hb_close } from "node:fs";
import { join as __hb_join } from "node:path";

function emitHeartbeat(name: string, cwd?: string): void {
  try {
    const base = cwd ?? process.cwd();
    const dir = __hb_join(base, ".allmight", "plugins", "heartbeats", "oc");
    __hb_mkdir(dir, { recursive: true });
    const p = __hb_join(dir, name);
    const now = new Date();
    try {
      __hb_utimes(p, now, now);
    } catch {
      __hb_close(__hb_open(p, "w"));
    }
  } catch {
    // heartbeats must never throw
  }
}
// --- end heartbeat ---
"""


PY_HEARTBEAT_SNIPPET = '''\
# --- All-Might plugin heartbeat (do not edit) ---
def _hb(name):
    try:
        import os as _hb_os
        from pathlib import Path as _hb_Path
        base = _hb_Path(_hb_os.environ.get("CLAUDE_PROJECT_DIR") or _hb_os.getcwd())
        d = base / ".allmight" / "plugins" / "heartbeats" / "cc"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).touch()
    except Exception:
        pass  # heartbeats must never throw
# --- end heartbeat ---
'''


# ---------------------------------------------------------------------------
# Context-injection budget (shared by both surfaces)
# ---------------------------------------------------------------------------
#
# Claude Code caps hook output — plain stdout, ``additionalContext`` and
# ``systemMessage`` alike — at 10,000 characters, and truncates past it
# *silently*. ``role_load`` concatenates every personality's full
# ROLE.md, so a three-personality project clears the cap and loses the
# alphabetically-last roles with no error anywhere.
#
# The budget sits below the hard cap so a fallback notice always fits.
# It is deliberately shared with the OpenCode surface even though
# ``output.parts.unshift`` has no documented cap: a role visible in one
# editor and absent in the other is exactly the "behaviour depends on
# which editor I open the project with" drift the dual-platform
# invariant exists to prevent (see CLAUDE.md -> Editor Compatibility).
#
# See docs/compaction-reprime-proposal.md for the full rationale.
HOOK_OUTPUT_BUDGET = 9_000

# Emitted in place of the full role bodies when they exceed the budget.
# Degrades to a read-on-demand index rather than a blind mid-sentence
# cut — the same progressive-disclosure pattern L2 ``_index.md`` uses,
# so every role stays discoverable at any project size.
ROLE_INDEX_NOTICE = (
    "Role bodies were omitted to stay within this editor's "
    "context-injection budget. The roles below are an index only — read "
    "personalities/<name>/ROLE.md in full before acting for that role."
)

# Appended when even the index does not fit. __N__ is substituted with
# the number of roles dropped, so the omission is always stated rather
# than silent.
ROLE_OMITTED_NOTICE = (
    "... and __N__ further role(s) not listed; see personalities/."
)

# Appended when a single-document injection (MEMORY.md) is trimmed.
DOC_TRUNCATED_NOTICE = (
    "... truncated to fit this editor's context-injection budget. "
    "Read the file directly for the remainder."
)


TS_BUDGET_SNIPPET = """\
// --- All-Might context-injection budget (do not edit) ---
const HOOK_OUTPUT_BUDGET = __HOOK_OUTPUT_BUDGET__;
function fitBudget(text: string, notice: string, limit?: number): string {
  const cap = limit === undefined ? HOOK_OUTPUT_BUDGET : limit;
  if (text.length <= cap) return text;
  const room = cap - notice.length - 2;
  if (room <= 0) return notice.slice(0, Math.max(cap, 0));
  let cut = text.slice(0, room);
  const nl = cut.lastIndexOf("\\n");
  if (nl > 0) cut = cut.slice(0, nl);
  return cut.replace(/\\s+$/, "") + "\\n\\n" + notice;
}
// --- end budget ---
"""


PY_BUDGET_SNIPPET = '''\
# --- All-Might context-injection budget (do not edit) ---
HOOK_OUTPUT_BUDGET = __HOOK_OUTPUT_BUDGET__


def _fit_budget(text, notice, limit=None):
    """Trim ``text`` to the budget at a line boundary, stating the trim.

    ``limit`` overrides the budget when part of it is already reserved
    for content that must survive (e.g. a trailing principle block).
    """
    cap = HOOK_OUTPUT_BUDGET if limit is None else limit
    if len(text) <= cap:
        return text
    room = cap - len(notice) - 2
    if room <= 0:
        return notice[:max(cap, 0)]
    cut = text[:room]
    nl = cut.rfind("\\n")
    if nl > 0:
        cut = cut[:nl]
    return cut.rstrip() + "\\n\\n" + notice
# --- end budget ---
'''


def ts_budget_snippet() -> str:
    """Return the TS budget helper with the shared constant inlined."""
    return TS_BUDGET_SNIPPET.replace(
        "__HOOK_OUTPUT_BUDGET__", str(HOOK_OUTPUT_BUDGET),
    )


def py_budget_snippet() -> str:
    """Return the Python budget helper with the shared constant inlined."""
    return PY_BUDGET_SNIPPET.replace(
        "__HOOK_OUTPUT_BUDGET__", str(HOOK_OUTPUT_BUDGET),
    )
