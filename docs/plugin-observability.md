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

## T1 / T2 / T3 — three different questions (2026-06)

Heartbeat freshness alone misled a real deployment: super-learner's
markers refreshed on every tick while `/remember`, `/reflect`, and
skill creation never fired once in 16 cycles (see
`docs/concentration-review-2026-06.md`). The fix is to measure three
strictly-ordered observables, all still touch-file simple:

- **T1 `fired`** — handler entry. `emitHeartbeat("<name>")` /
  `_hb("<name>")` as the first line of every handler. Proves only
  that events arrive.
- **T2 `injected`** — content delivered. `<name>.injected` touched
  only on the actual injection / snapshot path. `fired` fresh +
  `injected` `—` means the handler's condition never held (e.g. a
  nudge threshold unreachable in one-shot sessions).
  `memory-history`'s T2 is emitted by `allmight memory snapshot`
  when a commit lands, not by the plugin.
- **T3 outcomes** — durable artifacts. The `Outcomes:` footer of
  `allmight plugin status` (memory-history commit count, journal
  entry count, MEMORY.md placeholder check) answers whether the
  *agent* acted on what was injected. This is the only metric that
  would have caught the super-learner gap.

## Plugin reduction plan (2026-06: phase 1 executed)

Audit of the plugin set. The first two verdicts have been **executed**
— the super-learner deployment supplied the evidence the original
plan was waiting for (16 cycles, zero readers of either output).

| Plugin              | Current fire rate          | Verdict |
|---------------------|----------------------------|----------------------|
| `memory-load`       | every `chat.message`       | **Reduce fire rate.** Probably SessionStart + post-compaction only. Re-injecting MEMORY.md on every turn is wasteful. Deferred — next round. |
| `role-load`         | every `chat.message`       | **Probably delete.** Redundant with `AGENTS.md`, which is already composed from every `ROLE.md`. Deferred — next round. |
| `feedback-check`    | every user prompt          | **Renamed from `reflection` (2026-06).** The old name collided with `/reflect` (the periodic memory audit) and misled users into reading it as a self-reflection engine. Behaviour unchanged; watch T2/T3 before further calls. |
| `remember-trigger`  | every Nth idle, compaction | **Keep.** Only plugin with prior evidence of working. Note: structurally dead in one-shot scheduled sessions — episodic duties belong in loop-skill steps there. |
| `usage-logger`      | —                          | **Deleted (2026-06).** Nobody read `usage.log` (super-learner: 0 bytes after 16 cycles). Re-init prunes the stale `.ts`. Manual log instructions in `/remember`/`/recall` remain (other writers exist). |
| `todo-curator`      | TodoWrite calls + session  | **Keep, verify.** Cross-session TODO persistence has real value; confirm via status that it fires at all. |
| `trajectory-writer` | —                          | **Deleted (2026-06).** No consumer ever read it. Re-init prunes the stale `.ts`. Bring back when (if) a `Tier-6` adaptive plugin actually needs it. |
| `memory-history`    | every `chat.message`       | **Change fire condition.** Should be event-driven (after `/remember`, after memory writes) instead of every turn. Deferred — next round. |

Current set: 7 plugins. Remaining intended cuts (role-load,
fire-rate reductions) wait on T2/T3 data from the new columns.

### Stale-plugin pruning

Deleting (or renaming) a plugin in the framework must not leave the
old generated `.ts` running forever in deployed projects.
`prune_stale_plugins` (`core/plugin_telemetry.py`) runs on every
`allmight init`: it deletes `.opencode/plugins/*.ts` and staged
`.allmight/templates/*.ts` whose basename is no longer in
`KNOWN_OPENCODE_PLUGINS` **and** whose head carries the All-Might TS
marker. User-authored plugins (no marker) are never touched. The
Claude side handles renames via `_LEGACY_HOOK_SCRIPTS` in
`core/claude_bridge.py` (settings.json entry stripped, marker'd
script deleted).

## Why "delete a plugin" needs evidence

The general principle: **observability is the cheaper move than
reduction**, because adding it back later is harder than deleting code
later. Add the eyes first, then trim what they show is dead. The
2026-06 deletions followed exactly this path — the deployment data
arrived, then the cut.

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
