Look up documentation in the offline corpus — the local stand-in for
web search and up-to-date library docs.

Use this when you would otherwise web-search a fact that lives in
product manuals, library/API docs, PDK files, or the internal wiki.
This environment is offline; `web_search` / `context7` are not
available.

## How to execute

Record usage (one line), then search:

```bash
mkdir -p .allmight/usage && date -Iseconds >> .allmight/usage/docs.log
smak search-all "<query>" --config personalities/<active>/database/docs/config.yaml --top-k 5 --json
```

## If nothing comes back

- Config file missing → the documentation index isn't built yet; tell
  the user, don't guess.
- Empty results → the corpus has no entry; say so and ask the user.
  **Never** fill the gap with a hallucinated answer.

The corpus reflects the last indexed snapshot — if the user needs
something newer, say so. Load the `docs` skill for the full procedure.
