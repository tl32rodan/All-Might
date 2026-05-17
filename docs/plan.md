# Memory Layer & Dual-Platform Plan

Outcome of a comparison-driven design session against `pro-workflow`,
`claude-memory-compiler`, and `opencode-swarm`. This plan captures the
decisions, the reasoning behind them, and the concrete work items —
ordered by priority. Read top-to-bottom; later sections assume the
earlier decisions.

## Context

Three peer projects were studied for design lessons:

- **pro-workflow** (Claude Code only) — self-correcting SQLite memory,
  auto-capture `[LEARN]` blocks, UserPromptSubmit auto-injection of
  top-k wiki hits, Multi-LLM council.
- **claude-memory-compiler** — session-derived markdown knowledge base,
  no embeddings. Documented scaling failure at ~100 articles because
  the whole wiki ships in every compile/query prompt.
- **opencode-swarm** — multi-agent gated pipeline with file-authority
  bounds and PRM failure detection.

The lessons that matter for All-Might:

1. Auto-capture beats agent-discipline. pro-workflow's value prop —
   "50 sessions → zero correction frequency" — comes from a Stop hook
   that parses output, not from an agent that remembers to call
   `/remember`.
2. claude-memory-compiler's #3 issue (whole-wiki-in-prompt) is not a
   verdict on LLM-over-markdown. It is a verdict on **no scaling
   strategy**. At its scale the right answer is "index + load on
   demand", not "switch to RAG".
3. opencode-swarm's PRM and file-authority bounds are orthogonal to
   our framework concerns; not adopted.

## Decisions (locked)

1. **No `/distill` slash command.** Incremental pattern detection is
   folded into `/remember#Record` as a `## After Recording` step.
   Batch distillation is deferred to a CLI tool (`allmight memory
   distill`) and only built if incremental proves insufficient after
   ≥3 months of usage.
2. **No new plugin for distill.** Zero new dual-platform sync surface.
3. **Fix the silent RAG bug first.** L3 SMAK ingest is currently
   manual-only — `/recall` returns stale results after every new
   journal write until someone remembers to run `smak ingest`. This
   is a bug, not a feature gap.
4. **L2 gets a TOC, not RAG.** RAG on L2 understanding fragments
   structured knowledge and matches the opposite failure mode of
   claude-memory-compiler. Defer L2 RAG until L2 demonstrably crosses
   ~200 files per personality.
5. **Capability Manifest replaces ad-hoc dual-platform tiering.** Drop
   the idea of no-op Python stubs for OpenCode-only plugins — they
   create the illusion of equivalence. Each feature declares its
   required platform capabilities in a manifest; tests enforce
   manifest ↔ generated-files consistency.

## Work Items

### P0-1 — L3 auto-ingest closure (1–2 days)

**The bug.** `memory/smak_config.yaml` is generated and `/recall`
runs `smak search ... --index journal`, but nothing automatically
triggers `smak ingest` after journal writes. The index falls behind
silently. `/remember#Reflect` mentions `smak ingest` as a manual
"if needed" step that agents routinely skip.

**Mechanism.** Two-stage: mark on write, drain on next start.

1. `memory-history.ts` Stop hook (already fires per turn): after the
   existing snapshot, scan `personalities/*/memory/journal/` for
   files newer than `.allmight/ingest.pending`'s mtime (or absence).
   If any → touch `.allmight/ingest.pending`. Do not run ingest here
   (embedding can be 5–30s, would block the turn).
2. `memory-load.ts` `session.created` handler: if
   `.allmight/ingest.pending` exists, spawn `smak ingest --config
   personalities/<p>/memory/smak_config.yaml --incremental` async per
   personality. Delete the marker on success. Log to
   `memory/usage.log`.

**Acceptance.** New journal written in session N is searchable via
`/recall` in session N+1 without any agent action. Session N's own
`/recall` returning stale-for-N entries is acceptable — the
just-written content is still in the agent's context window.

**Files touched.**

- `src/allmight/capabilities/memory/initializer.py`:
  `_memory_history_plugin_content` (add marker write),
  `_opencode_plugin_content` for `memory-load.ts` (add drain on
  session.created), and the matching `_claude_memory_load_hook_content`
  / `_claude_memory_history_hook_content` for Claude Code parity.
- `tests/test_memory_init.py`: assert marker-write logic and drain
  logic strings present in both surfaces.

**Dual-platform.** Both required capabilities (`session_stop_marker`,
`session_start_inject` with subprocess) exist on both platforms.
Manifest entry: `requires: [session_stop_inject, session_start_inject]`,
`opencode: memory-history.ts + memory-load.ts`, `claude_code:
memory_history.py + memory_load.py`.

### P0-2 — Incremental distill in `/remember#Record` (0.5 day)

**Intent.** When `/remember#Record` writes a new journal entry, the
same call also detects whether the new entry forms a pattern with the
last N entries in the same workspace, and updates
`memory/understanding/<workspace>.md` if it does.

