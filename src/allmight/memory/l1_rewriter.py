"""F1 — L1 handoff rewriter.

MEMORY.md is loaded every turn via hook, so unbounded growth costs
every agent turn. :class:`HandoffRewriter` enforces a byte cap on the
body (FIFO bullet eviction) and manages the ``Next Session Start Here``
section that the handoff-writer plugin populates before compaction.

Design choices:
- **Byte count, not char count.** Multi-byte runes under-count; bytes
  match the real cost of injection.
- **FIFO bullet eviction.** Oldest bullets (top of each section) go
  first — the premise is that the latest turns matter most.
- **Protected section.** ``## Next Session Start Here`` is never
  evicted. Its whole purpose is to survive handoff.
- **Section headers preserved.** Empty sections signal to the agent
  that the scope exists — dropping them makes the file misleading.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SENTINEL_MARKER = "allmight_l1_cap"
DEFAULT_MAX_BYTES = 4096
PROTECTED_SECTION = "Next Session Start Here"


@dataclass
class _Section:
    header: str                     # "## Project Map"
    pre: list[str] = field(default_factory=list)   # non-bullet lines before bullets
    bullets: list[str] = field(default_factory=list)
    post: list[str] = field(default_factory=list)  # trailing blank lines


def _is_bullet(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("- ") or s.startswith("* ")


def _parse_sections(body: str) -> tuple[list[str], list[_Section]]:
    """Split *body* into (prelude_lines, sections).

    Prelude is everything before the first ``## `` header (typically
    ``# Project Memory`` and blank lines).
    """
    lines = body.splitlines()
    prelude: list[str] = []
    sections: list[_Section] = []
    current: _Section | None = None
    seen_bullet = False

    for line in lines:
        if line.startswith("## "):
            current = _Section(header=line)
            sections.append(current)
            seen_bullet = False
            continue
        if current is None:
            prelude.append(line)
            continue
        if _is_bullet(line):
            current.bullets.append(line)
            seen_bullet = True
        elif seen_bullet:
            current.post.append(line)
        else:
            current.pre.append(line)

    return prelude, sections


def _render(prelude: list[str], sections: list[_Section]) -> str:
    out: list[str] = []
    out.extend(prelude)
    for sec in sections:
        out.append(sec.header)
        out.extend(sec.pre)
        out.extend(sec.bullets)
        out.extend(sec.post)
    rendered = "\n".join(out)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


class HandoffRewriter:
    """Enforce the L1 byte cap and manage the handoff section."""

    def __init__(self, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.max_bytes = max_bytes

    def body_of(self, md: str) -> str:
        """Return *md* with the sentinel comment stripped."""
        lines = md.splitlines(keepends=True)
        out = [ln for ln in lines if SENTINEL_MARKER not in ln]
        return "".join(out).lstrip("\n")

    def enforce_cap(self, md: str) -> tuple[str, str]:
        """Trim *md* body to ``max_bytes`` and return ``(trimmed, overflow)``.

        Overflow is a plain-text string listing dropped bullets, one
        per line with their section as a prefix. It's suitable for
        appending to a journal spill file.
        """
        body = self.body_of(md)
        if len(body.encode("utf-8")) <= self.max_bytes:
            return md, ""

        prelude, sections = _parse_sections(body)
        overflow_lines: list[str] = []

        # Round-robin FIFO eviction across non-protected sections.
        while len(_render(prelude, sections).encode("utf-8")) > self.max_bytes:
            dropped_any = False
            for sec in sections:
                sec_name = sec.header.lstrip("# ").strip()
                if sec_name == PROTECTED_SECTION:
                    continue
                if sec.bullets:
                    dropped = sec.bullets.pop(0)
                    overflow_lines.append(f"[{sec_name}] {dropped.lstrip()}")
                    dropped_any = True
                    if len(_render(prelude, sections).encode("utf-8")) <= self.max_bytes:
                        break
            if not dropped_any:
                # No more evictable bullets — stop even if still over.
                break

        trimmed_body = _render(prelude, sections)
        # Re-attach sentinel at the top of the rewritten file.
        sentinel = f"<!-- {SENTINEL_MARKER}={self.max_bytes} -->\n"
        if sentinel.strip() in md:
            # Preserve the original sentinel line exactly once.
            for line in md.splitlines():
                if SENTINEL_MARKER in line:
                    sentinel = line + "\n"
                    break
        trimmed = sentinel + "\n" + trimmed_body
        overflow = "\n".join(overflow_lines) + ("\n" if overflow_lines else "")
        return trimmed, overflow

    def prepend_handoff(self, md: str, bullets: list[str]) -> str:
        """Replace the ``Next Session Start Here`` section with *bullets*.

        Creates the section at the end of the document if missing.
        """
        body = self.body_of(md)
        prelude, sections = _parse_sections(body)

        target: _Section | None = None
        for sec in sections:
            if sec.header.strip().lstrip("# ").strip() == PROTECTED_SECTION:
                target = sec
                break

        if target is None:
            target = _Section(
                header=f"## {PROTECTED_SECTION}",
                pre=[""],
                bullets=[],
                post=[""],
            )
            sections.append(target)

        target.bullets = [f"- {b.lstrip('- ').lstrip('* ')}" for b in bullets]
        # Ensure a blank line between header and bullets.
        if not target.pre or target.pre[-1] != "":
            target.pre.append("")

        rewritten_body = _render(prelude, sections)

        # Preserve sentinel if present.
        for line in md.splitlines():
            if SENTINEL_MARKER in line:
                return line + "\n\n" + rewritten_body
        return rewritten_body
