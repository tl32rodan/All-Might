# Scheduling — periodic All-Might work

## When to invoke

Trigger phrases include: "schedule", "automate", "run every <N>",
"every Monday/morning/week", "remind me at <time>", "set up a
periodic <X>", "cron", "background job", "babysit".

If the user says only *"just schedule it"*, ask **two** questions
before acting:

1. **Persistence**: must it survive after the current OpenCode
   session ends? (governs runtime choice — see matrix below)
2. **Machine-on requirement**: is it OK if it only fires while
   the user's laptop is awake? (cloud runtime is the only
   "always-on" option)

## Runtime matrix

| Runtime | When to pick | Persistence | Min interval | Where state lives |
|---|---|---|---|---|
| **OpenCode + `opencode-scheduler` plugin** (default for OpenCode projects) | Persistent, machine-on; the user runs OpenCode and wants the cadence to outlive any single session. | OS scheduler unit (launchd / systemd / cron / schtasks) | 1 min | `~/.config/opencode/scheduler/scopes/<scopeId>/jobs/*.json` |
| **Claude Code `/loop`** (CC users) | Throwaway polling during one CC session — "ping me when the build finishes". | Session-only; restored ≤7d via `claude --resume`. | 1 min | Session JSON |
| **Claude Code Desktop scheduled tasks** (CC users with the Desktop app) | Persistent, machine-on, CC user. | App daemon | 1 min | `~/.claude/scheduled-tasks/<task>/SKILL.md` |
| **External cron / systemd / launchd** | The user explicitly wants a non-Claude runtime, or the work is not a prompt at all. | OS scheduler | 1 min | OS-specific |

For an All-Might project running on OpenCode (the canonical
surface), the default answer is **opencode-scheduler**.

## Detecting the plugin

The `opencode-scheduler` plugin is opt-in. Detect it by checking
the project's `opencode.json` for an entry like:

```json
{
  "plugin": ["opencode-scheduler"]
}
```

If the entry is absent, tell the user **once**:

> Scheduling needs the `opencode-scheduler` plugin. Install it by
> adding `"plugin": ["opencode-scheduler"]` to `opencode.json` and
> restarting OpenCode. Until then I can only suggest cron lines.

Do **not** auto-edit `opencode.json` — third-party plugin
installation is an explicit user action.

## Slug discipline (non-negotiable)

Every job All-Might creates uses the slug

```
am-<personality>-<task>
```

- `am-` prefix marks it as All-Might-owned (so the user can
  distinguish All-Might jobs from their own on the same scope).
- `<personality>` is the **active personality** at the moment the
  job is created — see the `ROUTING_PREAMBLE` rules in every
  command body for how to resolve `<active>`.
- `<task>` is a short kebab-case description.

Examples: `am-stdcell_owner-sidecar-sweep`,
`am-code_reviewer-pr-poll`, `am-pll_owner-l3-size-check`.

Reject any agent-proposed schedule whose slug omits the `am-`
prefix — those collide with user-managed jobs on the same scope.

## Calling `schedule_job` (opencode-scheduler MCP tool)

The plugin exposes 11 MCP tools. The four you reach for in
normal use:

- `schedule_job({slug, cron, prompt, timeoutSeconds?, permissionMode?})`
- `list_jobs()` — filter results client-side by `am-` prefix
- `delete_job({slug})`
- `run_job_now({slug})` — manual fire-and-forget for testing

Cron is standard 5-field vixie-cron:

| Example | Meaning |
|---|---|
| `*/15 * * * *` | every 15 min |
| `0 9 * * *` | daily at 09:00 local |
| `0 9 * * 1` | weekly Monday 09:00 |
| `0 9 1 * *` | monthly on the 1st at 09:00 |

The prompt body should be self-contained: when the schedule fires,
a fresh OpenCode session starts; no conversational context survives.
Write it the way you would write the contents of a `/loop` prompt.

`timeoutSeconds` defaults to 1800 (30 min); set higher only when
the work is genuinely long-running.

`permissionMode` defaults to `deny` on scheduled runs (set by
`opencode-scheduler` itself via `OPENCODE_PERMISSION`) so the job
does not hang on a permission prompt. Override only with explicit
user consent.

## All-Might cadence catalogue (recommendations)

Use these as starting points when the user asks "what should we
schedule?". Each is per-personality; multiply by the number of
personalities that own that concern.

| Concern | Suggested slug | Cron | Prompt sketch |
|---|---|---|---|
| Curator audit of shared memory `_inbox/` | `am-<p>-curator-audit` | `0 9 * * 1` (weekly Mon 09:00) | "Walk `personalities/<p>/memory/_inbox/`. For each file: decide keep / promote / discard following the rules in `docs/team-share.md`. Report changes." |
| Plugin observability roll-up | `am-<p>-plugin-status` | `0 9 * * 1` (weekly) | "Run `allmight plugin status`. Summarise: which plugins never fired this week; flag any > 14 days stale." |
| L3 size sanity (per `docs/plan.md` thresholds) | `am-<p>-l3-size-check` | `0 9 1 * *` (monthly) | "Walk `personalities/<p>/memory/journal/`. If total > 50 MB or > 5000 files, propose archiving the oldest year." |

These are recommendations, not auto-installed jobs. T1 of the
schedule capability does NOT materialise them; the user (or you,
when asked) calls `schedule_job` per cadence as needed.

## Anti-patterns

- **Don't schedule L3 ingest.** The reactive marker-file closure
  (`memory-history.ts` + `memory-load.ts`) already keeps the SMAK
  index fresh on every session start. A scheduled L3 ingest
  duplicates work and obscures the closure.
- **Don't schedule from `allmight init`.** Scheduling is always
  user-opt-in. A fresh `allmight init` must produce zero jobs.
- **Don't omit the `am-` prefix.** Collides with user-managed jobs.
- **Don't schedule sub-minute work.** `opencode-scheduler`'s floor
  is 1 minute; below that, look at the OpenCode `Monitor` /
  in-session loops instead.
- **Don't schedule one-shot reminders here.** For "remind me at
  3pm", `/loop` (CC) or `at` (Unix) is lighter than registering a
  full cron entry; explain the alternative and let the user pick.

## Forward reference (deferred to T2)

This skill currently teaches the agent to call
`opencode-scheduler` MCP tools directly. A later milestone (T2,
tracked in `docs/schedule-proposal.md`) introduces a **declarative**
flow in which the agent writes a
`personalities/<active>/scheduled/<task>.md` file in the project
repo and runs `allmight schedule apply` to materialise it to the
runtime. Until that milestone ships:

- The agent **may** create files at
  `personalities/<active>/scheduled/<task>.md` for the user's
  reference, but All-Might does not yet read or apply them.
- The runtime source of truth is **only** the
  `opencode-scheduler` state directory.
- Manual sync (call the MCP tools) is required.

When T2 ships, this section is replaced with the declarative
workflow.
