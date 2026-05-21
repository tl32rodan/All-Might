"""Bundled OpenCode reference — framework-level, not capability-owned.

We frequently generate ``.opencode/plugins/*.ts``, ``.opencode/agents/
<name>.md`` and slash-command files. The Python test suite verifies
**what strings we wrote**, not whether the result is a well-shaped
OpenCode artefact (see *Discipline When Generating Third-Party
Integrations* in CLAUDE.md). Agents that author or modify those files
need an offline reminder of the API conventions; this module bundles
that reminder.

Architecture:

* The reference is a small set of markdown cheat-sheets under
  ``.opencode/reference/opencode/`` — NOT a fork of upstream docs.
  Each file focuses on the shapes the test suite cannot pin (event
  vs hook distinction, subagent vs primary, ``output.parts.unshift``
  injection path).
* A companion skill at ``.opencode/skills/opencode-ref/SKILL.md``
  exists so the agent has an autoload-discoverable pointer back at
  the cheat-sheets when a relevant task arises.
* A short section gets stitched into ``AGENTS.md`` by
  ``_AGENTS_MD_FRAMEWORK_PRIMER`` so the pointer is visible from the
  highest-level surface, not buried in a skill that may not load.

This module is framework-level (called from
``personalities.write_init_scaffold``) and therefore does not live
under ``capabilities/`` — no personality owns it, no per-personality
data dir is created. Re-init refreshes the markered files via
``write_guarded``; user-edited (marker-removed) versions are
preserved exactly like ``role-load.ts`` / ``reflection.ts``.
"""

from __future__ import annotations

from pathlib import Path

from .markers import ALLMIGHT_MARKER_MD
from .safe_write import write_guarded
from .skill_io import install_skill


OPENCODE_VERSION = "1.14.28"
"""The upstream OpenCode version the cheat-sheets were authored against.

Surfaced verbatim in the bundled ``README.md`` so a reader can decide
whether to cross-check upstream when something looks off. We do not
runtime-check the installed OpenCode against this — the cheat-sheets
focus on shapes that have been stable across the 1.x line, and a
stale snapshot is still a better starting point than guessing.
"""


_REFERENCE_README = f"""# OpenCode reference (bundled snapshot)

A focused cheat-sheet for the OpenCode plugin / agent / skill / command
conventions that the All-Might initializer leans on. **Pinned to
OpenCode `{OPENCODE_VERSION}`** at the time the bundle was generated.

This is not a docs fork. It only covers the wrong-shape traps the
Python test suite cannot catch — the kind of thing that passes
`pytest` but breaks at runtime inside OpenCode's TypeScript host.

## When to read what

| File | Read when you are about to |
|------|----------------------------|
| `plugins.md` | author or modify `.opencode/plugins/*.ts` — events vs hooks, signatures, `output.parts.unshift` injection path |
| `agents.md` | author `.opencode/agents/<name>.md` — subagent vs primary, the `prompt: "{{file:...}}"` pointer convention |
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

We don't auto-check the installed OpenCode against `{OPENCODE_VERSION}`.
The 1.x line has been stable for the surfaces below, and a one-version
drift is unlikely to invalidate the cheat-sheet. If something here
contradicts what your OpenCode actually does, the running OpenCode
wins — and please open an issue so the bundle gets refreshed.
"""


_REFERENCE_PLUGINS = """# OpenCode plugins — events vs hooks

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
    text: "<context>\\n...\\n</context>",
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
"""


