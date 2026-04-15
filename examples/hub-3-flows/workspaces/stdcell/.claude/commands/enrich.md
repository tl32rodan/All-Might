Annotate a code symbol with intent and/or relations.

## How to execute

Set intent (what the symbol does and why):
```bash
smak enrich --config config.yaml --index source_code \
    --file <relative_path> --symbol "<SymbolName>" \
    --intent "Human-readable description of purpose"
```

Add a relation to another symbol:
```bash
smak enrich --config config.yaml --index source_code \
    --file <relative_path> --symbol "<SymbolName>" \
    --relation "<other_file>::<OtherSymbol>" --bidirectional
```

## When to enrich

- **Reading code**: symbol has no intent → add one
- **Discovering relationships**: two entities are related → link them
- **After modifying code**: existing intent may be stale → update it

## Priority

1. Entry points — main functions, API handlers, CLI commands
2. Complex logic — algorithms, state machines, non-obvious flow
3. Cross-cutting concerns — error handling, auth, logging
4. Frequently modified files (high git activity)

Skip auto-generated code, simple getters, and obvious boilerplate.

## What to expect

- A `.{filename}.sidecar.yaml` file is created/updated beside the source file
- The sidecar contains structured YAML with `symbols[].intent` and `symbols[].relations`
- Do NOT edit sidecar files by hand — always use `smak enrich`

## UID format

`<file_path>::<symbol_name>` — e.g., `src/auth.py::AuthHandler.validate`
- File path is relative to project root
- Dot notation for nested symbols: `ClassName.method_name`
- Wildcard `*` for entire file: `path/to/file.py::*`
- Never invent UIDs — use `/search` to discover valid ones
