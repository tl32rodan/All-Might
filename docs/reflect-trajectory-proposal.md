# Proposal — Make `/reflect` actually fire, and give it evidence

Status: draft for review (2026-07-18). Field report from internal
workstation deployment: `/reflect` never visibly runs — no
self-critique in transcripts, no runtime skills ever written by
step 6. This doc diagnoses why from the current source and proposes
the smallest fix set.

## 1. Diagnosis (grounded in code, not vibes)

### 1.1 `/reflect` has no trigger that arrives at an actionable moment

- The periodic nudge (`_reminder_nudge_text()` in
  `capabilities/memory/initializer.py`) mentions **only `/remember`**.
  `/reflect` is absent from the every-3rd-idle nudge entirely.
- The only automated `/reflect` trigger is `preCompactText()` inside
  `remember-trigger.ts`, delivered via the
  `experimental.session.compacting` hook — which pushes the text into
  `output.context`, i.e. **the compaction prompt read by the
  summarizer model, not the agent**. The instruction "you MUST run
  /reflect before history is condensed" is delivered at the exact
  moment compliance is impossible: compaction is already underway and
  the agent has no turn in which to act. At best the summary carries
  a paraphrase of the instruction.
- The `chat.message` pending-nudge pattern only delivers on the
  *next user turn*. "End of session" — the ideal `/reflect` moment
  named in the command body — has **no delivery mechanism at all**:
  by `session.deleted` there are no turns left.
- `experimental.*` hooks are exactly that; on the internal
  workstation's OpenCode build the compacting hook may not fire at
  all (see the V2-plugin-API risk note, `docs/daily-learning/
  2026-06-29.md`). Step 0 of any fix: run `allmight plugin status`
  on the workstation and read remember-trigger's fired/injected
  columns before trusting any of this plumbing.

Conclusion: "the agent never reflects" is **structural**, not (only)
a weak-internal-model problem. Nothing ever asks it to reflect at a
moment where reflecting is possible.

### 1.2 `/reflect`'s body audits memory files, not behaviour

Steps 1–7 of `templates/commands/reflect.md` are memory hygiene:
L1 accuracy, L2 additions, scope drift, cap triage. **No step says
"review what went wrong"** — tool-call errors, aborted turns, user
corrections are never mentioned. Step 6 (turn repetition into a
skill) depends on the agent recalling repeated procedures from its
own context — precisely the detail class a compaction summary drops
first. The observed "never writes a skill, never self-critiques"
is the expected output of this body.

### 1.3 The evidence infrastructure existed and was deleted

`trajectory-writer.ts` (removed 2026-06, commit b93a80e) captured
input / tool_calls-with-verdict / output and flushed a journal entry
per session. Verdict at the time: "No consumer ever read it. Bring
back when (if) an adaptive plugin actually needs it"
(`docs/plugin-observability.md`). `/reflect` reading trajectory
evidence **is that consumer**. Two caveats for a revival:

- The old schema is not reflect-shaped: it kept tool names + args +
  a coarse verdict, but **not error messages** and not
  aborts/interruptions — the two things a reflection actually needs.
- It buffered state in memory and flushed on compaction/deletion —
  the same unreliable flush timing as §1.1. A revival should append
  per-event instead.

## 2. What NOT to do

- **Do not feed a full session export to the agent.** OpenCode can
  produce one (plugin-side `client.session.messages({path:{id}})`;
  CLI-side `opencode export`), but `/reflect` typically runs when
  context is already tight — re-ingesting the whole transcript is a
  token explosion and re-introduces the salience problem it was
  meant to fix. Deterministic extraction belongs in the plugin;
  judgment belongs in the agent. (Same split as `/onboard` calling
  `allmight add`.)
- **No LLM-side "was this a user correction?" detection in the
  plugin.** Corrections are a judgment call; the plugin records
  facts (errors, aborts), the agent interprets them.
