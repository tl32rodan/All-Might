"""Tests for Enrichment — policy only (Power Level removed)."""

import pytest

from allmight.enrichment.policy import default_policy, TriggerEvent


class TestEnrichmentPolicy:
    def test_default_policy_is_advisory(self):
        policy = default_policy()
        assert policy.strategy == "advisory"

    def test_default_policy_has_rules(self):
        policy = default_policy()
        assert len(policy.rules) > 0

    def test_default_policy_covers_key_triggers(self):
        policy = default_policy()
        triggers = {r.trigger for r in policy.rules}
        assert TriggerEvent.ON_READ_SYMBOL in triggers
        assert TriggerEvent.ON_CODE_CHANGE in triggers
        assert TriggerEvent.ON_DISCOVER_RELATION in triggers
