"""Episodic Memory Store — Layer 2 of the agent memory system.

Manages append-only session records (Episodes) stored as YAML files
in ``memory/episodes/YYYY/MM/``.  Each episode is immutable after
creation.  Episodes are indexed by SMAK for semantic search via the
``episodes`` index.

File layout::

    memory/episodes/
    ├── 2026/
    │   ├── 04/
    │   │   ├── sess_abc123.episode.yaml
    │   │   └── sess_def456.episode.yaml
    │   └── 05/
    │       └── ...
    └── ...
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..core.domain import Episode
from ..utils.yaml_io import write_yaml


class EpisodicMemoryStore:
    """Creates, reads, lists, and searches session episodes."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.episodes_dir = root / "memory" / "episodes"

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_episode(
        self,
        session_id: str,
        summary: str,
        *,
        key_decisions: list[str] | None = None,
        observations: list[str] | None = None,
        files_touched: list[str] | None = None,
        topics: list[str] | None = None,
        outcome: str = "",
        importance: float = 0.5,
    ) -> Episode:
        """Create and persist a new Episode.

        Returns the created Episode.
        """
        now = datetime.now(timezone.utc)
        episode_id = f"ep_{uuid.uuid4().hex[:12]}"

        episode = Episode(
            id=episode_id,
            session_id=session_id,
            started_at=now.isoformat(),
            ended_at=now.isoformat(),
            summary=summary,
            key_decisions=key_decisions or [],
            observations=observations or [],
            files_touched=files_touched or [],
            topics=topics or [],
            outcome=outcome,
            importance=importance,
            consolidated=False,
        )

        self._persist(episode, now)
        return episode

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_episode(self, episode_id: str) -> Episode | None:
        """Load a single episode by ID.  Returns None if not found."""
        for path in self.episodes_dir.rglob("*.episode.yaml"):
            ep = self._load(path)
            if ep and ep.id == episode_id:
                return ep
        return None

    def list_episodes(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int = 50,
        unconsolidated_only: bool = False,
    ) -> list[Episode]:
        """List episodes in reverse chronological order.

        Args:
            since: ISO timestamp — only episodes created after this.
            until: ISO timestamp — only episodes created before this.
            limit: Maximum number to return.
            unconsolidated_only: If True, only return un-consolidated episodes.
        """
        episodes: list[Episode] = []

        for path in sorted(self.episodes_dir.rglob("*.episode.yaml"), reverse=True):
            ep = self._load(path)
            if ep is None:
                continue
            if since and ep.started_at < since:
                continue
            if until and ep.started_at > until:
                continue
            if unconsolidated_only and ep.consolidated:
                continue
            episodes.append(ep)
            if len(episodes) >= limit:
                break

        return episodes

    def count(self) -> int:
        """Total number of stored episodes."""
        return sum(1 for _ in self.episodes_dir.rglob("*.episode.yaml"))

    def count_unconsolidated(self) -> int:
        """Number of episodes not yet consolidated."""
        count = 0
        for path in self.episodes_dir.rglob("*.episode.yaml"):
            ep = self._load(path)
            if ep and not ep.consolidated:
                count += 1
        return count

    # ------------------------------------------------------------------
    # Update (limited — episodes are mostly immutable)
    # ------------------------------------------------------------------

    def mark_consolidated(self, episode_id: str) -> bool:
        """Mark an episode as consolidated.  Returns True if found."""
        for path in self.episodes_dir.rglob("*.episode.yaml"):
            ep = self._load(path)
            if ep and ep.id == episode_id:
                ep.consolidated = True
                self._write_episode_file(path, ep)
                return True
        return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _persist(self, episode: Episode, timestamp: datetime) -> None:
        """Write episode to date-partitioned directory."""
        year_month = timestamp.strftime("%Y/%m")
        target_dir = self.episodes_dir / year_month
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{episode.session_id}.episode.yaml"
        path = target_dir / filename
        self._write_episode_file(path, episode)

    @staticmethod
    def _write_episode_file(path: Path, episode: Episode) -> None:
        """Serialise an Episode to YAML."""
        data = {
            "id": episode.id,
            "session_id": episode.session_id,
            "started_at": episode.started_at,
            "ended_at": episode.ended_at,
            "summary": episode.summary,
            "key_decisions": episode.key_decisions,
            "observations": episode.observations,
            "files_touched": episode.files_touched,
            "topics": episode.topics,
            "outcome": episode.outcome,
            "importance": episode.importance,
            "consolidated": episode.consolidated,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    @staticmethod
    def _load(path: Path) -> Episode | None:
        """Deserialise an Episode from YAML."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return Episode(
                id=data["id"],
                session_id=data["session_id"],
                started_at=data.get("started_at", ""),
                ended_at=data.get("ended_at", ""),
                summary=data.get("summary", ""),
                key_decisions=data.get("key_decisions", []),
                observations=data.get("observations", []),
                files_touched=data.get("files_touched", []),
                topics=data.get("topics", []),
                outcome=data.get("outcome", ""),
                importance=data.get("importance", 0.5),
                consolidated=data.get("consolidated", False),
            )
        except Exception:
            return None

    def initialize(self) -> None:
        """Create the episodes directory."""
        self.episodes_dir.mkdir(parents=True, exist_ok=True)
