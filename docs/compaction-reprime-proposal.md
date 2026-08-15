# Proposal — Fix the Claude Code compaction re-prime + hook output budget

**Status**: **implemented** 2026-08-15. Both maintainer decisions in
§6 were resolved *in favour of the rules*: the budget applies to both
surfaces, and the two `UserPromptSubmit` scripts converted in the same
change. See §7 for what actually shipped.
**Found**: 2026-08-15 platform recon (`docs/daily-learning/2026-08-15.md` §6).
**Scope**: two defects in the Claude Code hook surface, both pre-existing,
both invisible to the current test suite. Neither is caused by an
upstream change.

---

## 1. Summary

| ID | Defect | Severity | Fix size |
|---|---|---|---|
| **B1** | The Claude Code post-compaction re-prime is registered on the wrong event **and** emits its payload through a channel that event does not honour. | **high** — a shipped feature is very likely dead | small |
| **B2** | Hook output is capped at 10,000 characters and truncated silently. `role_load.py` concatenates every personality's full `ROLE.md`. | **high** — scales with personality count | medium |

Both live in the same two generators, so they should land together:

- `src/allmight/core/claude_bridge.py` (`role_load.py`, `_settings_payload`)
- `src/allmight/capabilities/memory/initializer.py`
  (`_claude_memory_load_hook_content`)

---

## 2. B1 — the re-prime is on the wrong event, and speaks the wrong protocol

### 2.1 What the code does today

`claude_bridge.py:373`

```python
_RELOAD_SCRIPTS = ("memory_load.py", "role_load.py")
```

`claude_bridge.py:424-431`

```python
reload_block = _block(_RELOAD_SCRIPTS)
return {
    "SessionStart": reload_block,
    "PreCompact":   reload_block,     # <-- defect
    ...
}
```

Both scripts end the same way — `claude_bridge.py:348-356` and
`memory/initializer.py:1999-2006`:

```python
event = payload.get("hook_event_name") or "SessionStart"
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": event,       # == "PreCompact" when PreCompact fires
        "additionalContext": text,
    }
}))
```

### 2.2 Two independent defects, stacked

**Defect 2.2a — wrong event.** Verified from
`code.claude.com/docs/en/hooks`:

> "**PreCompact and PostCompact**: These events fire before and after
> context compaction. PreCompact hooks can block compaction; PostCompact
> hooks fire after it completes and can't block it."

`PreCompact` fires **before** compaction. Anything it injects is part of
the context that compaction is about to summarise away. Re-priming there
is the wrong end of the operation regardless of protocol.

**Defect 2.2b — wrong protocol.** The docs describe the context path as
plain stdout, for three named events only:

> "For `UserPromptSubmit`, `UserPromptExpansion`, and `SessionStart`,
> where Claude Code adds plain-text stdout as context that Claude can
> see and act on."

There is **no `hookSpecificOutput` section for `SessionStart`,
`UserPromptSubmit`, `PreCompact`, or `PostCompact`** — those events take
only the universal fields (`continue`, `stopReason`, `suppressOutput`,
`systemMessage`, `terminalSequence`). And a mis-shaped object is
absorbed rather than raised:

> "exit 0 with a parsed object that fails schema validation is a
> non-blocking error: the action proceeds, and the transcript shows a
> `<hook name> hook error` notice with the validation message."

**Correction to the daily-learning entry**: this is *not* fully silent —
a hook-error notice appears in the transcript. It is silent **to the
agent's context**, which is the part that matters, and silent to our
test suite. The daily-learning log overstated it; §6 there should be
read with this correction.

### 2.3 The parity argument — this is settled independently of the docs

The OpenCode side does not re-prime before compaction either. From
`memory/initializer.py:728`:

```
// Cleared on session.created / session.compacted so the next chat.message
```

The OpenCode mechanism is: **`session.compacted` marks the session
un-primed → the next `chat.message` re-injects** via
`output.parts.unshift`. That is a *post*-compaction re-prime driven by
the next turn.

