# Plugin Observability & Reduction Plan

Decisions captured from the design session that produced this PR. Future
contributors should read this before adding new plugins or proposing
"smarter" observability infrastructure.

## Why this exists

All-Might emits 8 OpenCode plugins and 4 mirroring Claude Code hooks.
Users could not tell whether any of them were actually firing — the
plugins write to disk silently (`usage.log`, `trajectories/`,
`memory-history/.git`) or inject into the agent's context silently
(`memory-load`, `role-load`, `reflection`). The only plugin with
*evidence* of firing was `remember-trigger`, because its injected
prompt asks the agent to think about `/remember` and that thinking
sometimes surfaces.

Without visibility:

- We cannot tell a broken plugin from a working-but-quiet one.
- We cannot make evidence-based decisions about which plugins to keep,
  which to drop, and which to upgrade.
- Tier-6 "cross-turn learning" plugins (adaptive reflection, lesson
  recall, failure recorders) would be built on the assumption that the
  underlying observation plugins fire correctly. That assumption is
  currently untested.

## What we built: touch-file heartbeats

Every plugin / hook touches a marker file when it fires:

```
.allmight/plugins/heartbeats/oc/<plugin-basename>   # OpenCode .ts
.allmight/plugins/heartbeats/cc/<hook-basename>     # Claude Code .py
```

`allmight plugin status` lists each surface, shows the mtime of each
marker as "fired N ago", and explicitly lists known plugins that have
never fired.

Deliberately simple:

- **No JSONL, no rotation, no schema.** mtime is the only datum. The
  question is "did it fire?" — mtime answers it.
- **No per-event detail.** A plugin that handles `chat.message` +
  `session.deleted` only gets one marker per surface. If we ever need
  per-event breakdowns we'll know it because someone has a concrete
  use for the data.
- **No structured logger, no SDK.** Each plugin inlines ~10 lines of
  touch logic. Duplication is fine for code this trivial; the
  alternative (cross-plugin helper module) couples 8 plugins to a
  shared file.
- **Failures swallowed.** A plugin must never throw because telemetry
  broke. Worst case is the heartbeat doesn't appear and status shows
  "never fired" — which is still useful.

The point is to *enable evidence-gathering*, not to build an
observability platform.

## Plugin reduction plan (data-driven, future work)

Audit of the existing 8 plugins. The verdict column says what we
*intend* to do once heartbeat data justifies it. None of the actions
in this column are taken in this PR — we ship observability first,
then gather a week of data, then act.

| Plugin              | Current fire rate          | Verdict (post-data) |
|---------------------|----------------------------|----------------------|
| `memory-load`       | every `chat.message`       | **Reduce fire rate.** Probably SessionStart + post-compaction only. Re-injecting MEMORY.md on every turn is wasteful. |
| `role-load`         | every `chat.message`       | **Probably delete.** Redundant with `AGENTS.md`, which is already composed from every `ROLE.md`. |
| `reflection`        | every user prompt          | **Wait for data.** Just shipped. If status shows it fires constantly with no visible behaviour change, drop it or upgrade to adaptive (`§5.1` of the design plan). |
| `remember-trigger`  | every Nth idle, compaction | **Keep.** Only plugin with prior evidence of working. |
| `usage-logger`      | every tool call            | **Probably delete.** Nobody reads `usage.log`. OpenCode / Claude transcripts already log tool calls. |
| `todo-curator`      | TodoWrite calls + session  | **Keep, verify.** Cross-session TODO persistence has real value; confirm via status that it fires at all. |
| `trajectory-writer` | every tool before/after    | **Probably delete.** §4 of the design plan confirms no consumer reads it. Re-derivable from editor transcripts. Bring back when (if) a `Tier-6` adaptive plugin actually needs it. |
| `memory-history`    | every `chat.message`       | **Change fire condition.** Should be event-driven (after `/remember`, after memory writes) instead of every turn. Most turns don't touch memory. |

Net effect, if the data confirms: 8 plugins → 5 (drop 3, change fire
rate for 2, keep 3).

## Why "delete a plugin" needs evidence

Several of these plugins look obviously useless on inspection. They
are not deleted in this PR for two reasons:

1. **`reflection.ts` just shipped.** Killing it before observing
   whether it has any effect would discard a deliberate experiment.
2. **`usage-logger.ts` *looks* unused but might have private uses.**
   Maybe the user greps it occasionally. Heartbeat data will tell us
   the fire rate; field reports will tell us whether anyone reads it.

The general principle: **observability is the cheaper move than
reduction**, because adding it back later is harder than deleting code
later. Add the eyes first, then trim what they show is dead.

## Non-goals (deliberately deferred)

The plan that produced this PR considered, and rejected for now:

- **Structured JSONL heartbeats.** Touch-file is enough for the
  current question. If we ever want fire-rate histograms or per-hook
  detail, that's the upgrade path. Don't pre-emptively build it.
- **`plugin doctor` health check.** Useful eventually but requires
  per-plugin smoke harnesses. Heartbeats answer "did it fire"; doctor
  would answer "would it work if invoked". Different question, can
  wait.
- **`Stop`-hook per-turn summary lines.** Most users won't want every
  turn to end with `"[allmight] 3 plugins fired this turn"`. Defer
  until someone asks for it.
- **Verbose / debug mode env var.** Touch-file + status CLI covers
  the "did it fire" question without needing extra modes. If verbose
  becomes useful, add it then.
- **Dashboard / TUI.** Speculative.

## Dual-platform contract

Heartbeats are emitted from **both** OpenCode plugins (via a
TypeScript snippet) and Claude Code hooks (via a Python snippet).
Both write to the same `.allmight/plugins/heartbeats/<surface>/`
tree, with `<surface>` being `oc` or `cc`. `plugin status` reports
each surface separately so a plugin that fires under one editor but
not the other is visible immediately.

The TS and Python snippets are kept in `core/plugin_telemetry.py` as
string constants and inlined into every plugin / hook by the
generators. **Changes to one snippet require updating the other** —
the same dual-platform rule that applies to memory-load, role-load,
reflection, and memory-history (see project `CLAUDE.md`, "Editor
Compatibility").
