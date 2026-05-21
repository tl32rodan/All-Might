# `.opencode/opencode.json` and `.opencode/package.json`

These two files are framework-level scaffold — `write_init_scaffold`
keeps them present and minimal. Setting things on them is fine; you
just need to know which fields All-Might depends on.

## `.opencode/opencode.json`

```json
{
  "$schema": "https://opencode.ai/config.json"
}
```

All-Might only sets `$schema` if absent. Everything else is yours.

| field | All-Might cares? | notes |
|-------|------------------|-------|
| `$schema` | Yes, sets if missing | Points at the canonical config schema so editors can complete. Internal mirrors are fine — `setdefault` won't overwrite. |
| `model`, `provider` | No | User-owned. |
| `tools`, `agents`, anything else | No | User-owned. |

## `.opencode/package.json`

```json
{
  "private": true,
  "dependencies": {
    "@opencode-ai/plugin": "latest"
  }
}
```

Bundled so OpenCode's embedded Bun runtime can resolve plugin imports
(`import type { Plugin } from "@opencode-ai/plugin"`). On re-init,
`@opencode-ai/plugin` is `setdefault`-ed into the dependencies map;
other deps you add survive untouched.

## `.opencode/plugins/` vs `.opencode/skills/` vs `.opencode/commands/`

These three sibling directories carry the three runtime surfaces:

| Directory | Loaded as | Fires on |
|-----------|-----------|----------|
| `plugins/` | TypeScript plugin (Bun) | Plugin lifecycle (events + hooks) |
| `skills/<name>/SKILL.md` | Markdown context fragment | Auto-load based on description match |
| `commands/<name>.md` | Markdown prompt template | User types `/<name>` |

They do not interact at load time — adding one does not require
touching the others. (All-Might often ships matching trios for a
single feature; that is a convention, not a runtime requirement.)
