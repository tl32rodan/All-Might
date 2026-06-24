# Concentration Review — 2026-06

Scope: whole-framework architecture review (`/simplify` session), plus a
root-cause diagnosis of a long-standing operator complaint: *"plugin
heartbeats refresh, but my deployed agent (super-learner) never
self-reflects and never creates skills."*

Method: four parallel reviews (core-spirit audit, plugin-mechanics
trace, deployment evidence audit of `tl32rodan/super-learner`,
concentration plan) over `All-Might` HEAD `27e3b83` and `super-learner`
HEAD `be9c71d`.

---

## 1. Core spirit (as stated by our own docs)

- **`docs/plan.md` lesson 1:** *"Auto-capture beats agent-discipline."*
  Reliable cross-session memory comes from hooks that capture
  automatically, not from an agent that remembers to call `/remember`.
- **README:** a **role-centric agent harness** — user-defined
  personalities opt into framework capabilities (`database`, `memory`,
  `schedule`); one global slash-command surface; OpenCode primary,
  Claude Code mirrored where structurally possible.

Everything below is judged against those two sentences.

## 2. Headline finding: heartbeat ≠ behavior

Ground truth from the super-learner deployment:

- The learning loop itself works: **16 wake cycles** committed
  (deepener drafts, critic findings, librarian curriculum,
  `mindmap/_operations.log` entries).
- The memory/reflection layer has **never fired once**:
  `.allmight/memory-history/` is empty (no `.git`), `MEMORY.md` still
  shows `*(none recorded yet)*`, every `usage.log` is 0 bytes, every
  `skills-log.md` is the unmodified template, zero journal entries,
  zero `understanding/` files.

So heartbeats answer *"did the handler run?"* — they cannot answer
*"was a nudge injected?"* nor *"did the agent comply?"*.
`emitHeartbeat()` is the first line of every handler, before any
conditional. A `remember-trigger` heartbeat refreshes on every
`session.idle` even in sessions where the nudge condition
(`idleCount % NUDGE_EVERY === 0`) is never true.

## 3. Root-cause chain (why reflection / skill-creation never happens)

1. **Name collision misleads.** `reflection.ts`
   (`core/personalities.py:1118-1217`) is only a per-turn *"if the
   user just pointed out a mistake, reflect 2-3 sentences"* cue. The
   actual self-reflection surface is the `/reflect` command
   (`capabilities/memory/templates/commands/reflect.md`). The plugin
   and the command share a name but not a job.
2. **The deployed instance never got `/reflect`.** super-learner's
   `.opencode/commands/` has 10 commands; `reflect.md` is not one of
   them (its `remember.md` is the pre-Wave-2 merged body). The agent
   cannot run a command that is not installed.
3. **Nudge fire-conditions assume long interactive sessions.**
   `remember-trigger` needs `idleCount % NUDGE_EVERY === 0`
   (`initializer.py:859`, currently 3; the deployed copy says 5 —
   drift) *and* a subsequent `chat.message` in the same session to
   deliver the queued nudge. A scheduled one-shot `/wake` session has
   exactly one `chat.message` and one `session.idle`, then exits:
   the nudge is never queued, and even a queued nudge would have no
   next turn to land on. The pre-compaction nudge needs compaction,
   which one-shot sessions never reach. **In super-learner's primary
   operating mode, every reflection trigger is structurally dead.**
4. **Skill creation is aspirational, not implemented.**
   - Nothing teaches it: no skill/command body explains how to write
     `personalities/<p>/skills/<name>/SKILL.md`; the only mention is
     the nudge line "if you created a new skill … log it in
     skills-log.md", which presupposes creation that nothing initiates.
   - Even if the agent wrote one, `compose()`
     (`core/personalities.py:266-382`) — the only thing that projects
     per-personality entries into `.opencode/` — is called solely from
     `allmight add` / `share pull` (`cli.py:323`, `cli.py:573`).
     A runtime-written skill is invisible to OpenCode until a human
     re-runs the CLI. The loop has no closure.
   - In super-learner the `personalities/<p>/{skills,commands}/` slots
     don't even exist on disk.
5. **The deployment drifted because it was file-copied.** super-learner
   moved to "unified file-based air-gap deployment, no git remote"
   (its commit `76943bd`); it predates the `/remember`–`/reflect`
   split, `offline-reference.ts`, NUDGE_EVERY=3, and the memory-history
   mirror init. Two `cc/` heartbeat markers are committed to its git
   (`.gitignore` excludes `heartbeats/` but the files were added
   earlier) — runtime telemetry in version control is noise.

## 4. Verdict on the mechanism ("is plugin prompt-injection right?")

**Right for context freshness, wrong as the sole driver of episodic
duties.**

- Keep injection where the job is *keeping always-on context warm*:
  `memory-load` (L1 after compaction), `role-load` (ROLE.md for
  un-primed sessions), `offline-reference`. That is genuine
  auto-capture infrastructure.
