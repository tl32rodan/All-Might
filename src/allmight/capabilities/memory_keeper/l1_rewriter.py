"""F1.5 — L1 portable-only auditor.

MEMORY.md is loaded every turn via hook, so unbounded growth costs every
agent turn. :class:`L1Auditor` computes whether the body exceeds the cap
and *never* modifies MEMORY.md — triage is the agent's job, prompted by
a passive nudge sentinel.

Design choices:
- **Byte count, not char count.** Multi-byte runes under-count; bytes
  match the real cost of injection.
- **Audit, never trim.** Evicting bullets silently would hide work the
  user wanted persisted. The nudge is a forcing function for essence
  extraction (distill portable facts, migrate corpus-specific content
  to L2 / per-corpus state).
"""

from __future__ import annotations

from dataclasses import dataclass

SENTINEL_MARKER = "allmight_l1_cap"
DEFAULT_MAX_BYTES = 4096


@dataclass
class AuditResult:
    """Outcome of a single L1 audit pass."""

    over: bool
    body_bytes: int
    overflow_bytes: int
    cap: int


class L1Auditor:
    """Reports whether MEMORY.md's body is over the byte cap. Never writes."""

    def __init__(self, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.max_bytes = max_bytes

    def body_of(self, md: str) -> str:
        """Return *md* with the sentinel comment stripped."""
        lines = md.splitlines(keepends=True)
        out = [ln for ln in lines if SENTINEL_MARKER not in ln]
        return "".join(out).lstrip("\n")

    def audit(self, md: str) -> AuditResult:
        """Measure body size against the cap. Pure — never modifies input."""
        body = self.body_of(md)
        body_bytes = len(body.encode("utf-8"))
        over = body_bytes > self.max_bytes
        overflow = body_bytes - self.max_bytes if over else 0
        return AuditResult(
            over=over,
            body_bytes=body_bytes,
            overflow_bytes=overflow,
            cap=self.max_bytes,
        )


def audit_and_update_sentinel(project_dir, cap: int | None = None) -> AuditResult | None:
    """Run an audit at *project_dir* and reconcile the `.l1-over-cap` sentinel.

    - Writes `memory/.l1-over-cap` (YAML) when MEMORY.md body > cap.
    - Removes it when the body is under cap (or when MEMORY.md is absent).
    - Never modifies MEMORY.md.

    Returns the `AuditResult`, or ``None`` when MEMORY.md does not exist.
    """
    from datetime import datetime, timezone
    from pathlib import Path

    root = Path(project_dir)
    memory_md = root / "MEMORY.md"
    sentinel = root / "memory" / ".l1-over-cap"

    if not memory_md.exists():
        if sentinel.exists():
            sentinel.unlink()
        return None

    auditor = L1Auditor(max_bytes=cap or DEFAULT_MAX_BYTES)
    result = auditor.audit(memory_md.read_text())

    if result.over:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sentinel.write_text(
            f"overflow_bytes: {result.overflow_bytes}\n"
            f"cap: {result.cap}\n"
            f"body_bytes: {result.body_bytes}\n"
            f"timestamp: {ts}\n"
        )
    elif sentinel.exists():
        sentinel.unlink()

    return result
