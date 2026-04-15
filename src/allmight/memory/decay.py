"""Decay Engine — Ebbinghaus forgetting curves for agent memory.

Implements ``M(t) = e^(-t / S)`` where:

- ``t`` = hours since ``last_accessed``
- ``S`` = memory strength = ``base_S × ln(1 + access_count)``
- ``base_S`` is configurable (default 168 h ≈ 1-week half-life for
  never-accessed memories)

Accessed memories resist decay: each retrieval bumps ``last_accessed``
and ``access_count``, increasing ``S``.

Decay is computed **lazily** at retrieval time — no background sweeps.
The explicit ``apply_decay()`` is for manual garbage-collection passes.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone


# Default base strength in hours.  A memory accessed once has
# S = 168 × ln(2) ≈ 116 h, giving a 50 % retention after ~5 days.
DEFAULT_BASE_STRENGTH_HOURS: float = 168.0

# Below this score the entry is considered "dormant".
DORMANT_THRESHOLD: float = 0.10

# Below this score the entry is eligible for archival/deletion.
ARCHIVE_THRESHOLD: float = 0.01


def compute_decay_score(
    last_accessed: str,
    access_count: int,
    *,
    now: datetime | None = None,
    base_strength: float = DEFAULT_BASE_STRENGTH_HOURS,
) -> float:
    """Compute the current retention score for a memory entry.

    Returns a float in ``(0, 1]`` where 1.0 means "just accessed"
    and values approaching 0 mean "effectively forgotten".
    """
    if now is None:
        now = datetime.now(timezone.utc)

    try:
        accessed_dt = datetime.fromisoformat(last_accessed)
    except (ValueError, TypeError):
        return 0.0

    # Ensure timezone-aware comparison
    if accessed_dt.tzinfo is None:
        accessed_dt = accessed_dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    elapsed_hours = max((now - accessed_dt).total_seconds() / 3600.0, 0.0)

    # Strength grows logarithmically with access count.
    # Creation itself counts as one access (min 1) so that brand-new
    # entries are not immediately forgotten.
    effective_count = max(access_count, 1)
    strength = base_strength * math.log(1.0 + effective_count)
    if strength <= 0:
        return 0.0

    return math.exp(-elapsed_hours / strength)


def is_dormant(
    last_accessed: str,
    access_count: int,
    *,
    now: datetime | None = None,
    base_strength: float = DEFAULT_BASE_STRENGTH_HOURS,
) -> bool:
    """Check if a memory entry has decayed below the dormant threshold."""
    score = compute_decay_score(
        last_accessed, access_count, now=now, base_strength=base_strength
    )
    return score < DORMANT_THRESHOLD


def is_archivable(
    last_accessed: str,
    access_count: int,
    *,
    now: datetime | None = None,
    base_strength: float = DEFAULT_BASE_STRENGTH_HOURS,
) -> bool:
    """Check if a memory entry has decayed enough for archival."""
    score = compute_decay_score(
        last_accessed, access_count, now=now, base_strength=base_strength
    )
    return score < ARCHIVE_THRESHOLD


class DecayEngine:
    """Applies forgetting curves across memory stores.

    Primarily used for explicit GC sweeps via ``/memory gc``.
    Normal retrieval computes decay scores inline via the module-level
    functions above.
    """

    def __init__(self, base_strength: float = DEFAULT_BASE_STRENGTH_HOURS) -> None:
        self.base_strength = base_strength

    def score(self, last_accessed: str, access_count: int) -> float:
        """Compute decay score for a single entry."""
        return compute_decay_score(
            last_accessed, access_count, base_strength=self.base_strength
        )

    def classify(self, last_accessed: str, access_count: int) -> str:
        """Classify a memory entry's decay status.

        Returns one of: ``"active"``, ``"fading"``, ``"dormant"``,
        ``"archivable"``.
        """
        s = self.score(last_accessed, access_count)
        if s >= 0.5:
            return "active"
        if s >= DORMANT_THRESHOLD:
            return "fading"
        if s >= ARCHIVE_THRESHOLD:
            return "dormant"
        return "archivable"
