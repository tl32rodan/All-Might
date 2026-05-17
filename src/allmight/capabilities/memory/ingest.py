"""L3 SMAK auto-ingest orchestration — see ``docs/plan.md`` work item C'.

This module is the canonical Python implementation. Stop hooks
(``memory-history.ts`` / ``memory_history.py``) inline the
marker-write decision logic so they remain self-contained and fast;
the hook's inlined version must stay behaviourally equivalent to
:func:`journal_has_unindexed_files` here.

State files (all relative to project root):

- ``.allmight/ingest.pending`` — presence marker: drain has not yet
  run for the newest journal entries. Touched by the Stop hook,
  removed by :func:`run_ingest_cycle` on overall success.
- ``.allmight/last_ingest`` — its mtime is the cutoff for the
  "is the journal newer than the index?" comparison. Touched by
  :func:`run_ingest_cycle` on overall success.

Trade-off (documented in ``docs/plan.md``): same-session ``/recall``
may miss the just-written entry. Next session's drain picks it up.
The embedding cost (5–30s) never blocks a turn.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

INGEST_PENDING_REL = Path(".allmight") / "ingest.pending"
LAST_INGEST_REL = Path(".allmight") / "last_ingest"
INGEST_TIMEOUT_SECONDS = 120


@dataclass
class IngestResult:
    """Outcome of one :func:`run_ingest_cycle` invocation."""

    succeeded: list[Path] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)


def find_smak_configs(root: Path) -> list[Path]:
    """Return absolute paths to every ``personalities/*/memory/smak_config.yaml``.

    Result is sorted for determinism across platforms.
    """
    personalities = root / "personalities"
    if not personalities.is_dir():
        return []
    return sorted(personalities.glob("*/memory/smak_config.yaml"))


def journal_has_unindexed_files(root: Path) -> bool:
    """Return True if any journal entry is newer than ``last_ingest``.

    Walks ``personalities/*/memory/journal/**/*.md``. Short-circuits
    on the first newer file. Missing personalities / missing journal
    dirs are not errors — the caller decides whether that warrants a
    pending marker (it does not).
    """
    last_ingest = root / LAST_INGEST_REL
    try:
        cutoff = last_ingest.stat().st_mtime if last_ingest.exists() else 0.0
    except OSError:
        cutoff = 0.0

    personalities = root / "personalities"
    if not personalities.is_dir():
        return False

    for journal_dir in personalities.glob("*/memory/journal"):
        for entry in journal_dir.rglob("*.md"):
            try:
                if entry.stat().st_mtime > cutoff:
                    return True
            except OSError:
                continue
    return False


def _smak_argv(cmd: str, config: Path, *, incremental: bool) -> list[str]:
    """Build the argv for one ``smak ingest`` invocation.

    Supports ``cmd`` being either a single binary name (``"smak"``) or
    a wrapped command line (``"python /path/to/fake_smak.py"``) by
    shlex-splitting on first whitespace. This matters for the test
    fixture, which wraps a Python script.
    """
    parts = shlex.split(cmd)
    argv = [*parts, "ingest", "--config", str(config)]
    if incremental:
        argv.append("--incremental")
    return argv


def run_ingest_cycle(
    root: Path,
    *,
    incremental: bool = True,
    smak_cmd: str = "smak",
) -> IngestResult:
    """Run ``smak ingest`` for every personality config.

    On overall success (no errors AND at least one config processed):

    - Touches ``.allmight/last_ingest`` so future Stop-hook scans
      treat the indexed-as-of-now state as the cutoff.
    - Removes ``.allmight/ingest.pending`` if present.

    On any per-personality error, the markers are left untouched so
    the next session's drain retries the cycle.
    """
    result = IngestResult()
    configs = find_smak_configs(root)
    if not configs:
        return result

    for config in configs:
        personality_dir = config.parent.parent
        argv = _smak_argv(smak_cmd, config, incremental=incremental)
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=INGEST_TIMEOUT_SECONDS,
                check=False,
            )
        except FileNotFoundError:
            result.errors.append((personality_dir, f"command not found: {argv[0]}"))
            continue
        except subprocess.TimeoutExpired:
            result.errors.append(
                (personality_dir, f"timeout after {INGEST_TIMEOUT_SECONDS}s")
            )
            continue

        if proc.returncode == 0:
            result.succeeded.append(personality_dir)
        else:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            msg = stderr or stdout or f"exit {proc.returncode}"
            result.errors.append((personality_dir, msg))

    if not result.errors:
        last_ingest = root / LAST_INGEST_REL
        last_ingest.parent.mkdir(parents=True, exist_ok=True)
        last_ingest.touch()
        pending = root / INGEST_PENDING_REL
        if pending.exists():
            pending.unlink()

    return result
