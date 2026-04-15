"""Working Memory Manager — Layer 1 of the agent memory system.

Manages ``MEMORY.md``, the always-in-context file that agents see at
session start.  Structured into named sections that can be independently
read and updated while respecting a configurable token budget.

Design follows the existing ``CLAUDE.md`` marker-based section pattern
used by ``detroit_smak/initializer.py``.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

from ..utils.yaml_io import load_config


# Approximate tokens ≈ words × 1.3  (conservative estimate)
_TOKENS_PER_WORD = 1.3

# Sections in MEMORY.md and their markers
SECTIONS = (
    "user_model",
    "environment",
    "active_goals",
    "pinned_memories",
)

_SECTION_HEADERS: dict[str, str] = {
    "user_model": "User Model",
    "environment": "Environment Facts",
    "active_goals": "Active Goals",
    "pinned_memories": "Pinned Memories",
}


def _marker(section: str, end: bool = False) -> str:
    tag = "END" if end else "BEGIN"
    return f"<!-- MEMORY:{section.upper()}:{tag} -->"


def _estimate_tokens(text: str) -> int:
    """Rough token estimate from word count."""
    words = len(text.split())
    return math.ceil(words * _TOKENS_PER_WORD)


class WorkingMemoryManager:
    """Reads and writes the structured ``MEMORY.md`` file.

    ``MEMORY.md`` lives at ``<root>/memory/working/MEMORY.md`` and is
    designed to be injected into the agent's system prompt (or loaded
    as a SKILL.md-style auto-load file).

    Each named section is independently updatable.  The manager enforces
    a token budget — if the total size exceeds the limit, it reports the
    overage so the caller can decide what to evict.
    """

    def __init__(self, root: Path, budget: int = 4000) -> None:
        self.root = root
        self.memory_dir = root / "memory" / "working"
        self.memory_path = self.memory_dir / "MEMORY.md"
        self.budget = budget

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read(self) -> dict[str, str]:
        """Return all sections as ``{section_name: content}``."""
        if not self.memory_path.exists():
            return {s: "" for s in SECTIONS}

        text = self.memory_path.read_text()
        result: dict[str, str] = {}

        for section in SECTIONS:
            begin = _marker(section)
            end = _marker(section, end=True)
            if begin in text and end in text:
                start_idx = text.index(begin) + len(begin)
                end_idx = text.index(end)
                result[section] = text[start_idx:end_idx].strip()
            else:
                result[section] = ""

        return result

    def read_section(self, section: str) -> str:
        """Return the content of a single section."""
        if section not in SECTIONS:
            raise ValueError(f"Unknown section '{section}'. Valid: {SECTIONS}")
        return self.read().get(section, "")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def update(self, section: str, content: str) -> int:
        """Update a single section and persist.

        Returns the current total estimated token count after the update.
        """
        if section not in SECTIONS:
            raise ValueError(f"Unknown section '{section}'. Valid: {SECTIONS}")

        sections = self.read()
        sections[section] = content
        self._persist(sections)
        return self.token_usage()

    def clear_section(self, section: str) -> None:
        """Clear a single section."""
        self.update(section, "")

    # ------------------------------------------------------------------
    # Render — produce the full in-context block
    # ------------------------------------------------------------------

    def render(self) -> str:
        """Render the complete MEMORY.md content for context injection."""
        sections = self.read()
        return self._build_content(sections)

    # ------------------------------------------------------------------
    # Budget
    # ------------------------------------------------------------------

    def token_usage(self) -> int:
        """Estimate total tokens in current MEMORY.md."""
        if not self.memory_path.exists():
            return 0
        return _estimate_tokens(self.memory_path.read_text())

    def is_over_budget(self) -> bool:
        return self.token_usage() > self.budget

    def budget_status(self) -> dict[str, int | bool]:
        """Return token usage vs. budget."""
        usage = self.token_usage()
        return {
            "tokens_used": usage,
            "budget": self.budget,
            "remaining": max(0, self.budget - usage),
            "over_budget": usage > self.budget,
        }

    # ------------------------------------------------------------------
    # Initialise — create a blank MEMORY.md
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create the working memory directory and an empty MEMORY.md."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        sections = {s: "" for s in SECTIONS}
        self._persist(sections)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _persist(self, sections: dict[str, str]) -> None:
        """Write all sections to MEMORY.md."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        content = self._build_content(sections)
        self.memory_path.write_text(content)

    @staticmethod
    def _build_content(sections: dict[str, str]) -> str:
        """Build the full MEMORY.md text from section dict."""
        lines = [
            "# Agent Working Memory",
            "",
            "> Auto-managed by All-Might memory system.",
            "> Do not edit this file by hand — use `/memory-update`.",
            "",
        ]

        for section in SECTIONS:
            header = _SECTION_HEADERS[section]
            body = sections.get(section, "").strip()
            lines.append(f"## {header}")
            lines.append("")
            lines.append(_marker(section))
            if body:
                lines.append(body)
            lines.append(_marker(section, end=True))
            lines.append("")

        ts = datetime.now(timezone.utc).isoformat()
        lines.append(f"_Last updated: {ts}_")
        lines.append("")
        return "\n".join(lines)
