Rebuild the search corpus from source files.

## When to run

- **First time**: after `allmight init` to build the initial index
- **After significant changes**: new files added, major refactoring
- **After adding a corpus**: to populate the new index

You do NOT need to re-ingest after enrichment — sidecars are separate
from the search index.

## How to execute

Rebuild all corpora:
```bash
smak ingest --config config.yaml --json
```

Rebuild a specific corpus:
```bash
smak ingest --config config.yaml --index source_code --json
```

## What to expect

- The `./smak/<corpus_name>/` directory is populated with search index data
- `/search` will return results from the newly ingested files
- Ingestion may take a few minutes for large codebases

## Troubleshooting

- If `smak` is not found, ensure SMAK is installed and on PATH
- Check `smak health --config config.yaml --json` for diagnostics
- List available corpora: `smak describe --config config.yaml --json`
