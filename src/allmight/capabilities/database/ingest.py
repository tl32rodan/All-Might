"""Database L-DB SMAK auto-ingest orchestration.

The read-surfacing closure (``docs/retrieval-surfacing-proposal.md`` §6,
bundled): the ``search-surface`` plugin lazily kicks
``allmight database ingest --incremental`` off the hot path when the
agent greps source, so each personality's ``database/*`` index
self-bootstraps (create) and stays fresh (maintain).

This module is the canonical, **testable Python core** — the TS plugin
only spawns the CLI fire-and-forget. It parallels
``capabilities/memory/ingest.py`` but globs the database workspace
configs instead of the per-personality memory configs.

Divergence from the memory L3 closure (deliberate, see the proposal):
memory's Stop hook can cheaply scan ``personalities/*/memory/journal``
(small, in-project) to decide whether to re-ingest. Database workspaces
index **external** source trees of arbitrary size, so a per-turn mtime
scan is too expensive. Instead the plugin throttles on the
``.allmight/db_last_ingest`` marker mtime and delegates change-detection
to ``smak ingest --incremental`` itself (cheap when nothing changed).
No background watcher daemon (CLAUDE.md touch-file-simplicity).

State file (relative to project root):

- ``.allmight/db_last_ingest`` — its mtime is "last successful database
  ingest". Touched by :func:`run_db_ingest_cycle` on overall success;
  the plugin reads its mtime to throttle re-kicks.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

DB_LAST_INGEST_REL = Path(".allmight") / "db_last_ingest"
INGEST_TIMEOUT_SECONDS = 120


@dataclass
class DbIngestResult:
    """Outcome of one :func:`run_db_ingest_cycle` invocation."""

    succeeded: list[Path] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)


def find_db_configs(root: Path) -> list[Path]:
    """Return absolute paths to every ``personalities/*/database/*/config.yaml``.

    These are the SMAK workspace configs for each personality's
    knowledge corpora. Result is sorted for determinism — the same
    glob ``mcp/knowledge_server.discover_database_configs`` uses.
    """
    personalities = root / "personalities"
    if not personalities.is_dir():
        return []
    return sorted(personalities.glob("*/database/*/config.yaml"))


def _smak_argv(cmd: str, config: Path, *, incremental: bool) -> list[str]:
    """Build the argv for one ``smak ingest`` invocation.

    Supports ``cmd`` being either a single binary name (``"smak"``) or a
    wrapped command line (``"python /path/to/fake_smak.py"``) by
    shlex-splitting — the test fixture wraps a Python script. Mirrors
    ``capabilities/memory/ingest.py::_smak_argv`` (kept local so the
    database capability owns its directory with no cross-capability
    import).
    """
    parts = shlex.split(cmd)
    argv = [*parts, "ingest", "--config", str(config)]
    if incremental:
        argv.append("--incremental")
    return argv


def run_db_ingest_cycle(
    root: Path,
    *,
    incremental: bool = True,
    smak_cmd: str = "smak",
) -> DbIngestResult:
    """Run ``smak ingest`` for every database workspace config.

    On overall success (no errors AND at least one config processed),
    touches ``.allmight/db_last_ingest`` so the plugin's throttle treats
    the index as fresh-as-of-now. On any per-workspace error the marker
    is left untouched so the next kick retries.
    """
    result = DbIngestResult()
    configs = find_db_configs(root)
    if not configs:
        return result

    for config in configs:
        workspace_dir = config.parent
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
            result.errors.append((workspace_dir, f"command not found: {argv[0]}"))
            continue
        except subprocess.TimeoutExpired:
            result.errors.append(
                (workspace_dir, f"timeout after {INGEST_TIMEOUT_SECONDS}s")
            )
            continue

        if proc.returncode == 0:
            result.succeeded.append(workspace_dir)
        else:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            msg = stderr or stdout or f"exit {proc.returncode}"
            result.errors.append((workspace_dir, msg))

    if not result.errors:
        last_ingest = root / DB_LAST_INGEST_REL
        last_ingest.parent.mkdir(parents=True, exist_ok=True)
        last_ingest.touch()

    return result
