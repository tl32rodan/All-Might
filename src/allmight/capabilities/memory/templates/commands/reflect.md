Structured self-reflection to keep memory accurate and tidy.

Run periodically: end of session, after major work, when the
sentinel `memory/.l1-over-cap` exists, or when the user asks you to
consolidate what you learned.

For single-observation persistence (the default `/remember` flow):
use `/remember`, not this command.

## 1. Review L1 — MEMORY.md

Read `MEMORY.md` at project root. Is the Project Map still accurate?
Are Active Goals current? Any Key Facts stale or wrong? Update
directly.

## 2. Review L2 — Understanding

For each workspace you worked on this session, read
`memory/understanding/<workspace>.md`. Did you learn new architecture
details, a debug SOP, or a gotcha? Add them. Create the file if it
doesn't exist yet.

## 3. Audit per-corpus scoping

List `memory/`. Check each file is scoped correctly:

- Anything in `MEMORY.md` that's really about one workspace?
  Move it to `memory/understanding/<workspace>.md`; leave at most a
  one-line pointer in `MEMORY.md`.
- Any `memory/journal/general/` entry that's actually
  workspace-specific? Move it under `memory/journal/<workspace>/`.
- Any ad-hoc `memory/<kind>/<workspace>.md` you (or a past session)
  created? Confirm names follow `<kind>/<workspace>.md`.

## 4. L1 cap triage (only if `memory/.l1-over-cap` exists)

`MEMORY.md` grew past its byte cap. Triage without waiting:

1. Classify each line: **portable** (keep in L1) / **corpus-specific**
   (move to `understanding/`) / **open TODO** (move to
   `memory/todos/<workspace>.md` or matching `<kind>`).
2. Distill duplicates and stale bullets.
3. Save. The next Stop hook re-audits and removes the sentinel
   automatically when the body is back under cap.

The cap **never silently evicts** — only this step removes content
from L1.

## 5. Log the reflection

Append a journal entry summarising this session's learnings. Use
the v1 frontmatter (mandatory `allmight_journal: v1` sentinel):

```markdown
---
allmight_journal: v1
id: <ISO-8601 timestamp + short hash>
type: reflection
workspace: <name-or-general>
trigger: slash_remember_reflect
created_at: <ISO-8601>
---
# <date> — Reflection: <brief title>

<2-3 actionable insights — what to keep, change, or learn next.>
```

Write it under `memory/journal/<workspace>/` or
`memory/journal/general/`.

## 6. Skill check — turn repetition into a skill

If the same multi-step procedure appears twice or more across this
session and the journal entries you just reviewed:

1. Write it to `personalities/<active>/skills/<name>/SKILL.md`
   (frontmatter `name:` + `description:`; body = the steps).
2. Run `allmight compose` to publish it into `.opencode/skills/`.
3. Add a dated bullet to `memory/skills-log.md`. Nothing repeated → skip.

## 7. Re-index if you added journal entries

```bash
smak ingest --config memory/smak_config.yaml
```

(Or rely on the next-session auto-drain — same effect, just delayed
by one session boundary.)
