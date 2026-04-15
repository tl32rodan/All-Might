Show the knowledge graph coverage and system health.

## How to execute

1. Scan all sidecar YAML files (`.*.sidecar.yaml`) across all paths
   defined in `config.yaml` indices.
2. For each sidecar, count symbols and check which have non-empty `intent`.
3. Calculate coverage: `enriched_symbols / total_symbols * 100`.
4. Read `enrichment/tracker.yaml` for historical data.
5. If `memory/config.yaml` exists (memory system enabled), also report:
   - Working memory: count words in `memory/working/MEMORY.md`
   - Episodic memory: count files in `memory/episodes/`
   - Semantic memory: count files in `memory/semantic/`

## What to report

```
Power Level: XX.X%
  source_code: XX.X% (N/M symbols enriched)
  tests:       XX.X% (N/M symbols enriched)
  Total relations: N

Memory (if enabled):
  Episodes: N total, M unconsolidated
  Facts: N total, avg confidence X.XX
```

## When to run

- After enrichment work to see progress
- Periodically to track coverage trends
- When the user asks "how healthy is the knowledge graph?"

## After checking status

- If coverage is low, prioritize `/enrich` on entry points
- If many episodes are unconsolidated, suggest `/consolidate`
- Update `enrichment/tracker.yaml` with the new snapshot
