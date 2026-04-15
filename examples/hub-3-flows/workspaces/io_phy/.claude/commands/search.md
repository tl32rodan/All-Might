Search the codebase by semantic meaning.

## How to execute

```bash
smak search "<query>" --config config.yaml --index source_code --top-k 5 --json
```

To search across all corpora at once:
```bash
smak search-all "<query>" --config config.yaml --top-k 3 --json
```

To look up a specific symbol by UID:
```bash
smak lookup "<file_path>::<symbol_name>" --config config.yaml --index source_code --json
```

## What to expect

JSON output with a `results` array. Each result contains:
- `id` — the matched chunk/symbol identifier
- `text` or `content` — the matched source code
- `score` — relevance score (0–1)
- `metadata` — file path, symbol name, etc.

## After searching

- If a result has a sidecar (`.{filename}.sidecar.yaml` beside it), read the
  sidecar to see its enriched intent and relations.
- If a result has NO sidecar or missing intent, consider enriching it with `/enrich`.
- Present results to the user in terms of "knowledge graph" — do not mention SMAK.