_REFERENCE_AGENTS = """# OpenCode subagents — `.opencode/agents/<name>.md`

Each personality is exposed to OpenCode as a subagent so the user can
`@<name>` mention it without Tab-switching out of the current session.
All-Might generates these files as thin pointers — `ROLE.md` remains
the source of truth.

## File shape (canonical pointer form)

```yaml
---
description: "<role summary, one line>"
mode: subagent
prompt: "{file:../personalities/<name>/ROLE.md}"
---
<!-- all-might generated -->
```

The `{file:...}` syntax is OpenCode's prompt-substitution: the file
contents are inlined when the agent is invoked. Editing
`personalities/<name>/ROLE.md` updates the subagent's behaviour
without re-running `allmight init`.

## `mode:` — subagent vs primary

| mode | Invocation | When the user is in it |
|------|------------|------------------------|
| `subagent` | `@<name>` from any conversation; runs one task and returns | The main conversation is preserved |
| `primary` | `Tab`-switch to it at the session selector | The whole session *becomes* that agent |

All-Might emits `subagent` because the design philosophy is "no
default personality switching" — the user should not be inside a
specific personality's frame by default. Subagent invocation is a
single mention; primary switching changes the entire session.

## Directory naming

`.opencode/agents/` (plural) is canonical. Singular `agent/` is
accepted by OpenCode for backwards compatibility but should not be
used in new code.

## What NOT to put in the agent file

* Long behaviour specs — those go in `ROLE.md`, the file the
  `prompt: {file:...}` points at. The agent file is a pointer.
* Tools list — All-Might subagents inherit tools from the parent
  session. Explicit `tools:` entries are only needed when you want
  to restrict the subagent's tool surface.
* Frontmatter without `mode:` — OpenCode defaults to `primary` if
  `mode:` is absent, which is the wrong default for All-Might.
"""


_REFERENCE_SKILLS_COMMANDS = """# OpenCode skills and slash commands

Two distinct surfaces share the `.opencode/` namespace. They look
similar but trigger differently.

## Skills — `.opencode/skills/<name>/SKILL.md`

A skill is a markdown file the agent may pull into context when the
description suggests it is relevant to the current task. Auto-load
is gated by the `description:` field.

```yaml
---
name: opencode-ref
description: |
  Use when about to author or modify any file under .opencode/ —
  plugins, agents, slash commands. Points at the bundled OpenCode
  cheat-sheets at .opencode/reference/opencode/.
---
<!-- all-might generated -->

# Body...
```

Required frontmatter:

| field | purpose |
|-------|---------|
| `name` | matches the directory; how the agent refers to the skill |
| `description` | the auto-load trigger; write it as a "use when …" rule |

Optional:

| field | purpose |
|-------|---------|
| `disable-model-invocation: true` | the skill is callable by the user / commands but the model will not autoload it. Useful for skills whose body would crowd context unhelpfully. |

The directory layout is `<skills-dir>/<name>/SKILL.md`. Putting the
SKILL.md at `<skills-dir>/<name>.md` (flat) is **not** discovered.

## Slash commands — `.opencode/commands/<name>.md`

A slash command is a markdown body the user fires with `/<name>`.
The body is the prompt the agent runs.

```md
<!-- all-might generated -->

# /<name>

<command body — instructions to the agent. ROUTING_PREAMBLE goes
here for any command that acts on a specific personality.>
```

No frontmatter is required; OpenCode discovers commands by filename.
A command and a skill can share a name — All-Might uses this to ship
`/remember` as both a command (the user-invoked entry point) and a
skill (auto-loaded for context).

## When to ship which

| Surface | When | Trigger |
|---------|------|---------|
| Skill alone | Background know-how the agent needs only sometimes. | Auto-loaded by description match. |
| Command alone | User-facing action with no extended context. | User types `/<name>`. |
| Skill + command | A multi-step operation the user invokes directly AND the agent should understand without being asked. | Both. The `install_skill` helper writes the pair in one call. |
"""


_REFERENCE_CONFIG = """# `.opencode/opencode.json` and `.opencode/package.json`

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
"""


_REFERENCE_FILES: dict[str, str] = {
    "README.md": _REFERENCE_README,
    "plugins.md": _REFERENCE_PLUGINS,
    "agents.md": _REFERENCE_AGENTS,
    "skills-commands.md": _REFERENCE_SKILLS_COMMANDS,
    "config.md": _REFERENCE_CONFIG,
}


