# Scheduling Proposal — T1 + T2 Implementation Plan

Decision baseline from `docs/daily-learning/2026-05-20.md` §7–§8:

- OpenCode has no native scheduling ([anomalyco/opencode#11232](https://github.com/anomalyco/opencode/issues/11232)).
- De-facto community runtime: [`different-ai/opencode-scheduler`](https://github.com/different-ai/opencode-scheduler)
  (361★, MIT, single `src/index.ts`, 11 MCP tools, workdir-scoped).
- T3 (own plugin) rejected — duplicates `opencode-scheduler`,
  fails CLAUDE.md's *"new capability needs novel infrastructure"*
  bar, owes per-OS maintenance forever.
- T2 (declarative + apply with schema check) is the target.
- T1 (skill-only) ships first so T2 is incremental, not big-bang.

This document fixes the implementation contract before code is
written, per CLAUDE.md's *Planning Workflow*.

---

## 1. Premises requiring user confirmation

Each "P-n" is a non-negotiable choice that, if reversed later,
makes T2 throwaway. Confirm in chat before starting T1.

| # | Decision | Default in this plan | Reversible? |
|---|---|---|---|
| **P-1** | T1 ships a capability skeleton (`src/allmight/capabilities/schedule/`) carrying only `_install_globals` (SKILL.md) and an empty `personalities/<p>/scheduled/` dir — *not* a bare SKILL.md dropped from `memory`'s `_install_globals`. | Capability skeleton. | Hard. Reversing means moving files later. |
| **P-2** | Declarative file naming: `personalities/<p>/scheduled/<task>.md` carries YAML frontmatter `name`, `description`, `cron`, optional `timeout_seconds`, `permission_mode`. Body is the prompt. Matches Anthropic Desktop's SKILL.md task format verbatim. | YAML frontmatter exactly as shown. | Medium — bundle migration if changed post-T2. |
| **P-3** | Slug for `opencode-scheduler` is `am-<personality>-<task>` (the `am-` prefix prevents collision with user-managed jobs on the same scope). | `am-` prefix. | Easy — slug regeneration on next apply. |
| **P-4** | `apply.py` writes JSON state files directly to `~/.config/opencode/scheduler/scopes/<scope>/jobs/*.json` (Option (b) from yesterday's §7.8), gated by a schema probe — NOT via subprocess MCP calls. | Direct write + probe. | Medium — switch to MCP requires rewriting apply. |
| **P-5** | Schema probe semantics: read the *first existing* job file in the scope and diff its top-level field set against a `KNOWN_SHAPE` constant in `apply.py`. If no jobs exist yet, write a canary file `__allmight_probe__.json`, ask the user to verify it appears in OpenCode via the `opencode-scheduler` MCP `list_jobs`, then delete it. Abort with a clear error on mismatch. | Diff-on-existing, canary-on-empty. | Easy. |
| **P-6** | No Claude Code mirror. `PLUGIN_MANIFEST` entry sets `claude_code_mirror: None` because CC users have Anthropic Desktop scheduled tasks for persistent scheduling; All-Might does not duplicate that. | `claude_code_mirror: None`. | Easy — promote to mirror later if demand. |
| **P-7** | CLI surface: `allmight schedule apply`, `allmight schedule status`. No `add` / `rm` / `edit` — those happen in-tree (`personalities/<p>/scheduled/<task>.md`). | Two subcommands only. | Easy. |
| **P-8** | Plugin name: `schedule-sync.ts` (OpenCode-only, marker-file closure analogous to `memory-history.ts`). | `schedule-sync.ts`. | Easy. |

If any premise is wrong, redirect now — 30 seconds of confirmation
saves a redraft.

---

## 2. Goal & scope

| | T1 | T2 |
|---|---|---|
| Deliverable | Capability scaffolding + agent skill that teaches use of `opencode-scheduler` MCP tools | Declarative source-of-truth + `apply` reconciliation + schema check + sync plugin |
| Agent capability after | Can create / list / delete scheduled jobs by talking to OpenCode (which forwards to `opencode-scheduler`) | Same plus: declared schedules live in repo, travel with `/one-for-all`, drift between repo and runtime is detected on session start |
| LOC budget | ~200 (P-1 makes it slightly heavier than the original 150 estimate because the capability skeleton replaces a bare SKILL.md drop) | ~700 additional (~900 cumulative) |
| Stop-loss | T1 alone is shippable. If T2 is never built, T1 still gives full agent capability — just no portability. | T2 is incremental on T1; no rework. |

---

## 3. T1 milestone — capability skeleton + agent skill

### 3.1 Files written

```
src/allmight/capabilities/schedule/
├── __init__.py                                 — TEMPLATE + install/install_globals/status
├── initializer.py                              — writes globals + per-personality empty dir
├── skill_content.py                            — build_scheduling_skill_md()
└── templates/
    └── skills/scheduling/SKILL.md              — content; read via importlib.resources
```

### 3.2 SKILL.md content sketch (~140 lines)

```yaml
---
name: scheduling
description: >-
  Use this skill when the user asks to schedule, automate, run-on-a-
  cadence, or "every <interval>" any work. Covers OpenCode (via the
  opencode-scheduler plugin's MCP tools), Claude Code (/loop and
  Desktop scheduled tasks), and external cron as the three runtimes.
  Slugs use the prefix "am-<personality>-<task>".
---
```

Body sections (in order):

1. **When to invoke** — trigger phrases; explicit "if user says 'just
   schedule it', ask what runtime and persistence level they need".
2. **Runtime matrix** — three columns (OpenCode + opencode-scheduler /
   Claude Code `/loop` / external cron) × four rows (persistence /
   machine-on / catch-up / setup cost).
3. **Slug discipline** — every job slug MUST start with
   `am-<personality>-` so allmight-owned jobs are distinguishable.
   Reject any agent-proposed schedule that omits the prefix.
4. **Catalogue of recommended All-Might cadences** — table mapping
   each concern to a suggested prompt + cron + chosen runtime:
   - curator audit (weekly)
   - plugin observability roll-up (weekly)
   - L3 size sanity (monthly)
5. **How to use `opencode-scheduler`** — concrete invocation: agent
   calls the `schedule_job` MCP tool with `{slug, cron, prompt,
   timeoutSeconds, permissionMode}`.
6. **Anti-patterns** — don't schedule L3 ingest (already
   reactive); don't schedule from `allmight init` (always
   user-opt-in); don't omit the `am-` prefix.
7. **(Forward reference, marked deferred)** — when T2 ships, this
   skill gets a §3.5 about the declarative `scheduled/` dir; until
   then a stub line says "the agent may create files in
   `personalities/<active>/scheduled/<task>.md` but allmight does
   not yet read them — manual sync only".

### 3.3 Test surface

```
tests/test_schedule_capability.py
├── test_template_registers                     — TEMPLATE in core.personalities registry
├── test_install_globals_writes_skill           — .opencode/skills/scheduling/SKILL.md exists
├── test_install_creates_empty_personality_dir  — personalities/<p>/scheduled/ is a real empty dir
├── test_skill_has_marker                       — ALLMIGHT_MARKER_MD present
├── test_skill_describes_slug_convention        — body contains "am-<personality>-"
└── test_no_claude_hook_emitted                 — no .claude/hooks/schedule*.py file
```

The last test is the negative assertion required by CLAUDE.md's
*Discipline When Generating Third-Party Integrations* rules.

### 3.4 Acceptance criteria for T1

- `allmight init` in an empty directory produces
  `.opencode/skills/scheduling/SKILL.md` with the
  `ALLMIGHT_MARKER_MD` token.
- `allmight add stdcell_owner --capabilities database,memory,schedule`
  creates `personalities/stdcell_owner/scheduled/` (empty).
- `personalities.yaml` lists `schedule` under the personality's
  capabilities.
- `pytest tests/test_schedule_capability.py` is green.
- No new entries in `PLUGIN_MANIFEST` (T1 ships no plugin).
- Agent in an OpenCode session, asked "set up a weekly poster
  search at 9am", produces a `schedule_job` MCP call with slug
  `am-<personality>-poster-search` and cron `0 9 * * 1`.

### 3.5 What T1 does NOT include

- No `apply.py`. No CLI subcommands.
- No `scheduled/<task>.md` file format validation.
- No marker-file plugin.
- No `/one-for-all` integration.
- No schema probe.

These all land in T2.

---

## 4. T2 milestone — declarative state + apply + schema check + sync

### 4.1 Files written

```
src/allmight/capabilities/schedule/
├── apply.py                                    — reconciliation + schema probe (new)
├── format.py                                   — load_task_file(path) → TaskDecl; ALLMIGHT_MARKER_MD
├── scope.py                                    — derive opencode-scheduler scopeId from project root
└── templates/
    └── examples/curator-audit.md               — example task file shipped as documentation

src/allmight/capabilities/schedule/cli_options.py
                                                — registers `schedule` subgroup with apply/status
                                                  via the existing cli_options machinery
                                                  (compliant with "cli.py is closed against templates")

src/allmight/capabilities/schedule/plugin_template.py
                                                — emits .opencode/plugins/schedule-sync.ts
                                                  (no Claude Code mirror, per P-6)

src/allmight/core/plugin_telemetry.py           — append PLUGIN_MANIFEST entry for schedule-sync
                                                  with claude_code_mirror=None

src/allmight/capabilities/database/one_for_all_skill_content.py
                                                — add `schedule` row to the per-capability
                                                  export table (P-2 file format is portable)
src/allmight/capabilities/database/all_for_one_skill_content.py
                                                — add `schedule` row: merge by task name,
                                                  conflict dialog identical to ROLE.md prose
```

### 4.2 `personalities/<p>/scheduled/<task>.md` format

```yaml
---
# ALLMIGHT_MARKER_MD: scheduled-task v1
name: curator-audit
description: Weekly audit of shared memory _inbox/ entries
cron: "0 9 * * 1"                # 5-field, vixie-cron
timeout_seconds: 1800            # optional, default 1800 (30 min)
permission_mode: deny            # opencode-scheduler default; rarely overridden
---

Walk `personalities/*/memory/_inbox/` for the current personality.
For each file: …  (the prompt body, exactly as the agent would
read it via /loop or schedule_job)
```

Versioning the marker (`v1`) lets future format changes detect
old files and refuse-with-message instead of silently
mis-applying.

### 4.3 `apply.py` flow

```
allmight schedule apply [--dry-run] [--personality <name>]
```

1. Discover. Walk `personalities/*/scheduled/*.md`. Parse each via
   `format.load_task_file`. Compute target slug
   `am-<personality>-<task>` (P-3).
2. Schema probe (P-5):
   a. Derive `scopeId` for the project root via `scope.py` (matches
      `opencode-scheduler`'s normalisation rule — read its source
      file to pin the algorithm).
   b. List `~/.config/opencode/scheduler/scopes/<scopeId>/jobs/*.json`.
   c. If any exist: read one; assert its top-level field set
      equals `KNOWN_SHAPE_V1`. On mismatch:
      ```
      ERROR: opencode-scheduler job state at <path> has fields
        unexpected={…} missing={…}.
        This usually means opencode-scheduler has been upgraded to
        a version All-Might has not been tested against.
        Run `bun pm ls opencode-scheduler` and pin to a known-good
        version, or open an issue at <repo>.
      ```
      Abort.
   d. If empty: write `__allmight_probe__.json` with
      `KNOWN_SHAPE_V1`, prompt user to run `opencode` and check
      that the `list_jobs` MCP tool sees it, then delete on
      confirmation. (One-time setup ritual; subsequent applies
      skip this branch.)
3. Reconcile.
   - For each declared file: write
     `~/.config/opencode/scheduler/scopes/<scopeId>/jobs/<slug>.json`.
     Set fields per `KNOWN_SHAPE_V1`. Include an `am_managed: true`
     field so `cleanup_global` etc. can distinguish.
   - List existing `am-*` jobs on disk. Any without a matching
     declaration is an orphan — delete (after one-line user
     prompt unless `--yes`).
4. Trigger backend re-read. `opencode-scheduler` watches its state
   dir via `fs.watch` — writes propagate automatically. Verify by
   `stat`-ing the launchd plist / systemd unit that gets emitted;
   if missing within 2 s, instruct the user to restart OpenCode
   once. (One-time race, then steady-state.)
5. Print summary. Created N, updated M, deleted O, untouched P.

### 4.4 `KNOWN_SHAPE_V1`

Pinned by reading `opencode-scheduler`'s
[src/index.ts](https://github.com/different-ai/opencode-scheduler/blob/main/src/index.ts)
at implementation time. Likely fields (to be verified):

```python
KNOWN_SHAPE_V1 = frozenset({
    "slug", "cron", "prompt", "workdir",
    "timeoutSeconds", "permissionMode",
    "createdAt", "updatedAt",
})
```

**Verification step before merge**: open the latest tagged release
on GitHub, read the field set actually written by `schedule_job`,
update `KNOWN_SHAPE_V1` to match. Do not guess — this is the
*"verify the API on one file before propagating"* rule from
CLAUDE.md.

### 4.5 `schedule-sync.ts` (OpenCode plugin)

Pattern lifted directly from `memory-history.ts` + `memory-load.ts`:

```ts
// On Stop hook: if any personalities/*/scheduled/*.md is newer
// than .allmight/schedule.pending → touch the marker.
// On session.created: if marker exists, do NOT auto-apply (writes
// could be destructive); instead inject a one-line nudge into the
// session: "Schedule declarations are newer than runtime state.
// Run `allmight schedule apply` to reconcile." Then clear marker
// on next /chat.message? No — clear only after a successful apply,
// detected by mtime of one runtime json file.
```

Heartbeat snippet inlined (per CLAUDE.md plugin observability
rules). Register in `KNOWN_OPENCODE_PLUGINS`.

### 4.6 `/one-for-all` and `/all-for-one` integration

Add to the per-capability table in
`one_for_all_skill_content.py`:

| Capability | Path | Action |
|---|---|---|
| `schedule` | `scheduled/*.md` | **Export** (no PII review needed — content is the same prompt the user wrote) |

In `all_for_one_skill_content.py`:

| Capability | Path | Action |
|---|---|---|
| `schedule` | `scheduled/<task>.md` | **Merge by task name.** Conflict ⇒ same per-file dialog already used for `memory/understanding/`. ROLE.md prose reconciliation pattern applies for the task body. |

After import, `/all-for-one` must instruct the user to run
`allmight schedule apply` to materialise the new tasks to runtime.

### 4.7 CLI registration without violating "cli.py is closed against templates"

Add `cli_options` extension that registers a *subgroup* not a top-level
command on the `init` command. Pattern check needed against
`core/personalities.py::Template.cli_options`. If subgroup registration
isn't supported by the existing surface, the alternative is to add
exactly one new top-level `schedule` group in `cli.py` that delegates
to a callable provided by the schedule capability — this is a
narrowly-scoped exception, matching the existing precedent of
`allmight memory ...` (also a top-level group registered in `cli.py`).

**Decision deferred to implementation**: pick whichever path mirrors
how `allmight memory` is wired today. Read the current code; don't
invent a new mechanism.

### 4.8 Test surface (additions to T1's)

```
tests/test_schedule_apply.py
├── test_dry_run_lists_actions
├── test_apply_writes_known_shape_to_scope_dir
├── test_schema_probe_detects_unknown_fields    — synthesises a
│                                                   bogus job json,
│                                                   asserts apply
│                                                   refuses with clear
│                                                   message
├── test_canary_path_on_empty_scope
├── test_orphan_deletion_with_prompt
├── test_orphan_deletion_with_yes_flag
├── test_slug_collision_is_rejected             — two task files
│                                                   resolving to the
│                                                   same slug across
│                                                   personalities
└── test_personality_filter_scope               — --personality <name>
                                                   only touches that
                                                   personality's slugs

tests/test_schedule_plugin.py
├── test_plugin_emits_with_heartbeat
├── test_plugin_writes_marker_when_files_newer
├── test_plugin_clears_marker_after_apply
└── test_no_claude_hook_emitted                 — PLUGIN_MANIFEST entry
                                                   has claude_code_mirror=None

tests/test_one_for_all_includes_schedule.py
├── test_bundle_includes_scheduled_dir
├── test_bundle_excludes_runtime_state          — never bundle from
                                                   ~/.config/opencode/
                                                   scheduler/

tests/test_all_for_one_merges_schedule.py
├── test_disjoint_task_sets_merge_cleanly
├── test_same_slug_triggers_dialog
```

### 4.9 Acceptance criteria for T2

- All T1 criteria still hold.
- `allmight schedule apply --dry-run` on a project with two
  personalities + three tasks prints the expected diff.
- `apply` on a fresh machine writes runtime state, OpenCode picks
  it up after restart, `schedule_job`-style `list_jobs` shows the
  am-prefixed jobs.
- Schema probe fails cleanly when fed a synthetic mismatched job
  file; never half-writes.
- `/one-for-all` bundle round-trip via `/all-for-one` on another
  project preserves all `scheduled/<task>.md` files; running
  `apply` there reproduces the same jobs.
- `schedule-sync.ts` heartbeat appears under
  `.allmight/plugins/heartbeats/oc/schedule-sync` after one session.
- Generated TS type-checks: `tsc --noEmit --skipLibCheck
  .opencode/plugins/schedule-sync.ts` clean (CLAUDE.md rule).

---

## 5. Non-goals (explicit cut lines)

| Cut | Why |
|---|---|
| Self-rescheduling tasks (Anthropic's `update_scheduled_task` MCP) | L3 ingest closure already covers reactive freshness. Defer until concrete need. |
| Claude Code mirror | Anthropic Desktop scheduled tasks already covers CC persistent scheduling. Mirror = duplication. |
| Wrapping launchd / systemd / cron directly | T3 rejected. We own declarations, runtime is `opencode-scheduler`. |
| `allmight schedule add / rm / edit` CLI | Declarative-first; edits happen in `personalities/<p>/scheduled/<task>.md`. |
| Sub-minute intervals | `opencode-scheduler` floor is 1 min; we don't beat that. |
| Triggering on events (webhooks, Sentry, GitHub) | `background-agents` does this; out of scope for All-Might. |
| `/curator-audit` slash command itself | Wait for user demand; the skill can reference it abstractly. |

---

## 6. Risk register

| # | Risk | Mitigation | Severity if hit |
|---|---|---|---|
| R-1 | `opencode-scheduler` changes its JSON shape between releases | Schema probe (P-5) aborts before write; `KNOWN_SHAPE_V1` pinning + clear error. | Low — agent loses scheduling temporarily until shape pinned. |
| R-2 | OpenCode lands native scheduling (#11232) mid-T2 | T2's `apply.py` is the integration point; switch its backend from `opencode-scheduler` state files to native API. Other layers (declarative format, plugin, OFA integration) survive. | Low. |
| R-3 | `opencode-scheduler` not installed in target project | `apply.py` detects missing scope dir; prints install hint pointing to plugin's README. | Low — bypass path documented. |
| R-4 | User runs `apply` from wrong cwd, hitting a different scope | Scope derivation (`scope.py`) keys off `personalities.yaml` location, not `os.getcwd()`. Tests pin this. | Medium — pinned by test. |
| R-5 | OFA bundle export accidentally includes prompts with secrets | The task body is a prompt the user authored; same PII review the rest of `/one-for-all` does already applies. No new attack surface, but skill must remind. | Low. |
| R-6 | Two personalities declare same task name → same slug under different personalities (impossible because slug includes personality), but across the *same* personality two task files with same `name:` frontmatter still collide | `format.load_task_file` rejects duplicate `name` per personality at parse time. Test covers. | Low. |
| R-7 | `apply` produces an orphan flood after a personality is renamed | One-time prompt + `--yes` flag for bulk delete; doc the rename path. | Low. |

---

## 7. Sequencing & estimates

| Phase | Calendar | Effort | Gate |
|---|---|---|---|
| T1 implementation | half day | ~200 LOC + ~5 tests | Acceptance §3.4 |
| T1 land + verify in a real project | half day | manual: `allmight init` → `allmight add stdcell --capabilities schedule,memory,database` → start an OpenCode session → ask agent to "schedule X" → verify it emits the expected MCP call | Smoke OK |
| **Stop-loss checkpoint** | — | re-evaluate based on actual usage; T2 only if portability or in-tree-source-of-truth feels missing | go/no-go for T2 |
| T2 implementation | 2–3 days | ~700 additional LOC + ~15 tests | Acceptance §4.9 |
| T2 land + dogfood (run schedule on a real personality for 1 week) | 1 week | observation only | Heartbeat + one full apply→fire→complete cycle |

Total budget if both ship: ~900 LOC + ~20 tests, spread over
roughly one calendar week of focused work.

---

## 8. Open questions for implementation phase (not blockers for plan
   approval)

- Exact `KNOWN_SHAPE_V1` field set — read `opencode-scheduler`
  source at implementation time, do not guess.
- `scope.py` normalisation algorithm — must byte-match what
  `opencode-scheduler` computes; read its source.
- `cli.py` integration shape — match how `allmight memory` is
  registered today; do not invent.
- Whether `schedule-sync.ts` should warn or block when the project
  has no `opencode-scheduler` plugin installed — propose: warn
  once per session, never block.
- Whether T2 should also ship one example pre-installed task
  (`templates/examples/curator-audit.md`) the user can copy, or
  keep `scheduled/` empty until the user fills it — propose:
  copy is opt-in via a CLI flag deferred to T3-or-later.

---

## 9. Approvals required before T1 starts

- [ ] User confirms P-1 through P-8 (or proposes specific changes).
- [ ] No outstanding "redirect" in chat; otherwise this plan is
      stale and must be re-drafted before implementation.
