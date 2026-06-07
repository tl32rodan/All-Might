Build the knowledge mesh — link a code symbol to the documentation that
explains it (and back), so searching one surfaces the other.

Use this when you discover a doc section that explains a code symbol (or
vice versa) and they are not yet connected. Links live in SMAK sidecars
(metadata beside the source); the code itself is never edited.

## How to execute

```bash
smak enrich-symbol \
  --config personalities/<active>/database/<workspace>/config.yaml \
  --file <code_file> --symbol <Symbol.name> \
  --relation "<doc_path>::*" --bidirectional --json
```

`<doc_path>::*` is the doc node's UID (a doc file is a file-level node,
symbol `*`). `--bidirectional` writes the reverse link. Add
`--intent "<one line>"` to record the symbol's purpose.

Load the `link` skill for the full procedure (UID lookup, re-ingest).