**Why not a separate `/distill` command.** Composability and trigger
mismatch. `/remember` already fires at the right cadence (every 5
turns, pre-compaction). A separate `/distill` would either fire too
often (expensive) or too rarely (lose freshness). Same reasoning as
`/reflect` being folded into `/remember`.

**Why not at SessionStart.** Adding heavy journal reading at session
start delays the user's first turn and burdens the most context-rich
moment with batch processing of stale data. Incremental keeps the
work small and contextual.

**Scope.** Read **at most 5** most-recent same-workspace journal
entries. Update L2 **only if** a pattern emerges (repeated theme,
correction of earlier note, completion of a hypothesis). No pattern
→ skip cleanly. Bounded read keeps token cost predictable.

**Files touched.**

- `src/allmight/capabilities/memory/initializer.py`:
  `_remember_command_body` — add `## After Recording: Pattern Check`
  section at the end of `# Record`.
- `tests/test_command_body_generic.py` already pins that no
  personality literal leaks; add a string-presence test in
  `tests/test_memory_init.py`.

**Dual-platform.** Zero impact. `/remember` is a slash command;
`.opencode/commands/` and `.claude/commands/` are the same symlink
target. One source, both platforms.

### P1 — L2 TOC mechanism (0.5 day)

**Intent.** Replace "agent reads all `understanding/*.md`" with
"agent reads `understanding/_index.md` first, then reads the relevant
single file." Defers the need for L2 RAG indefinitely.

**`_index.md` shape.**

```markdown
# Understanding Index — <personality>
- **<workspace>**: <N sections>, last updated <ISO>
  - <one-line topic summary, ≤80 chars>
  - <another>
```

The index is regenerated by `/remember` whenever L2 is written. It is
NOT free-form prose — the schema is enforced so the agent can scan it
in <500 tokens.

**`/recall` step 2** changes from "read every relevant
`understanding/<workspace>.md`" to:

1. Read `understanding/_index.md` (small).
2. Pick relevant workspace based on query.
3. Read only that workspace's full `understanding/*.md`.

**Files touched.**

- `_remember_command_body` — add `_index.md` write step in Record
  flow (after writing L2).
- `_recall_command_body` — replace the unconditional L2 read with the
  index-first flow.
- Generator helper: a Python function that produces the canonical
  `_index.md` schema header so both `/remember` and `/recall` bodies
  reference the same expected format.

**Dual-platform.** Zero impact. Slash-command-only change.

### P2 — Capability Manifest (1–2 days)

**Intent.** Encode the dual-platform contract declaratively, so
deciding "should this plugin be mirrored to Claude Code" stops being
a per-feature judgment call and becomes a manifest lookup.

**Shape.** Add to `src/allmight/core/plugin_telemetry.py` (next to
`KNOWN_OPENCODE_PLUGINS`):

```python
# Required platform capabilities per plugin.
PLATFORM_CAPABILITIES = {
    # Available on both platforms
    "session_start_inject":   {"opencode": True, "claude_code": True},
    "session_stop_inject":    {"opencode": True, "claude_code": True},
    "pre_compact_inject":     {"opencode": True, "claude_code": True},
    "user_prompt_inject":     {"opencode": True, "claude_code": True},
    # OpenCode-only structurally
    "session_idle_counter":   {"opencode": True, "claude_code": False},
    "cross_turn_plugin_state":{"opencode": True, "claude_code": False},
    "mid_turn_message_inject":{"opencode": True, "claude_code": False},
}

PLUGIN_MANIFEST = {
    "memory-load":      {"requires": ["session_start_inject",
                                       "pre_compact_inject"],
                          "claude_code_mirror": "memory_load.py"},
    "memory-history":   {"requires": ["session_stop_inject"],
                          "claude_code_mirror": "memory_history.py"},
    "role-load":        {"requires": ["session_start_inject"],
                          "claude_code_mirror": "role_load.py"},
    "reflection":       {"requires": ["user_prompt_inject"],
                          "claude_code_mirror": "reflection.py"},
    "remember-trigger": {"requires": ["session_idle_counter",
                                       "mid_turn_message_inject"],
                          "claude_code_mirror": None},   # structurally OC-only
    "todo-curator":     {"requires": ["cross_turn_plugin_state"],
                          "claude_code_mirror": None},
    "trajectory-writer":{"requires": ["session_stop_inject"],
                          "claude_code_mirror": None},   # candidate to promote
    "usage-logger":     {"requires": ["session_stop_inject"],
                          "claude_code_mirror": None},   # candidate to promote
}
```

**Update protocol.**

- New plugin: declare requirements in `PLUGIN_MANIFEST` **before**
  writing the TS plugin. The required-capability list determines
  whether `claude_code_mirror` can be non-null.
- Update existing plugin: if behavior change touches a string that
  both platforms emit, update the shared Python generator function
  (never duplicate the string in TS and Python).
