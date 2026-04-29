"""F5 — Export structured journal entries to JSONL for offline analysis.

Only v1-sentinel entries are exported. Legacy freeform entries are
skipped, with the count returned so the CLI can report it.
"""

from __future__ import annotations

import json
from pathlib import Path

from .journal_schema import entry_to_dict, parse_frontmatter


def export_to_jsonl(journal_dir: Path, out_path: Path) -> int:
    """Walk *journal_dir* and write structured entries to *out_path*.

    Returns the count of legacy/unparseable entries skipped.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    skipped = 0
    lines: list[str] = []

    if journal_dir.exists():
        for md in sorted(journal_dir.rglob("*.md")):
            if not md.is_file():
                continue
            entry = parse_frontmatter(md.read_text())
            if entry is None:
                skipped += 1
                continue
            lines.append(json.dumps(entry_to_dict(entry), ensure_ascii=False))

    out_path.write_text("\n".join(lines) + ("\n" if lines else ""))
    return skipped
