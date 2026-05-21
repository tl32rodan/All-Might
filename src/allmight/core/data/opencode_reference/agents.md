# OpenCode subagents — `.opencode/agents/<name>.md`

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
