# Proposal — Per-turn micro-reflection notes + consolidated `/reflect`

Status: draft v2 (2026-07-18). v1 diagnosed why `/reflect` never
fires; v2 incorporates the maintainer's design: **jot per turn,
consolidate rarely** — deep reflection must not run often enough to
derail the actual task.

## 1. Diagnosis (unchanged from v1, condensed)

1. **No actionable trigger.** The only automated `/reflect` ask is
   injected via `experimental.session.compacting` into
   `output.context` — the compaction prompt read by the *summarizer*,
   not the agent. There is no agent turn between "about to compact"
   and "compacted", so the instruction lands at a moment where
   compliance is impossible. The periodic idle nudge
   (`_reminder_nudge_text()`) never mentions `/reflect` at all, and
   "end of session" has no delivery mechanism (nudges deliver on the
   *next* user turn; at `session.deleted` there is none).
2. **`/reflect`'s body audits memory files, not behaviour.** No step
   reviews tool failures, dead-ends, or user corrections; step 6
   (repetition → skill) relies on post-compaction recall of exactly
   the details summaries drop first.
3. **The per-turn cue already exists but evaporates.**
   `feedback-check.ts` injects, every `chat.message`, a prompt asking
   the agent to do a 2-3 sentence retrospective if the user
   redirected it / it retried into a dead-end / an assumption broke
   (`FEEDBACK_CHECK_PROMPT`, `core/personalities.py`). The output
   goes into the chat and is lost — nothing persists it, so nothing
   downstream can consolidate it.
4. **Evidence plumbing existed and was cut.** `trajectory-writer.ts`
   (deleted 2026-06, "no consumer") captured tool calls but not
   error messages or aborts, and buffered in memory with the same
   broken flush timing as (1).

