# OpenCode skills and slash commands

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