So even if `additionalContext` on `PreCompact` worked perfectly, the two
surfaces would still not be behaviourally equivalent — one re-primes
before, the other after. The dual-platform invariant is violated on
timing alone. This is the strongest part of the case: it does not depend
on any inference about undocumented field handling.

### 2.4 Proposed fix

**`SessionStart` already covers compaction.** Its documented matcher
values are:

> `"startup"`, `"resume"`, `"clear"`, `"compact"`, `"fork"`

We register `SessionStart` with **no matcher**, which means all sources —
**including `compact`**. The post-compaction re-prime therefore already
has a correct, working registration. `PreCompact` is redundant *and*
broken.

**P1a — drop the `PreCompact` registration.**

```python
return {
    "SessionStart": reload_block,     # covers startup|resume|clear|compact|fork
    "Stop": _block(_TURN_END_SCRIPTS),
    "UserPromptSubmit": _block(_USER_PROMPT_SCRIPTS),
    "PostToolUse": _block(_TOOL_RESULT_SCRIPTS),
}
```

**P1b — emit plain stdout instead of `hookSpecificOutput`.** In both
generators, replace the JSON print with:

```python
_hb("role_load.injected")
sys.stdout.write(text)
return 0
```

This is the documented path for `SessionStart`, needs no
`hook_event_name` echo, and sidesteps schema validation entirely. It
also deletes the `payload.get("hook_event_name")` read, which existed
only to fill a field we should not be sending.

> **Note on `feedback_check.py` / `offline_reference.py`.** These run on
> `UserPromptSubmit` (`claude_bridge.py:383`) and use the same
> `additionalContext` shape (`:127`, `:193`). `UserPromptSubmit` is in
> the documented plain-stdout list too, so they have the same protocol
> defect — but *not* the wrong-event defect, and their payloads are
> short fixed constants, so B2 does not touch them. **Recommendation:
> convert them in the same change** for one consistent output helper.
> Flagging explicitly because it widens the diff beyond the two
> scripts B1 is nominally about.

**P1c — clean up existing installs.** `_merge_hook_config` only strips
our commands from events present in `owned`; for events *not* in
`owned` it strips `legacy_commands` only (`claude_bridge.py:456-462`).
Removing `PreCompact` from `owned` would therefore **leave stale
`PreCompact` entries in every already-initialised project forever** —
and a dangling registration is exactly the OMO failure-cascade hazard
CLAUDE.md warns about.

Add an events analogue of the existing script-level mechanism:

```python
# Events we used to own. Our commands are stripped from these on every
# bridge write, and never re-added. Same removal-only contract as
# _LEGACY_HOOK_SCRIPTS.
_LEGACY_HOOK_EVENTS = ("PreCompact",)
```

and in `_merge_hook_config`, for events in `_LEGACY_HOOK_EVENTS`, strip
`owned_commands | legacy_commands` rather than `legacy_commands` alone.
User-authored `PreCompact` hooks must survive untouched — `_strip_commands`
already guarantees that, since it filters by exact command string.

### 2.5 Rejected alternatives

| Alternative | Why not |
|---|---|
| Move to `PostCompact` | Adds an event for no gain: `SessionStart` with source `compact` already fires post-compaction, and `PostCompact` has no documented context-injection path either. Adding it would repeat 2.2b with a different event name. |
| Keep `PreCompact`, add `continue`/`systemMessage` | `systemMessage` surfaces to the *user*, not the agent's context. Wrong channel for re-priming. |
| Keep `hookSpecificOutput`, add `SessionStart` matcher | Leaves the unsupported-field problem in place. Plain stdout is documented, simpler, and strictly less code. |
| Do nothing until reproduced live | Reasonable for the *inference* in 2.2b, but 2.3 (timing parity) stands on its own and already justifies the change. |

---