- Promote OC-only → dual: requires (a) all `requires:` entries
  available on Claude Code, (b) Python implementation, (c) test
  coverage parity.

**Enforced by tests.**

- For every plugin with `claude_code_mirror: <name>`, the file must
  exist after init with marker.
- For every plugin with `claude_code_mirror: None`, no Python file
  with that hook name may exist (prevents accidental no-op stubs
  that masquerade as parity).
- `allmight plugin status` output formats unavailable hooks as
  `claude_code: unavailable (requires: session_idle_counter)`,
  not `never fired`.

**Generated README compatibility matrix.** A small generator under
`docs/` (or piped into the README via a fenced block) produces a
table from `PLUGIN_MANIFEST`. Users picking a platform see the cost
explicitly.

### P3 — Memory size watch (0.5 day)

**Intent.** Surface scaling pressure before users feel pain. Inject
into the existing memory-load context payload:

```
[Memory Size Watch]
L2: <N files> / <total KB>
L3: <N files> / <total KB>  (index: <size>, last ingest: <relative>)
```

Thresholds (initial guess, tune later):

- L2 warn at 100 files or 1 MB → flag in MEMORY.md callout
- L3 warn at 5000 files or 50 MB → suggest periodic `smak ingest
  --rebuild`
- L3 ingest staleness >24h → flag

When L2 crosses **200 files for any single personality**, that is
the signal to revisit Decision #4 (L2 TOC vs L2 RAG) with real data.

**Files touched.** `memory-load.ts` and `memory_load.py` — add the
size-watch block to the injected context payload. Shared generator
helper for the threshold messages.

**Dual-platform.** Both required capabilities trivially available;
no new manifest entry needed.

## Dual-Platform Protocol (the meta-decision)

**Principle.** OpenCode is the design target; Claude Code is mirrored
where the platform's hook system structurally supports the same
behavior. No no-op stubs; no fake parity.

**The three rules.**

1. Any user-visible string that appears in both a TS plugin and its
   Python hook **must** originate from a single Python generator
   function. The TS template uses `__SHARED_CONSTANT__` substitution.
   Violations are silent-drift bugs waiting to happen — see
   `_reminder_nudge_text()` for the canonical pattern.
2. Every plugin is registered in `PLUGIN_MANIFEST` with required
   capabilities. The `claude_code_mirror` field is determined by the
   capabilities, not by intent.
3. Tests enforce manifest ↔ filesystem consistency on every init.

**The honest README claim.** All-Might supports OpenCode fully and
Claude Code for the subset of features whose required capabilities
exist in Claude Code's hook system. Users choose with eyes open.

## Non-goals (explicit, to prevent scope creep)

- **No L2 RAG** until L2 demonstrably crosses ~200 files per
  personality. Until then, TOC + on-demand single-file read is
  cheaper, simpler, and preserves narrative integrity.
- **No `/distill` slash command.** Incremental in `/remember#Record`
  is the agreed surface. Batch distillation, if ever needed, is a
  CLI tool that calls Claude API directly — out of the agent's
  context window entirely.
- **No no-op Python stubs** for OpenCode-only plugins. They create
  the illusion of parity and hide capability gaps.
- **No SQLite memory store** (pro-workflow's choice). All-Might's
  YAML + git mirror keeps memory human-readable, diff-able, and
  recoverable. SMAK already provides the vector layer where it's
  needed.
- **No Multi-LLM Council.** Out of scope for a framework — that is
  an individual workflow concern.

## Suggested execution order

| Order | Item | Days | Why |
|-------|------|------|-----|
| 1 | P0-1 L3 auto-ingest | 1–2 | Fixes a silent bug — highest user impact |
| 2 | P0-2 Incremental distill | 0.5 | Lowest-cost differentiator vs `claude-memory-compiler` |
| 3 | P1 L2 TOC | 0.5 | Closes the L2 scaling story without committing to RAG |
| 4 | P2 Capability Manifest | 1–2 | Structural; do once and stop relitigating |
| 5 | P3 Memory size watch | 0.5 | Observability for the thresholds above |

Total: ≤ 5 days. Recommended to do P0-1 and P0-2 in one pull request
(the user-visible memory improvements), then P1 + P2 + P3 in a
follow-up (the structural cleanups).

## Open questions

- How does `smak ingest --incremental` behave when the config points
  at journal entries deleted between sessions? Need to verify before
  P0-1 lands; may require `--rebuild` fallback on first run after
  restore.
- Trajectory-writer and usage-logger are listed `claude_code_mirror:
  None` for now. Their `requires` (`session_stop_inject`) is
  available on Claude Code; they are candidates to promote, but only
  if a user reports needing observability on the Claude Code side.
  Until then, keeping them OC-only respects "OpenCode is primary".
- For the L2 TOC, does the agent regenerate the index on every L2
  write (simple, cheap, possibly noisy) or only on `/remember#Reflect`
  (less churn, possible staleness)? Default to "every L2 write" for
  freshness; revisit if it becomes noisy.
