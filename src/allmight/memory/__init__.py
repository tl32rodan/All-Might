"""All-Might Agent Memory System.

Three-layer memory architecture inspired by Hermes Agent, MemGPT/Letta,
and cognitive science (Ebbinghaus, ACT-R):

- **Working Memory** (Layer 1): Always in context via ``MEMORY.md``.
  User model, environment facts, pinned memories.  Token-budgeted.
- **Episodic Memory** (Layer 2): Append-only session records in
  ``memory/episodes/``.  Indexed for semantic search.
- **Semantic Memory** (Layer 3): Consolidated facts in
  ``memory/semantic/``.  Versioned with supersession chains,
  conflict resolution, and Ebbinghaus decay scoring.

The memory system cross-pollinates with All-Might's existing
knowledge graph (sidecars + Panorama) — episodic observations
can seed sidecar enrichment, and graph structure boosts retrieval.
"""
