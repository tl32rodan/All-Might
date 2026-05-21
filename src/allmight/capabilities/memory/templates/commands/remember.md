Persist a single observation. The user said `/remember` — do exactly that.

For periodic memory audits (staleness, scope drift, L1 cap-overflow):
use `/reflect`, not this command.

## Pick the scope

| If the observation… | Write to |
|---|---|
| affects every workspace (env, prefs, goals) | `MEMORY.md` (L1) |
| is workspace-specific knowledge | `memory/understanding/<workspace>.md` (L2) |
| is workspace-specific state (TODOs, notes) | `memory/<kind>/<workspace>.md` |
| is historical / searchable | journal entry (L3) — see below |

**Rule of thumb**: prefer the narrower scope. Workspace beats project,
project beats `journal/general/`. `MEMORY.md` is portable-only — if
it isn't useful in *any* corpus, it doesn't belong there.

## Write

**L1 / L2 / per-kind**: `Edit` the file. Keep entries terse —
one paragraph beats five bullets.

**Journal (L3)**: write a Markdown file under
`memory/journal/<workspace>/` (or `.../general/`) with this v1
frontmatter — the `allmight_journal: v1` sentinel is mandatory so
future tools can parse the entry:

```markdown
---
allmight_journal: v1
id: <ISO-8601 timestamp + short hash>
type: discovery        # one of: discovery | decision | correction | reflection
workspace: <name>      # or: general
trigger: slash_remember
created_at: <ISO-8601>
---
# <date> — <brief title>

<What you learned, in your own words.>
```

## After writing — all four steps, in order

Do NOT stop early. Each step is independent; skipping one breaks
a downstream contract.

1. **Log to `memory/usage.log`**:
   ```
   <ISO-8601> remember scope=<project|workspace> workspace=<name|-> kind=<kind> "<brief>"
   ```

2. **Update STATUS.md** at `personalities/<active>/STATUS.md`:
   - bump `last_activity` in the frontmatter;
   - if the focus changed, rewrite the **Active focus** line;
   - add the topic to **Recent topics** (FIFO ~5, drop oldest);
   - if you opened a long-running thread (a TODO you can't close
     this session), add it to **Open threads**; if you closed one,
     remove it.

3. **Pattern Check** — runs if you wrote a journal entry:
   look at ≤5 most recent same-workspace entries. If a repeated
   theme emerges, promote a one-paragraph rule to
   `memory/understanding/<workspace>.md`. Most calls land "no pattern"
   — that is the correct default. If Pattern Check produces a new L2
   write, step 4 below MUST still run.

4. **L2 Index Refresh** — runs if ANY `understanding/<workspace>.md`
   was written this turn (in the main write step OR by Pattern Check
   above). Regenerate `memory/understanding/_index.md` by scanning
   every `understanding/*.md` and listing its `^## ` headings. Match
   the existing `_index.md` format; if it's missing, see `/recall`
   step 2 for the canonical schema. The index is what makes
   per-workspace L2 loading viable — leaving it stale silently
   degrades `/recall`.

The journal is auto-indexed between sessions — no manual
`smak ingest` needed for `/recall` to find this entry next session.

## What NOT to remember

- Trivial observations re-derivable from code.
- Information already captured elsewhere (sidecar enrichment).
- Temporary debug notes that won't matter next session.

## Lesson Learned (Mode-2 shared instance only)

If this project runs as a team-shared NFS instance, write
curator-audited observations to
`memory/lessons_learned/_inbox/<ISO-8601>-<unix_user>.md` instead of
the canonical L1/L2 surface. The curator later moves audited
entries to `_reviewed/`; the agent only writes to `_inbox/`.
Single-user projects can ignore this section.
