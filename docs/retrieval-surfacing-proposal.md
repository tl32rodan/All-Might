# Retrieval-Surfacing Proposal — closing the read-side asymmetry

Origin: design session 2026-06-29 (see `docs/daily-learning/2026-06-29.md`
for the reconnaissance pass that surfaced it). Trigger was a user-reported
pain on a live `allmight + smak` project running OpenCode + OMO:

1. The agent is **not proactive** about creating / maintaining / querying
   the vector index.
2. Despite having `/search` and `/recall`, the OpenCode / OMO agent still
   **defaults to built-in tools** (grep / read) to spelunk code.

The competitor that crystallised the fix is
[`DeusData/codebase-memory-mcp`](https://github.com/DeusData/codebase-memory-mcp)
(19.9k★). Its transferable idea is **not** its knowledge graph (that is
Serena's lane — dispositioned in `docs/daily-learning/2026-05-25.md` Q2 as
complementary code-nav, not a competitor to SMAK's fuzzy domain retrieval).
Its transferable idea is the **delivery mechanism**: a non-blocking
`PreToolUse` hook on `Grep`/`Glob` that runs a parallel structured query and
injects the result as `additionalContext` — the agent keeps its grep reflex
but gets the structured answer for free.

This document fixes the implementation contract before code is written, per
CLAUDE.md's *Planning Workflow*.

---

## 1. Diagnosis — mechanism gap, not philosophy error

The honest framing the user asked for: **is this a mechanism problem or a
design-philosophy / core-architecture deficiency?**

**Answer: primarily a mechanism gap, but it exposes one wrong architectural
assumption.** Not a philosophy to overhaul — a philosophy implemented
asymmetrically.

### 1.1 The smoking gun (our own code)

`core/plugin_telemetry.py::PLATFORM_CAPABILITIES` already declares:

```python
"tool_execute_after_inject": {"opencode": True, "claude_code": False},
```

This capability is **named, declared as OpenCode-available, and used by
zero plugins**. Every entry in `PLUGIN_MANIFEST` (`memory-load`,
`memory-history`, `role-load`, `feedback-check`, `offline-reference`,
`remember-trigger`, `todo-curator`) sits on a session / chat / stop /
user-prompt lifecycle event. **None intercepts tool execution.** The hole
was carved into the taxonomy and never filled.

### 1.2 The architectural asymmetry

| Side | Investment today | Mechanisms |
|---|---|---|
| **Write / freshness** | Heavy | heartbeats, `ingest.pending` marker, memory-history git mirror, L3 auto-ingest closure |
| **Read / surfacing** | ~Zero | 100% pull-based; agent must *choose* `/search` / `/recall`; only skill prose ("trust the model") nudges it |

The system is excellent at *keeping the index fresh* and *recording
memory*, and has **no mechanism to put the index in front of the agent at
the moment of need**. That single gap is the common root of both pains.

### 1.3 The wrong assumption, stated precisely

> **Recording (write) is intentional — `/remember` as a deliberate act is correct.**
> **Retrieval (read) should be ambient — it should *not* require a deliberate act.**
> **All-Might treats both as agent-initiated. That is the asymmetry.**

"Trust the model to reach for the tool" holds on the write side (a human
deliberately runs `/remember`). It fails on the read side — especially for
the OpenCode / OMO + weaker-model population All-Might explicitly targets,
which under context pressure always picks the lowest-friction tool (built-in
grep). **A tool you must remember to use is a tool that gets skipped.**

The fix is to make the read side symmetric with the write side — add a
surfacing mechanism — *without* touching the core capability model, the
routing preamble, or any non-goal.

### 1.4 Why this is not the rejected anti-pattern

CLAUDE.md rejects meta-cognition instructions ("first reflect, then list
candidates, then filter…") because weak models mechanise them into noise.
A surfacing hook is the **opposite**: it does not instruct the model to
change its decision process — it augments the model's *input* transparently.
`augment silently` ≠ `instruct to reflect`. The model still greps; it just
sees better data alongside the grep result.

---

## 2. Premises requiring user confirmation

Each "P-n" is a choice that, if reversed later, makes the work throwaway.
Confirm in chat before any code.

| # | Decision | Default in this plan | Reversible? |
|---|---|---|---|
| **P-1** | Ship as **one new project-wide plugin** (`search-surface`), *not* a new capability. It iterates `personalities/*/database/*/config.yaml` + `personalities/*/memory/store/` at runtime — same project-wide-hook pattern as `memory-history`. No new data dir, no `personalities.yaml` entry, no uninstall semantics → fails the "new capability" bar deliberately. | New plugin, no new capability. | Hard — re-homing later means moving files. |
| **P-2** | **Augment, never replace/gate.** The hook appends SMAK results to (OpenCode) or injects alongside (Claude Code) the agent's grep/glob result. It never blocks, rewrites, or substitutes the built-in tool. DeusData's "hard structural gate" is explicitly **rejected** — it fights the host and is brittle across host versions (cf. the OpenCode V2 plugin API churn logged 2026-06-29). | Augment-only. | Hard — gating is a different contract. |
| **P-3** | **OpenCode surface** = `tool.execute.after` on `grep`/`glob` (the already-declared `tool_execute_after_inject` capability). Read the real `@opencode-ai/plugin` output contract before writing — do not infer the `additionalContext`/append shape from release notes (CLAUDE.md third-party-integration rule). | `tool.execute.after`, contract verified first. | Medium. |
| **P-4** | **Claude Code mirror** = `PreToolUse` hook on `Grep`/`Glob` injecting `additionalContext` (DeusData proves this path). This requires a **new `PLATFORM_CAPABILITIES` key** (e.g. `pre_tool_inject: {opencode: True, claude_code: True}`) because the existing `tool_execute_after_inject` is marked `claude_code: False`. The plugin `requires` the new key so the manifest permits a mirror. | Mirrored via new capability key. | Medium — could ship OC-only first (`claude_code_mirror: None`) and promote later. |
| **P-5** | **Gating to control cost + noise.** The hook fires only when: (a) an index exists for the active personality; (b) the grep/glob target is in source-code / knowledge territory (not e.g. `.allmight/`); (c) results pass a relevance floor (SMAK score threshold); (d) capped at **top-3**. If any gate fails → no injection, T1 heartbeat fires with no T2. | All four gates, top-3 cap. | Easy — tune thresholds. |
| **P-6** | **Heartbeat is the judge, not a guess.** T1 (`search-surface`) on every handler entry; T2 (`search-surface.injected`) only when content is actually appended/injected. Ship as a **two-week prototype on the user's real project first**; decide fixation from the `fired` vs `injected` ratio and hit quality, not from intuition. | Prototype-gated by heartbeat data. | Easy. |
| **P-7** | **Scope = read surfacing only.** The create/maintain half of pain #1 (auto-index for `database`) is a **separate, smaller follow-up** (§6), not bundled here. It reuses the existing L3 marker-touch closure pattern and must **not** introduce a background daemon (CLAUDE.md touch-file-simplicity principle; DeusData's watcher is explicitly *not* copied). | Read-only this round. | Easy. |
| **P-8** | Plugin name `search-surface` (it surfaces `/search` + `/recall` material). Active-personality resolution reuses the `> **Default personality**` callout + `ROUTING_PREAMBLE` mechanism already in `MEMORY.md` — no new routing source. | `search-surface`. | Easy. |

If any premise is wrong, redirect now — 30 seconds of confirmation saves a
redraft.

---

## 3. Goal & scope

| | This proposal (read surfacing) | Deferred follow-up (§6, write/freshness) |
|---|---|---|
| Deliverable | `search-surface` plugin (OC) + `search_surface.py` mirror (CC) that injects SMAK results around grep/glob | Generalise the L3 marker-touch auto-ingest closure to `database/` workspaces |
| Agent capability after | When the agent greps source, top-3 SMAK hits appear alongside — without the agent choosing `/search` | `database` index re-ingests lazily on next session when source changed, like L3 journal does today |
| Pain addressed | #2 (defaults to built-in tools) + the *query* third of #1 | the *create* + *maintain* thirds of #1 |
| LOC budget | ~250 (one TS plugin + one Py hook + manifest entry + tests) | ~150 (closure reuse) |
| Stop-loss | Prototype-gated; if heartbeat shows low `injected` or poor hits, delete in one commit | Independent; can ship or not regardless of §3-left |

**Non-goals (locked by this document):**
- No knowledge graph / AST layer (Serena + DeusData lane — already rejected).
- No background watcher daemon (touch-file simplicity).
- No replacing/gating the host's grep/glob (augment-only, P-2).
- No new capability, no `cli.py` change, no `core/` → `capabilities/` import.

---

## 4. Design

### 4.1 Runtime flow (OpenCode)

```
agent calls grep("setup timing violation")        ← agent's own reflex, unchanged
  │
  ├─ tool.execute.after("grep") fires    ── T1 heartbeat: search-surface
  │     ├─ gate P-5: index exists? target in scope? ─ no → return (no T2)
  │     ├─ resolve active personality (Default callout + ROUTING_PREAMBLE)
  │     ├─ smak search --config <active>/... --top 3 --min-score <floor>
  │     ├─ no hits above floor → return (no T2)
  │     └─ append "Related (SMAK): …3 hits…" to the tool output
  │                                        ── T2 heartbeat: search-surface.injected
  └─ agent sees grep result + structured hits, decides next step
```

Claude Code mirror: same logic in `PreToolUse` on `Grep`/`Glob`, emitting
the hits as `additionalContext` instead of an output append (the CC
injection path DeusData uses).

### 4.2 Shared-string discipline (CLAUDE.md dual-platform rule 3)

The "Related (SMAK): …" framing text and the gate thresholds are **one
Python generator** (e.g. `_surface_block_text()` / `SURFACE_MIN_SCORE`),
substituted into the TS template via `__SHARED_CONSTANT__` and referenced
directly by the Py hook. The TS and Py surfaces must not drift.

### 4.3 Files

```
src/allmight/capabilities/database/        ← database owns it (it owns /search)
├── surface_plugin.py                        — build_search_surface_ts() (OC plugin string)
├── surface_hook.py                          — build_search_surface_py() (CC hook string)
└── (shared constants)                       — _surface_block_text(), SURFACE_MIN_SCORE

src/allmight/core/plugin_telemetry.py
├── PLATFORM_CAPABILITIES                     — + "pre_tool_inject": {oc:True, cc:True}
├── KNOWN_OPENCODE_PLUGINS                    — + "search-surface"
└── PLUGIN_MANIFEST["search-surface"]         — requires:[pre_tool_inject], mirror:"search_surface.py"

tests/
├── test_search_surface.py                    — OC plugin + CC hook string presence + negative assertions
├── (extend) test_capability_manifest.py      — mirror coherence for the new entry
└── (extend) test_claude_bridge.py            — TestHooksRunCleanly runs search_surface.py end-to-end
```

Ownership note: `search-surface` lives under the **`database`** capability
because `database` owns `/search`. But the *plugin* is project-wide (written
once into `.opencode/plugins/`), consistent with the "plugins are
project-wide" convention — it is not projected per-personality.

---

## 5. Why this clears the simplicity bar (when nothing has in 5 passes)

The 2026-05-25 standard: *a candidate clears the bar only when it solves a
real, experienced problem that no existing mechanism covers.* Every prior
pass's candidate failed one clause. This one passes both:

1. **Real & experienced** — the user reported it from a live project, not a
   hypothetical.
2. **No existing mechanism** — read-side surfacing genuinely does not exist;
   `/search` and `/recall` are pull-only.
3. **Built on declared infrastructure** — uses `tool_execute_after_inject`,
   already in the taxonomy; structurally isomorphic to existing plugins +
   heartbeat observability + dual-platform mirror.
4. **Violates no non-goal** — not a capability, not a daemon, not SQLite,
   does not touch `cli.py` or the routing single-source.

**Investment rating: 4/5 — build, but prototype-gated by heartbeat data.**
The one deduction is real noise risk: if SMAK's top-3 are often irrelevant,
the hook pollutes context. P-5's relevance floor + P-6's two-week
`injected`-ratio trial are the mitigations; do not fixate the design until
the heartbeat data justifies it.

---

## 6. Deferred follow-up — the create/maintain half of pain #1

Pain #1 has three parts; §3 covers *query*. The other two:

- **create** — `database` has no auto-index closure; today it needs manual
  `/onboard` / `/sync`. 
- **maintain** — the L3 marker-touch lazy closure (`memory-history.ts`
  touches `ingest.pending`; `memory-load.ts` drains it next session) covers
  **only `memory/journal/`**, not `database/` workspaces.

**Proposed (separate, ~150 LOC):** generalise the existing closure to also
mark `database/*/` dirty when source files under their `config.yaml` roots
change, draining on next session. **Reuses the existing pattern; introduces
no daemon** (explicitly *not* DeusData's background watcher — the deliberate
trade-off, per CLAUDE.md, is "one session stale but dead simple"). This is
filed as a follow-up, not bundled, so the read-side win can ship and be
measured independently.

---

## 7. Verification discipline (CLAUDE.md third-party-integration rules)

Non-negotiable before this ships:

1. **Read the real contract first.** Read `@opencode-ai/plugin` type defs
   and a published plugin that uses `tool.execute.after` (and DeusData's
   `PreToolUse` hook for the CC side) — do **not** infer the
   append/`additionalContext` shape from release notes. The 2026-06-29 pass
   already flagged the OpenCode **V2 plugin API** is in flux; confirm the
   `tool.execute.after` contract is stable on the target version *before*
   building on it.
2. **Type-check the generated TS once** — `allmight init <demo>` +
   `tsc --noEmit --skipLibCheck .opencode/plugins/search-surface.ts`.
   (This is also exactly the candidate for the CI typecheck test proposed
   as Q4 in the 2026-06-29 log — building that test first would cover this
   plugin automatically.)
3. **Negative assertions in tests** — assert the exact `tool.execute.after`
   signature and append path; assert the absence of any gating/blocking
   shape (P-2); assert the CC hook emits `additionalContext`, not a blocking
   exit code.
4. **Verify on one host before claiming both** — prototype on the user's
   OpenCode + OMO setup first (where the pain lives); only then validate the
   Claude Code mirror.

---

## 8. Open decisions for the user

1. **Confirm premises P-1…P-8** (especially P-2 augment-only and P-4
   mirror-now-vs-OC-first).
2. **Bundle or split §6?** Recommendation: split — ship read surfacing,
   measure, then do create/maintain.
3. **Prototype host?** Recommendation: the live OpenCode + OMO project that
   produced the pain, so the heartbeat data is real-world from day one.

Once P-1…P-8 are confirmed, the build is one plugin + one mirror + manifest
wiring + tests — incremental, reversible, and judged by its own heartbeat.