## 3. B2 — 10,000-character output cap

### 3.1 Evidence

> "Hook output strings, including `additionalContext`, `systemMessage`,
> and plain stdout, are capped at 10,000 characters."
> — `code.claude.com/docs/en/hooks` (verified verbatim)

The cap applies to **plain stdout too**, so P1b does not rescue us.

`role_load.py` (`claude_bridge.py:330-340`) builds:

```
--- Role: <name> (ROLE.md) ---
<entire ROLE.md body>
--- End Role: <name> ---
```

for **every** personality, unbounded. `memory_load.py` injects all of
`MEMORY.md` plus the scope-first principle. Three personalities with
ordinary ROLE.md files clear 10 KB comfortably; the truncation is
silent, and it truncates the *tail*, so the last personalities
alphabetically are the ones that vanish.

This is a self-inflicted scaling failure that gets worse exactly as a
project adopts the multi-personality model All-Might is built around.

### 3.2 Proposed fix — degrade to an index, do not blind-truncate

A bare `text[:10000]` would cut mid-sentence and drop whole roles
without telling anyone. Instead, **fall back to progressive disclosure**
— the mechanism All-Might already uses for L2 `understanding/_index.md`:

1. Compute the full payload.
2. If it fits the budget, emit it unchanged (current behaviour; no
   regression for small projects).
3. If it does not, emit a **role index** instead — per personality: name,
   the `role_summary` line, and the path to `ROLE.md` — plus one line
   telling the agent to read the full file on demand.
4. If even the index exceeds budget, truncate the index at a role
   boundary and state how many roles were omitted. Never cut mid-role.

This keeps every role *discoverable* at any scale, which blind
truncation does not, and it reuses a pattern the codebase already
commits to. The 2026-08-15 recon found `deepagents` independently
converging on the same progressive-disclosure shape, which is mild
external support that the fallback is the right one.

### 3.3 Budget constant and the single-generator rule

CLAUDE.md requires that any user-visible string both surfaces emit
originate from one Python generator. The budget is exactly such a
shared constant. Proposed home: `core/plugin_telemetry.py`, beside the
heartbeat snippets, since both surfaces already import from there.

```python
# Claude Code caps hook output (stdout, additionalContext,
# systemMessage) at 10_000 chars and truncates silently. Budget below
# that so the index fallback and its notice always fit.
HOOK_OUTPUT_BUDGET = 9_000
```

**The OpenCode side must adopt the same budget.** `output.parts.unshift`
has no documented cap, so this is not a correctness fix there — it is a
*parity* fix. Two surfaces that inject different amounts of role context
is the same class of drift as B1. The TS templates substitute it via the
existing `__SHARED_CONSTANT__` mechanism.

> **Open question for the maintainer.** Applying the budget to OpenCode
> makes the surfaces equal but makes OpenCode strictly *worse* than it
> is today (it currently injects everything, correctly). The alternative
> — cap Claude only — leaves a documented, deliberate asymmetry.
> My recommendation is **apply to both**, because "behaviour depends on
> which editor I open the project with" is the failure mode the
> invariant exists to prevent, and a role visible in one editor and
> absent in the other is precisely that. But this is a judgement call
> about which principle wins, and it is yours to make.

### 3.4 Interaction with B1

Ordering matters: P1b switches to plain stdout, which is *also* capped.
If B2 is deferred, the switch neither helps nor hurts the cap. If both
land together, apply the budget at the point where the text is
assembled, before any output call, so the two generators share one code
path.

---

## 4. Test plan

The current suite cannot catch either defect: `test_claude_bridge.py::
TestHooksRunCleanly` asserts the JSON output *shape* — which is exactly
the shape that is wrong — and the content tests assert string presence,
which truncation preserves.

