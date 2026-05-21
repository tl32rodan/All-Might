# OpenCode plugins — events vs hooks

Plugins live at `.opencode/plugins/*.ts` and are auto-loaded by
OpenCode on startup. The most common mistakes when writing one are
(a) confusing the *event bus* with *named lifecycle hooks* and
(b) using the wrong injection path for prefix parts.

## File shape

Every plugin default-exports an async function. The runtime calls
that function once at load time with a context object and expects
back a dict whose keys are **either** named lifecycle hooks **or**
the special `event` global observer.

```ts
import type { Plugin } from "@opencode-ai/plugin"

const myPlugin: Plugin = async ({ client, project, directory, worktree, $ }) => {
  return {
    // Named lifecycle hook — called with typed input/output args.
    "chat.message": async (input: any, output: any) => {
      // mutate output.parts here
    },
    // Global bus observer — called for every event on the bus.
    event: async ({ event }) => {
      if (event.type === "session.created") { /* ... */ }
    },
  }
}
export default myPlugin
```

`input` to the plugin factory carries:

| field | what it is |
|-------|------------|
| `client` | the OpenCode SDK client |
| `project` | project metadata (name, root path) |
| `directory` | current working directory |
| `worktree` | git worktree (if applicable) |
| `$` | Bun shell helper for spawning commands |

## Named hooks (have input/output)

These are top-level keys on the returned object. Each one has a
**specific** input and output shape — read the
`@opencode-ai/plugin` types before assuming.

| Hook | Fires on | Notable contract |
|------|----------|------------------|
| `chat.message` | every chat turn | mutate `output.parts` to inject prefix parts (see below) |
| `experimental.session.compacting` | before context compaction runs | can short-circuit / observe the compaction trigger |
| `tool.execute.before` | before any tool call | can mutate the args dict |
| `tool.execute.after` | after a tool call | observe the result |

The names are stable but the input/output dicts have evolved. Treat
the type definitions as ground truth.

## Event observer (just observes the bus)

The `event` key is **not** a hook — it is a single async handler the
runtime calls for every event on the bus. Filter inside the handler:

```ts
event: async ({ event }) => {
  if (event.type === "session.created") { /* ... */ }
  if (event.type === "session.compacted") { /* ... */ }
  if (event.type === "session.deleted") { /* ... */ }
}
```

Common bus events: `session.created`, `session.compacted`,
`session.deleted`, `message.updated`. Anything *not* on the bus —
notably `chat.message` and `experimental.session.compacting` — is a
hook with its own top-level key, NOT an `event.type` to switch on.
Putting a hook name inside the event if-chain is the single most
frequent "my plugin doesn't fire" bug.

## Injecting a prefix part at chat.message

To prepend a synthetic system / context part to the next assistant
turn (e.g. inject `MEMORY.md` after compaction), `unshift` into
`output.parts`:

```ts
"chat.message": async (input: any, output: any) => {
  if (alreadyPrimed) return
  output.parts.unshift({
    type: "text",
    text: "<context>\n...\n</context>",
  })
}
```

Do NOT assign to a `msg.content` field — that shape predates the
parts API and is silently dropped.

## Spawning external commands

Use the Bun `$` helper that the plugin context provides:

```ts
const result = await $`smak ingest --config ${cfgPath}`.nothrow()
if (result.exitCode !== 0) { /* handle */ }
```

`.nothrow()` returns the exit code instead of throwing; the All-Might
plugins use it to avoid taking down the whole hook chain on a single
non-fatal failure.

## Heartbeats

Every All-Might-generated plugin emits a heartbeat marker on fire
(see `src/allmight/core/plugin_telemetry.py::TS_HEARTBEAT_SNIPPET`).
When writing a new plugin, inline the snippet and call
`emitHeartbeat("<plugin-name>", cwd)` inside every top-level handler
so `allmight plugin status` can see it. Skipping this is silent —
the plugin still works, but it shows up as `never fired` even when
healthy.
