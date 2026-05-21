# OpenCode reference (bundled snapshot)

A focused cheat-sheet for the OpenCode plugin / agent / skill / command
conventions that the All-Might initializer leans on. **Pinned to
OpenCode `__OPENCODE_VERSION__`** at the time the bundle was generated.

This is not a docs fork. It only covers the wrong-shape traps the
Python test suite cannot catch — the kind of thing that passes
`pytest` but breaks at runtime inside OpenCode's TypeScript host.

## When to read what

| File | Read when you are about to |
|------|----------------------------|
| `plugins.md` | author or modify `.opencode/plugins/*.ts` — events vs hooks, signatures, `output.parts.unshift` injection path |
| `agents.md` | author `.opencode/agents/<name>.md` — subagent vs primary, the `prompt: "{file:...}"` pointer convention |
| `skills-commands.md` | add a new slash command or skill — required frontmatter fields, `disable-model-invocation`, the `commands/` vs `skills/` split |
| `config.md` | touch `.opencode/opencode.json` or `.opencode/package.json` — schema fields All-Might depends on |

## When the cheat-sheet is silent

The cheat-sheet is intentionally a subset. If your task touches an API
that is not in here:

1. Read the `@opencode-ai/plugin` type definitions in the bundled
   `node_modules/` (the package is installed via `.opencode/package.json`).
2. Read a published plugin's source on GitHub — `oh-my-opencode` and
   `opencode-supermemory` are the canonical examples. Doc summaries
   hide signatures; real code does not.
3. As a last resort, fetch the official OpenCode docs over the network.
   Treat them as authoritative for shapes the cheat-sheet pre-dates.

## Version drift

We don't auto-check the installed OpenCode against `__OPENCODE_VERSION__`.
The 1.x line has been stable for the surfaces below, and a one-version
drift is unlikely to invalidate the cheat-sheet. If something here
contradicts what your OpenCode actually does, the running OpenCode
wins — and please open an issue so the bundle gets refreshed.