| Test | Asserts | Catches |
|---|---|---|
| `test_settings_has_no_precompact` | `"PreCompact" not in _settings_payload()` | B1 regression |
| `test_reinit_strips_stale_precompact` | settings.json pre-seeded with our commands under `PreCompact` → after `write_claude_bridge`, our commands gone, **a user-authored `PreCompact` hook still present** | P1c, and that we don't clobber user hooks |
| `test_reload_hooks_emit_plain_stdout` | running each hook produces non-JSON text on stdout; **negative assertion**: `"hookSpecificOutput" not in out` | B1 protocol regression |
| `test_role_load_respects_budget` | 12 personalities × 2 KB ROLE.md → `len(stdout) <= HOOK_OUTPUT_BUDGET` | B2 |
| `test_role_load_index_fallback_lists_every_role` | same fixture → **every** personality name appears in the output | that the fallback degrades rather than drops |
| `test_role_load_full_body_under_budget` | 1 small personality → full ROLE.md body still present verbatim | no regression for the common case |
| `test_budget_shared_with_opencode` | the numeric budget appears in both the generated `.py` and the generated `.ts` | single-generator rule |

`TestHooksRunCleanly` must be **updated, not extended** — its current
JSON-shape assertion becomes wrong once P1b lands, and leaving it would
pin the bug.

Per CLAUDE.md *After Code Changes*: run `PYTHONPATH=src python -m
pytest tests/`, and because `role-load.ts` / `memory-load.ts` change,
re-run the one-shot `tsc --noEmit --skipLibCheck .opencode/plugins/*.ts`.

---

## 5. What is verified vs inferred

Being explicit, because §2.2b rests partly on absence-of-documentation.

| Claim | Status |
|---|---|
| 10,000-char cap covers stdout and `additionalContext` | **verified** — quoted verbatim |
| `SessionStart` matchers include `compact` | **verified** |
| `PreCompact` fires *before* compaction and can block | **verified** |
| Plain stdout is the documented context path for `SessionStart` / `UserPromptSubmit` | **verified** |
| No `hookSpecificOutput` section exists for `SessionStart` / `UserPromptSubmit` / `PreCompact` / `PostCompact` | **verified** (two independent fetches) |
| Schema-invalid output → non-blocking error + transcript notice | **verified** |
| Our `PreCompact` payload is therefore dropped from agent context | **inferred** — follows from the above, not stated directly |
| OpenCode re-primes *after* compaction, on the next `chat.message` | **verified** — read from our own generator source |
| `SessionStart` with no matcher fires on the `compact` source | **inferred** — from "omitting the matcher matches all" plus `compact` being a listed source |

Two inferences. Both are cheap to confirm empirically before merge:
initialise a scratch project, force a compaction in Claude Code, and
read `allmight plugin status` — `role_load` / `role_load.injected`
heartbeats settle both questions at once. **Recommend doing that first**;
it is a five-minute check that converts the whole proposal to verified.

---

## 6. Recommendation

Land B1 and B2 together as one change, in this order:

1. Run the heartbeat check in §5 to confirm the two inferences.
2. P1a + P1c — drop `PreCompact`, add `_LEGACY_HOOK_EVENTS` cleanup.
3. P1b — plain stdout in both reload generators (and, recommended, the
   two `UserPromptSubmit` scripts).
4. B2 — `HOOK_OUTPUT_BUDGET` + index fallback, shared with the TS side
   pending the §3.3 decision.
5. Tests per §4, including the `TestHooksRunCleanly` update.

Estimated diff: ~120 lines of generator changes plus ~150 lines of
tests, touching three files. No new capability, no new abstraction, no
CLI surface change — this is a correctness fix inside existing
generators, consistent with *"add a flag, not a capability."*

**Two decisions needed from the maintainer before implementation:**

- §3.3 — apply the output budget to the OpenCode surface too (parity,
  my recommendation), or cap Claude Code only (documented asymmetry)?
- §2.4 note — convert `feedback_check.py` / `offline_reference.py` to
  plain stdout in the same change (consistency), or leave them for a
  follow-up (narrower diff)?


