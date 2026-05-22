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

Before running anything below, identify which personality should act
and substitute its name for ``<active>`` in every path.

1. **Explicit mention** — if the user named a personality (e.g.
   "for stdcell_owner ..."), use it.
2. **Conversation context** — if recent turns are clearly about
   one personality's domain (workspace name, role keywords from
   that personality's ``ROLE.md``), use it.
3. **Default** — read the leading callout at the top of
   ``MEMORY.md``::

       > **Default personality**: <name>

   Use ``<name>``. If the callout is absent and only one personality
   is registered (one row in ``MEMORY.md``'s project map), that one
   is the implicit default.

If none of these resolves, ask the user before proceeding — never
guess. The same routing applies to every step below.

"""
