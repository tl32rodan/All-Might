"""All-Might Agent Memory System — L1 / L2 / L3.

Three-tier persistent memory organized like cache/RAM/disk:

- **L1 — MEMORY.md** (project root): Always in context via hook.
  Project map, user preferences, active goals, key facts.
- **L2 — understanding/** (per-corpus): Loaded when entering a
  workspace. Source code roadmap, debug SOP, patterns.
- **L3 — journal/** (append-only): Searchable via SMAK vector index.
  Historical observations and learned knowledge.
"""