---

## 7. What shipped

Both §6 decisions were resolved by the maintainer with "keep the
rules/disciplines first" — so in both cases the invariant won over the
narrower local option.

| Decision | Resolution |
|---|---|
| §3.3 — budget on OpenCode too? | **Yes.** Parity beats leaving OpenCode marginally better. A role visible in one editor and absent in the other is the exact drift the dual-platform invariant forbids. |
| §2.4 — convert the `UserPromptSubmit` scripts? | **Yes.** `feedback_check.py` and `offline_reference.py` now use plain stdout too, so all four hooks share one output convention. |

### Changes

**`core/plugin_telemetry.py`** — new shared source of truth:
`HOOK_OUTPUT_BUDGET = 9_000`, the three user-visible notices
(`ROLE_INDEX_NOTICE`, `ROLE_OMITTED_NOTICE`, `DOC_TRUNCATED_NOTICE`),
and `py_budget_snippet()` / `ts_budget_snippet()` emitting the same
`fitBudget` helper into both runtimes.

**`core/claude_bridge.py`** — `PreCompact` dropped from
`_settings_payload()`; `_LEGACY_HOOK_EVENTS` added with the
removal-only contract, including deleting the key once nothing of the
user's remains under it; `role_load.py`, `feedback_check.py` and
`offline_reference.py` switched to plain stdout; `role_load.py` gained
the index fallback with prose-preferring summaries.

**`capabilities/memory/initializer.py`** — `memory_load.py` switched to
plain stdout and budgeted; both it and `memory-load.ts` now reserve the
scope-first principle and size watch as an untrimmable tail and budget
only the `MEMORY.md` body.

**`core/personalities.py`** — `role-load.ts` gained the same budget,
`buildIndex` and `summarise`, ported to match the Python behaviour.

### Verification

- `822 passed` (was 803; +19 new, 8 updated).
- **8 pre-existing tests were updated, not extended** — they asserted
  the JSON shape that was itself the bug. `TestHooksRunCleanly`'s
  `*_returns_valid_json` tests are now `*_writes_plain_stdout` with
  negative assertions that `hookSpecificOutput` is *absent*.
- New `tests/test_hook_output_budget.py` (16 tests) measures **length
  and role coverage**, not string presence — the only thing that can
  see silent truncation. Covers 1/3/12/200/400-personality projects.
- New `TestRetiredEvents` (3 tests) proves re-init strips our stale
  `PreCompact` entries, **preserves user-authored hooks on that same
  event**, and is idempotent.
- `tsc --noEmit --skipLibCheck --types node .opencode/plugins/*.ts` —
  clean, per CLAUDE.md *After Code Changes* step 2.
- **Cross-surface equivalence checked at runtime, not by inspection**:
  the generated `role_load.py` and a compiled `role-load.js` were run
  against the same 12-personality fixture and their output compared —
  **identical, 1215 bytes both sides**. That is the dual-platform
  invariant actually satisfied rather than nominally.

### Disciplines recorded

Four rules added to CLAUDE.md → *Discipline When Generating
Third-Party Integrations*: output contracts are per-event not
per-tool; know the host's output cap and degrade deliberately;
retiring an event needs a removal path like retiring a script; plus
the existing verify-before-propagating rule now has this as its
worked example. A caution was also added to
`docs/retrieval-surfacing-proposal.md`, which plans to use
`additionalContext` on `PreToolUse` and should confirm that event's
own contract first.

### Still outstanding

The two inferences in §5 remain inferences — the empirical heartbeat
check was not run, because it needs a live Claude Code session and a
forced compaction, which this environment cannot provide. Neither the
fix nor its tests depend on them: §2.3 (timing parity) justifies the
change on its own, and `SessionStart` with no matcher was already the
registration doing the real work. Worth confirming opportunistically
via `allmight plugin status` on a real project.
