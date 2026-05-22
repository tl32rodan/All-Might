"""Routing-contract preamble for command bodies.

Every generated command body that addresses a personality's data dir
prepends ``ROUTING_PREAMBLE`` so the agent knows how to resolve the
``<active>`` placeholder before substituting it into paths.

The contract is **(explicit mention) → (conversation context) →
(default)**, where the default lives at the top of ``MEMORY.md`` as
a leading callout::

    > **Default personality**: <name>

This format is parsed by command bodies and plugins; commit 7's
init writes nothing here, commit 8's ``/onboard`` skill writes it
once the user picks a default. ``MEMORY.md`` is plugin-injected
into every chat, so the callout is always in the agent's context.
"""

ROUTING_PREAMBLE = """\
## Routing — pick the active personality

Substitute the active personality's name for ``<active>`` in every
path below. Resolution order:

1. **Explicit mention** in the user's message
   (e.g. "for stdcell_owner ...").
2. **Conversation context** — recent turns clearly about one
   personality's domain.
3. **Default** — MEMORY.md's leading callout
   ``> **Default personality**: <name>``. If the callout is absent
   and only one personality is registered, that one is the implicit
   default.

If none resolves, ask the user — never guess.

"""