- **No structured telemetry platform.** Heartbeats stay touch-files
  per `docs/plugin-observability.md`. The evidence file below is a
  new artifact class (agent-consumed working data, like the journal),
  not telemetry.

## 3. Proposal

### 3.1 Evidence side — `session-evidence.ts` (revived writer, new shape)

A transparent plugin (no injection) that **appends on event**, no
flush step to mis-time:

- `tool.execute.after`: if the result is an error, append
  `{ts, tool, error: <first ~300 chars>}`.
- `session.error` / turn-abort events: append `{ts, kind: abort}`.
- Target: `.allmight/evidence/<yyyy-mm-dd>-<sid8>.yaml`, capped
  (e.g. 100 entries, then count-only) so it stays cheap to read.
- Registered in `PLUGIN_MANIFEST` with heartbeats (T1 + `.injected`
  T2 on each append). Claude Code mirror: `session_evidence.py` via
  PostToolUse (tool errors are visible there), abort capture marked
  OC-only if no CC equivalent exists — manifest decides, per the
  dual-platform invariant.
- On `session.created`, also write the current session's evidence
  path to `.allmight/evidence/current` so command bodies can find it
  without knowing the session ID.

Why not pull `client.session.messages()` once at reflect time
instead? It's more complete, but it depends on the SDK client shape
(V2 plugin API risk on the internal build) and on knowing the
session ID from inside a command body. Append-on-event is dumber and
survives crashes; the pull-based variant can be a later upgrade if
the internal build proves to expose `client` reliably.

### 3.2 Trigger side — deliver the ask when acting is possible

1. **Post-compaction, not pre-compaction.** Keep the compacting hook
   only to set a per-session flag; on the **first `chat.message`
   after compaction**, inject: "History was just compacted. The
   evidence file at `.allmight/evidence/...` survived — run
   /reflect now." This inverts the current dead-end: with evidence
   on disk, *after* compaction becomes a legitimate reflect moment
   because the details no longer live only in context.
2. **Escalating idle nudge.** The existing every-3rd-idle nudge
   checks the evidence file (cheap line count): ≥N error entries →
   the nudge upgrades from "/remember" to "run /reflect — N tool
   errors recorded this session." Deterministic condition, no new
   plugin.
3. `_reminder_nudge_text()` grows one line pointing at `/reflect`
   for the audit case, so the periodic surface mentions it at all.

### 3.3 Body side — `/reflect` Step 0

Prepend one step to `templates/commands/reflect.md`:

> **0. Review the evidence.** Read the newest file under
> `.allmight/evidence/` (path in `.allmight/evidence/current`). For
> each recorded error/abort: your mistake, an environment
> limitation, or a missing skill? Carry the answers into steps 5–6.

Step 6's repetition check then has a deterministic input (repeated
failing tool patterns) instead of relying on post-compaction recall.
Budget note: `tests/test_skill_body_size.py` pins the body size —
trim steps 1–4 wording or consciously bump the budget in the same
commit.

## 4. Open decisions (need maintainer confirmation)

1. Evidence file format: YAML (human-diffable, matches journal
   ethos) vs JSONL (append-safe, matches `trajectory_export.py`).
   Leaning JSONL for append atomicity.
2. Does the internal workstation's OpenCode build fire
   `session.idle` / `tool.execute.after` at all? → run
   `allmight plugin status` there first; if remember-trigger has
   never injected, fix delivery before adding new plumbing.
3. Should `/reflect` keep owning memory hygiene (steps 1–4) or
   should behaviour-reflection become its own command? Current lean:
   keep one command — the split rule in CLAUDE.md is about trigger
   context, and both halves share the same trigger.
4. Evidence retention: delete files >7 days old on session start, or
   leave to `/reflect` step 0 to prune after reading.

## 5. Out of scope here

The second field report — personalities used rigidly, the agent
never proposes creating/merging personalities as work shifts — is a
separate design conversation (likely a `/reflect` step or an
`/onboard` re-run trigger, plus suggestion-catalog surfacing). Not
addressed in this doc; noted so it isn't lost.
