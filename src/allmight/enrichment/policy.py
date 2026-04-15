"""Enrichment Policy — defines when and what to enrich.

These policies are advisory — they are embedded in the enrichment skill
to guide agents, not enforced programmatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TriggerEvent(Enum):
    """Events that trigger enrichment suggestions."""

    ON_READ_SYMBOL = "on_read_symbol"
    ON_DISCOVER_RELATION = "on_discover_relation"
    ON_CODE_CHANGE = "on_code_change"
    ON_SEARCH_HIT = "on_search_hit"
    # Agent Memory triggers
    ON_SESSION_END = "on_session_end"
    ON_MEMORY_CONFLICT = "on_memory_conflict"
    ON_CONSOLIDATION = "on_consolidation"


@dataclass
class EnrichmentRule:
    """A single enrichment rule — when to suggest enrichment."""

    trigger: TriggerEvent
    condition: str
    action: str
    priority: str = "normal"  # "high", "normal", "low"


@dataclass
class EnrichmentPolicy:
    """A complete enrichment policy for a project."""

    strategy: str = "advisory"  # "advisory" or "aggressive"
    rules: list[EnrichmentRule] = field(default_factory=list)


def default_policy() -> EnrichmentPolicy:
    """Create the default advisory enrichment policy."""
    return EnrichmentPolicy(
        strategy="advisory",
        rules=[
            EnrichmentRule(
                trigger=TriggerEvent.ON_READ_SYMBOL,
                condition="Symbol has no intent in sidecar",
                action="Suggest: enrich_symbol with intent describing purpose",
                priority="normal",
            ),
            EnrichmentRule(
                trigger=TriggerEvent.ON_DISCOVER_RELATION,
                condition="Two entities are related but no relation exists in sidecar",
                action="Suggest: enrich_symbol with relation UID",
                priority="normal",
            ),
            EnrichmentRule(
                trigger=TriggerEvent.ON_CODE_CHANGE,
                condition="Code was modified and sidecar exists",
                action="Suggest: verify and update sidecar intent",
                priority="high",
            ),
            EnrichmentRule(
                trigger=TriggerEvent.ON_SEARCH_HIT,
                condition="Search returned a hit with no sidecar",
                action="Suggest: enrich_file to create stub sidecar",
                priority="low",
            ),
            # Agent Memory rules
            EnrichmentRule(
                trigger=TriggerEvent.ON_SESSION_END,
                condition="Session produced observations about code symbols",
                action="Suggest: record episode and check for enrichable observations",
                priority="normal",
            ),
            EnrichmentRule(
                trigger=TriggerEvent.ON_MEMORY_CONFLICT,
                condition="New observation contradicts an existing semantic fact about a symbol",
                action="Suggest: supersede fact and update sidecar intent if applicable",
                priority="high",
            ),
            EnrichmentRule(
                trigger=TriggerEvent.ON_CONSOLIDATION,
                condition="Consolidation extracted a code-structure observation",
                action="Suggest: create sidecar enrichment from consolidated memory",
                priority="normal",
            ),
        ],
    )