Field observation ("agent never self-critiques, never writes a
skill") is the expected output of this structure — not primarily a
weak-model problem.

## 2. Design principle (maintainer-set)

- **Per-turn: jot, don't dwell.** One-line note when the previous
  turn shows friction; no deep analysis mid-task. Deep reflection
  that fires often derails the task it is reflecting on.
- **Rarely: consolidate.** On `/reflect` (manual or nudged) — and
  only then — read the accumulated notes and decide the expensive
  things: update `AGENTS.md`? write a skill? update L2? prune.
- **Never feed a full transcript export to the agent** (token
  explosion; `/reflect` runs when context is tightest). Plugins
  capture deterministically; the agent judges from compact notes.

## 3. Proposal

### 3.1 Layer 1 — per-turn micro-reflection note (agent-written)

Extend `FEEDBACK_CHECK_PROMPT` (single source, both surfaces): keep
the existing two triggers —

- repeated tool use without the expected result (including *different
  commands* aiming at the same goal — not just literal retries);
- the user's message answers/corrects what the previous turn did;

— but replace "reflect in 2-3 sentences" with **"append ONE line to
`.allmight/feedback/notes.md` and move on"**:

```
- 2026-07-18 turn~12 [tool-deadend] 3x grep variants for X found nothing; answer was in docs/plan.md
- 2026-07-18 turn~15 [user-correction] proposed per-personality commands; user: globals only
```

Line format: date, rough turn, tag (`tool-deadend` /
`user-correction` / `assumption-broke`), one sentence. Nothing
happened → write nothing. This is *cheaper* in-chat than today's
2-3-sentence retrospective, and it survives compaction because it
is on disk.

Location rationale: not `journal/` (L3 is per-personality,
ingest-indexed, frontmatter-schema'd — heavyweight for scratch);
`.allmight/feedback/` is project-level scratch, plain markdown,
consumed and pruned by `/reflect`. "Versatile" = no schema beyond
the one-line convention.

### 3.2 Layer 2 — deterministic evidence (plugin-written backstop)

The internal model may ignore the cue (today's nudges already
"sometimes surface"). Backstop: a small `session-evidence` plugin
appends hard signals per event — tool result errors (first ~300
chars), aborts — to `.allmight/feedback/auto-<date>-<sid8>.jsonl`.
Append-on-event; no flush step to mis-time. Registered in
`PLUGIN_MANIFEST` with T1/T2 heartbeats; Claude Code mirror via
PostToolUse where capabilities allow. Layer 2 catches what Layer 1
sleeps through; Layer 1 catches what Layer 2 can't see (a
"successful" tool call that didn't achieve the goal; user
corrections).

### 3.3 Consolidation — `/reflect` reads notes, targets AGENTS.md/skills

New Step 0 in `templates/commands/reflect.md`:

> **0. Review friction notes.** Read `.allmight/feedback/notes.md`
> and the newest `auto-*.jsonl`. For each entry decide: my mistake /
> environment limitation / missing knowledge. Then:
> - a recurring *procedure* gap → write a skill (existing step 6);
> - a wrong *project-level fact the agent keeps assuming* → fix the
>   relevant `ROLE.md` (AGENTS.md recomposes via `allmight compose`)
>   or `MEMORY.md`/L2 per scope;
> - one-off noise → drop it.
> Prune consolidated lines from `notes.md` (leave unresolved ones).

AGENTS.md note: per the compose invariant, the agent edits
`personalities/<p>/ROLE.md` (source of truth) and runs
`allmight compose` — never AGENTS.md directly.

Body size is pinned by `tests/test_skill_body_size.py`; the same
commit must trim or consciously bump the budget.

### 3.4 Consolidation triggers

1. **Manual `/reflect`** — unchanged.
2. **Escalating idle nudge** — when `notes.md` + `auto-*.jsonl`
   exceed ~N entries, the existing every-3rd-idle nudge upgrades
   from "/remember" to "run /reflect — N friction notes pending".
   Deterministic file check inside `remember-trigger.ts`.
3. **Compaction-adjacent** — see §4; the honest options are limited.

## 4. Why consolidation cannot run "right before" compaction

The worry — "won't post-compaction reflection lose the mistakes?" —
is correct **when mistakes live only in the context window**. This
design moves capture to per-turn disk writes precisely so that
compaction can no longer destroy evidence: the summarizer drops
context, not files.

Mechanically, OpenCode offers no agent-actionable pre-compaction
moment. `experimental.session.compacting` fires once compaction has
*started*, and anything a plugin adds there goes into the
summarizer's prompt — the agent never gets a turn in between. Nor is
"the turn before compaction will trigger" predictable. So:

- **Capture** happens per turn, when the detail is fresh and cheap —
  strictly earlier and richer than any pre-compaction batch job
  could be. Nothing waits for compaction, so nothing is lost to it.
- **Consolidation** is timing-insensitive (it reads disk) and runs
  at the first *possible* moment near compaction: the compacting
  hook sets a flag; the first post-compaction `chat.message` injects
  "history was compacted; friction notes survived on disk — run
  /reflect if ≥N pending". Post-compaction is not the preferred
  moment; it is the only real one, and per-turn capture makes it
  lossless.

The v1 idea of using compaction as the *primary* reflect trigger is
demoted: with per-turn capture, compaction is just one more
"pending notes" checkpoint.

## 5. Open decisions

1. `notes.md` single rolling file vs per-day files. Lean: single
   file, `/reflect` prunes; simplest for the cue to state.
2. Threshold N for the nudge upgrade (lean: 5 combined entries).
3. Should Layer 2 ship in the same change, or land Layer 1 first and
   watch heartbeats/`notes.md` on the workstation to see if the cue
   alone suffices? Lean: Layer 1 + nudge upgrade first (smallest
   change: one prompt constant, one command body, one nudge
   condition), Layer 2 second.
4. Workstation pre-check unchanged from v1: run
   `allmight plugin status`; if `feedback-check` shows `injected: —`
   the cue never reaches the model and Layer 1 is moot until
   delivery is fixed.

## 6. Out of scope

Personality rigidity (agent never proposes new/merged personalities
as work shifts) — separate conversation. Note the hook: `/reflect`
step 0's "missing knowledge" bucket is a natural place to also ask
"does recent work still fit the installed personalities?" → route to
`/onboard` re-run. Not designed here.
