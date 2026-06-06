# Offline documentation lookup

> The offline stand-in for web search / up-to-date library docs.
> When you would normally reach for the web to check a library
> signature, a tool's flags, an API, or a manual, use this instead —
> it searches a local documentation corpus (manuals, library/API
> docs, PDK files, internal wiki) indexed as a `database` workspace.

## When to use

- "What's the signature / flags / options for `<library or tool>`?"
- "Look up the docs for `<X>`."
- Any moment you would otherwise web-search a fact that lives in
  product manuals, library docs, or the internal wiki.

This environment is offline. `web_search` and `context7` are not
available — this skill is their replacement for documentation.

## How to execute

Record usage (one line, then continue — this is telemetry, not
optional):

```bash
mkdir -p .allmight/usage && date -Iseconds >> .allmight/usage/docs.log
```

Search the documentation corpus:

```bash
smak search-all "<query>" --config personalities/<active>/database/docs/config.yaml --top-k 5 --json
```

Write the query as a natural-language description of what you need,
not a bare symbol name.

## If there are no results

Both cases below **must not** be answered from guesswork:

- **Config missing** — `personalities/<active>/database/docs/config.yaml`
  does not exist → the documentation index has not been built. Tell
  the user: "No offline documentation index is set up yet." Do not
  invent an answer.
- **Empty result set** — the corpus has no entry for this. Say so
  plainly and ask the user, rather than hallucinating.

## After searching

- Present results as "documentation" — never mention SMAK or vectors.
- The corpus reflects the **last indexed snapshot**. If the user needs
  something newer than that, say so and ask them.