_OPENCODE_REF_SKILL_DESCRIPTION = (
    "Use BEFORE authoring or modifying any file under `.opencode/` "
    "(plugins, agents, slash commands, opencode.json). Points at the "
    "bundled OpenCode cheat-sheets at `.opencode/reference/opencode/`."
)


_OPENCODE_REF_SKILL_BODY = f"""# OpenCode reference skill

You are about to touch a file under `.opencode/` — a plugin, a
subagent, a slash command, or `opencode.json` itself. The All-Might
Python test suite cannot catch wrong-shape calls in the resulting
TypeScript / YAML, so a runtime-broken artefact can ship while
`pytest` is fully green.

## Before you write, read

The cheat-sheets at `.opencode/reference/opencode/` cover the
shapes the test suite is blind to. Pick by task:

| About to touch | Read first |
|----------------|------------|
| `.opencode/plugins/*.ts` | `.opencode/reference/opencode/plugins.md` — events vs hooks, `output.parts.unshift`, the Bun `$` helper |
| `.opencode/agents/<name>.md` | `.opencode/reference/opencode/agents.md` — subagent vs primary, `prompt: "{{file:...}}"` |
| `.opencode/skills/<name>/SKILL.md` or `.opencode/commands/<name>.md` | `.opencode/reference/opencode/skills-commands.md` |
| `.opencode/opencode.json` or `.opencode/package.json` | `.opencode/reference/opencode/config.md` |

`.opencode/reference/opencode/README.md` is the index — start there
when unsure which file is closest.

## Pinned to OpenCode {OPENCODE_VERSION}

The bundle is a snapshot, not a docs fork. If the running OpenCode
disagrees with the cheat-sheet, the running OpenCode wins. For
APIs the cheat-sheet does not cover:

1. Read the `@opencode-ai/plugin` types under `.opencode/node_modules/`.
2. Read a real plugin on GitHub (`oh-my-opencode`,
   `opencode-supermemory`) before guessing from doc summaries.
3. Only then, fetch the official docs over the network.

## Heartbeats and dual-platform invariant

If the file you are writing is a plugin, two more things apply:

* Inline the heartbeat snippet from `core/plugin_telemetry.py` so
  `allmight plugin status` can see it fire.
* If the behaviour is also expected on Claude Code, update the matching
  `.claude/hooks/*.py` mirror in the same commit. The shared contract
  lives in `PLUGIN_MANIFEST` (`core/plugin_telemetry.py`); failing to
  mirror creates silent drift between editors. See CLAUDE.md
  → *Editor Compatibility* for the full rule set.
"""


def write_opencode_reference(project_root: Path) -> None:
    """Write the OpenCode reference bundle + the `/opencode-ref` skill.

    Framework-level — called from
    :func:`allmight.core.personalities.write_init_scaffold`. Both fresh
    init and re-init invoke this; ``write_guarded`` preserves files
    the user has deliberately un-markered. Marker-kept files refresh
    in place — same trade-off as ``role-load.ts`` / ``reflection.ts``
    and the other framework scaffold files.

    No staging path: this is a "reminder" bundle whose content is
    framework-owned, not a per-project artefact. If we add new
    upstream content, every project picks it up at next ``allmight
    init`` without `/sync` ceremony. Users who want a private copy
    just clear the marker on the affected file.
    """
    ref_dir = project_root / ".opencode" / "reference" / "opencode"
    ref_dir.mkdir(parents=True, exist_ok=True)

    for filename, body in _REFERENCE_FILES.items():
        write_guarded(ref_dir / filename, body, ALLMIGHT_MARKER_MD)

    install_skill(
        project_root,
        name="opencode-ref",
        description=_OPENCODE_REF_SKILL_DESCRIPTION,
        skill_body=_OPENCODE_REF_SKILL_BODY,
    )
