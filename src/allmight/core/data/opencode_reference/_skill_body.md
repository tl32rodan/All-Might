# OpenCode reference skill

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
| `.opencode/agents/<name>.md` | `.opencode/reference/opencode/agents.md` — subagent vs primary, `prompt: "{file:...}"` |
| `.opencode/skills/<name>/SKILL.md` or `.opencode/commands/<name>.md` | `.opencode/reference/opencode/skills-commands.md` |
| `.opencode/opencode.json` or `.opencode/package.json` | `.opencode/reference/opencode/config.md` |

`.opencode/reference/opencode/README.md` is the index — start there
when unsure which file is closest.

## Pinned to OpenCode __OPENCODE_VERSION__

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
