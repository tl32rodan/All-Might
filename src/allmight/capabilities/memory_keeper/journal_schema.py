"""F5 — Structured journal entry schema (v1).

Journal files are markdown with an optional YAML frontmatter block at
the top. The sentinel ``allmight_journal: v1`` flags structured entries;
anything without the sentinel is treated as legacy freeform, and
:func:`parse_frontmatter` returns ``None`` (backward-compatible).

The freeform body stays first-class — agents keep writing markdown the
way they always have. Frontmatter is mechanical: captured by the
trajectory-writer plugin (auto entries), or emitted by ``/remember``
and ``/reflect`` templates (slash-command entries).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import yaml

SENTINEL_KEY = "allmight_journal"
SENTINEL_VALUE = "v1"

_VALID_TYPES = frozenset({
    "trajectory", "reflection", "discovery", "decision", "correction",
})
_VALID_OUTCOMES = frozenset({"success", "partial", "failure", "aborted"})
_VALID_VERDICTS = frozenset({"ok", "drift", "blocked"})


@dataclass
class ToolCallRecord:
    """One tool invocation inside a journal entry."""

    tool: str
    args: dict[str, Any]
    verdict: str  # ok | drift | blocked

    def __post_init__(self) -> None:
        if self.verdict not in _VALID_VERDICTS:
            raise ValueError(
                f"invalid verdict: {self.verdict!r} "
                f"(expected one of {sorted(_VALID_VERDICTS)})"
            )


@dataclass
class JournalEntry:
    """A structured journal entry.

    The ``body`` field is the freeform markdown below the frontmatter
    fence — the part humans read. Everything else is the mechanical
    envelope.
    """

    id: str
    type: str
    workspace: str
    trigger: str
    input: str
    tool_calls: list[ToolCallRecord]
    output: str
    outcome_label: str
    tags: list[str]
    supersedes: str | None
    created_at: str
    body: str = ""

    def __post_init__(self) -> None:
        if self.type not in _VALID_TYPES:
            raise ValueError(
                f"invalid type: {self.type!r} "
                f"(expected one of {sorted(_VALID_TYPES)})"
            )
        if self.outcome_label not in _VALID_OUTCOMES:
            raise ValueError(
                f"invalid outcome_label: {self.outcome_label!r} "
                f"(expected one of {sorted(_VALID_OUTCOMES)})"
            )


def dump_frontmatter(entry: JournalEntry) -> str:
    """Serialize *entry* as a frontmatter block followed by its body."""
    front: dict[str, Any] = {
        SENTINEL_KEY: SENTINEL_VALUE,
        "id": entry.id,
        "type": entry.type,
        "workspace": entry.workspace,
        "trigger": entry.trigger,
        "input": entry.input,
        "tool_calls": [asdict(tc) for tc in entry.tool_calls],
        "output": entry.output,
        "outcome_label": entry.outcome_label,
        "tags": list(entry.tags),
        "supersedes": entry.supersedes,
        "created_at": entry.created_at,
    }
    yaml_block = yaml.safe_dump(
        front,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    return f"---\n{yaml_block}---\n{entry.body}"


def parse_frontmatter(text: str) -> JournalEntry | None:
    """Parse a structured journal entry.

    Returns ``None`` for legacy freeform entries (no leading ``---``
    fence or missing the v1 sentinel) and for frontmatter that fails
    to parse as YAML. This is intentional — callers decide what to do
    with legacy files (usually skip them).
    """
    if not text.startswith("---\n"):
        return None

    rest = text[4:]
    closing = rest.find("\n---\n")
    if closing == -1:
        return None

    yaml_text = rest[:closing]
    body = rest[closing + len("\n---\n"):]

    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return None

    if not isinstance(data, dict) or data.get(SENTINEL_KEY) != SENTINEL_VALUE:
        return None

    tool_calls_raw = data.get("tool_calls") or []
    tool_calls: list[ToolCallRecord] = []
    for tc in tool_calls_raw:
        if not isinstance(tc, dict):
            return None
        try:
            tool_calls.append(
                ToolCallRecord(
                    tool=tc.get("tool", ""),
                    args=tc.get("args") or {},
                    verdict=tc.get("verdict", "ok"),
                )
            )
        except ValueError:
            return None

    try:
        return JournalEntry(
            id=data.get("id", ""),
            type=data.get("type", ""),
            workspace=data.get("workspace", ""),
            trigger=data.get("trigger", ""),
            input=data.get("input", ""),
            tool_calls=tool_calls,
            output=data.get("output", ""),
            outcome_label=data.get("outcome_label", ""),
            tags=list(data.get("tags") or []),
            supersedes=data.get("supersedes"),
            created_at=data.get("created_at", ""),
            body=body,
        )
    except ValueError:
        return None


def entry_to_dict(entry: JournalEntry) -> dict[str, Any]:
    """Flat dict representation for JSONL export (body excluded)."""
    return {
        "id": entry.id,
        "type": entry.type,
        "workspace": entry.workspace,
        "trigger": entry.trigger,
        "input": entry.input,
        "tool_calls": [asdict(tc) for tc in entry.tool_calls],
        "output": entry.output,
        "outcome_label": entry.outcome_label,
        "tags": list(entry.tags),
        "supersedes": entry.supersedes,
        "created_at": entry.created_at,
    }