- Reflection, memory write-back, and skill creation are **episodic
  duties**. Driving them with ambient nudges contradicts plan.md
  lesson 1 — a nudge *is* agent-discipline, just relocated. Duties
  belong at one of two deeper layers:
  1. **Inside the scripted cycle** — a numbered step in the loop/skill
     body that the session is guaranteed to read (super-learner's
     `/wake` Step 4 STATUS.md trace proves this layer works: it fired
     16/16 times).
  2. **As their own scheduled session** — `am-<personality>-reflect`
     cron task that runs `/reflect` with nothing else competing for
     attention (the schedule capability already exists for exactly
     this shape).
- Skill creation additionally needs a deterministic closure:
  an agent-callable **`allmight compose`** CLI subcommand that re-runs
  projection (symlinks + AGENTS.md + registry), so the agent writes
  the SKILL.md and Python — never the agent free-form — wires it up.
  This matches the existing `/onboard` → `allmight add` pattern.

## 5. Test plan (how to verify any of this, now and after fixes)

Three observables, strictly ordered; each subsumes the previous:

| Level | Question | How to measure |
|---|---|---|
| T1 handler ran | did OpenCode load + call us? | existing heartbeats (`allmight plugin status`) |
| T2 payload injected | did a nudge actually enter the model context this session? | (a) add a second marker `heartbeats/oc/<name>.injected` touched only on the inject path; (b) in a live session ask the agent to quote any `[Memory Nudge]` / `Reflection Check` text it can see — if it can quote it, injection reaches the model; (c) inspect OpenCode session storage for the synthetic part |
| T3 agent complied | did behavior change? | outcome artifacts only: `git -C .allmight/memory-history log --oneline | wc -l`, journal entry count, `MEMORY.md` placeholder check, skills-log entries. super-learner today: all zero across 16 cycles — compliance is the metric that was never watched |

Deterministic E2E recipe (framework repo):

```bash
cd "$(mktemp -d)" && allmight init . --yes && allmight add tester --capabilities memory
# 1-turn scheduled-session simulation:
opencode run "do a trivial task"           # expect: NO nudge (by design)
# interactive simulation (NUDGE_EVERY turns):
opencode    # 3 turns, then check:
ls .allmight/plugins/heartbeats/oc/        # T1
grep -c . personalities/tester/memory/journal/* 2>/dev/null  # T3
git -C .allmight/memory-history log --oneline                # T3
```

`allmight plugin status` should grow a one-line outcome footer
(journal count, mirror commits, L1 placeholder yes/no) so T3 is
visible from the same command operators already run.

## 6. Concentration plan (priority order)

Builds on the reduction verdicts already in
`docs/plugin-observability.md` — none of this re-litigates locked
decisions.

1. **Close the deployment gap first** (super-learner): re-sync against
   current init (`/reflect` command, plugin generation, NUDGE_EVERY,
   memory-history init), untrack the committed heartbeat markers.
   Cheapest fix with the highest behavioral delta.
2. **Move episodic duties into the cycle**: add a "close the cycle"
   step to wake/loop bodies (one `/remember` observation per cycle;
   `/reflect` every k-th cycle or as `am-<p>-reflect` weekly task).
   This is the actual fix for "no self-reflection".
3. **Add the skill-creation closure**: `allmight compose` subcommand +
   one step in `/reflect` ("repeated procedure → write
   `personalities/<active>/skills/<name>/SKILL.md`, run
   `allmight compose`, log to skills-log.md"). Until then, stop
   claiming runtime skill slots work.
4. **Heartbeat v2 (`.injected` markers + outcome footer)** — tiny
   diff, converts `plugin status` from T1-only to T1+T2+T3.
5. **Execute plugin reduction Phase 1**: delete `trajectory-writer`
   (no consumer) and `usage-logger` (transcripts already log) —
   already marked "probably delete" in plugin-observability.md;
   the super-learner data adds: zero readers in 16 cycles.
   ~371 generated TS lines and ~12 KB per project removed.
6. **Reduce fire rates** per the same doc: `memory-load` size-watch
   scan and `memory-history` journal walk run on every
   `chat.message` — move both to session boundaries / write events
   (50-100 ms + up to ~1k tokens saved per turn).
   Re-evaluate `role-load` vs composed AGENTS.md (likely inject only
   the active personality's ROLE.md).
7. **Delete dead weight in the framework repo**: `hub/` (deprecated,
   no external importers), `enrichment/policy.py` (advisory prose
   living as Python — fold into the skill `.md`), and decide
   schedule T2 (ship or label T1-only in README).
8. **Defer**: shared-helper extraction for the duplicated
   Part-construction / dir-scan boilerplate inside generated TS —
   real but small; do it opportunistically when touching those
   generators, after the plugin count has shrunk.

Net effect: 9 always-on plugins → ~4 (memory-load, memory-history,
role-load-or-none, offline-reference), nudge logic relocated to the
two layers that demonstrably execute, and an observability story that
measures outcomes instead of handler entries.

## 7. Explicitly not changed

- Touch-file heartbeat simplicity (no JSONL telemetry) — T2/T3 above
  stay within the touch-file design.
- OFA/AFO asymmetry, no `/distill`, no L2 RAG, no SQLite store, marker
  contract, dual-platform invariant — all locked decisions, untouched.
- `reflection.ts`'s mistake-feedback cue may stay (it is cheap and
  orthogonal), but it must stop being mistaken for the self-reflection
  mechanism; renaming to `feedback-check` would dissolve the
  collision.
