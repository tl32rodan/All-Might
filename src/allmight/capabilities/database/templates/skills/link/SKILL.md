# Link code and docs (build the knowledge mesh)

> Connect a code symbol to the documentation that explains it — and
> back — so a later search of one surfaces the other. This is how the
> offline knowledge base becomes navigable when internal code has no
> formal API docs: you build the links as you discover them.

## When to use

When you notice a doc/manual section explains a specific code symbol
(or vice versa) and they are not yet linked — often while answering via
`project_knowledge_search`. Build the link so the next search inherits it.

## How to execute

Relations are written into SMAK **sidecars** (metadata beside the
source) — never into the code itself.

```bash
smak enrich-symbol \
  --config personalities/<active>/database/<workspace>/config.yaml \
  --file <code_file> --symbol <Symbol.name> \
  --relation "<doc_path>::*" --bidirectional --json
```

- `<doc_path>::*` is the doc node's UID — a documentation file is a
  **file-level** node, so its symbol is `*`.
- `--bidirectional` writes the reverse link too, so searching the doc
  also surfaces the code.
- Add `--intent "<one line>"` to record what the symbol is for.

Verify a relation target exists first with `smak lookup "<uid>"` if unsure.

## After linking

If the sidecar is new, run `smak ingest` on the workspace so the link is
searchable. Tell the user what you linked — keep it to one line.
