"""Bundled /sync skill and command content.

Installed when ``allmight init`` detects a re-init (existing
``.allmight/`` dir).  Teaches the agent how to reconcile staged
templates with existing files, how to recover anything ``init``
retired into ``.allmight/attic/``, and how to resolve compose
conflicts where the user authored a file All-Might also wanted to
write.
"""

SYNC_SKILL_BODY = """\
# Sync — Reconcile Staged Changes

> Run this skill after `allmight init` (re-init) to merge new
> templates with your current files.

## When to use

- After `allmight init` on an already-initialized project (templates
  staged in `.allmight/templates/`)
- After init reports **compose conflicts** — you authored a file
  All-Might also wanted to write (`.allmight/templates/conflicts.yaml`)
- After init reports **retired** files (moved to `.allmight/attic/`)
- After init warns that a `.claude/` entry you own shadows ours
- To register **orphan personalities** — a `personalities/<name>/`
  with a `ROLE.md` but no row in `.allmight/personalities.yaml`
  (copied in from another project, or created out-of-band)

## Template sync

1. List `.allmight/templates/` and map each staged file to its
   working location (table at the end of this skill).
2. **Check ownership before merging.** Read the working file's first
   lines and look for `<!-- all-might generated -->` (markdown) or
   `// all-might generated` (TypeScript). No marker means the user
   authored it — do **not** overwrite or merge; name the file and ask
   whether to keep theirs or take ours.
3. For files that are ours (or absent): identical → copy the staged
   version over; meaningfully customised → merge, keeping the user's
   changes, and summarise what you did.
4. Delete `.allmight/templates/` once every staged file is resolved.

## AGENTS.md — fence semantics

All-Might owns **only** the region between `<!-- ALL-MIGHT:BEGIN -->`
and `<!-- ALL-MIGHT:END -->`. Everything outside it is the user's and
survives every recompose automatically.

- Never move user prose inside the fence, and never hand-edit inside
  it: `allmight compose` regenerates that region from
  `personalities/*/ROLE.md`. To change what it says, edit the ROLE.md.
- `.allmight/templates/AGENTS.md` is staged **only** when the file
  carries an `ALL-MIGHT:OFF` comment (the opt-out). Show the user the
  staged block; if they want it live, remove the OFF marker and run
  `allmight compose`.
- `.allmight/templates/AGENTS.md.prev` is a backup taken when a
  pre-fence AGENTS.md had to be rewritten. Diff it against the live
  file, restore any of the user's prose the migration dropped (place
  it *outside* the fence), then delete the `.prev`.

## Retired files (`.allmight/attic/`)

`allmight init` never deletes. Marker-carrying files the framework no
longer ships (renamed plugins, retired commands) are **moved** to
`.allmight/attic/<original path>`.

Show the user what is in the attic. A fork of one of our plugins keeps
our marker, so their work can land here by mistake — if they want one
back, move it out under a name of their own and strip the
`// all-might generated` line so the next init leaves it alone:

```bash
mv .allmight/attic/.opencode/plugins/<name>.ts .opencode/plugins/<their-name>.ts
```

Otherwise leave the attic alone. It is a recovery bin, not clutter.

## Deprecated-command cleanup

`.allmight/templates/remove.txt` lists commands the framework retired
— `enrich.md` and `ingest.md` (the knowledge graph is read-only from
the agent surface; SMAK handles ingest out-of-band). For each
filename: remove `.opencode/commands/<name>` **only if it carries our
marker**. A same-named file the user wrote is theirs — leave it and
say so. Delete `remove.txt` when done.

## Claude Code surface clashes

`.claude/commands` and `.claude/skills` are normally directory
symlinks into `.opencode/`. When the user already owns a real
directory there, init links our entries in one by one and reports the
names it could not claim. For each reported path: show both versions
and ask whether to rename theirs (then re-run `allmight init` to link
ours) or keep theirs and drop ours. Never delete a user file here.

Note the per-entry fallback is a snapshot — a command added later
needs another `allmight init` to appear on the Claude Code side.

## Orphan personality reconciliation

A `personalities/<name>/` missing from `.allmight/personalities.yaml`
still gets its `ROLE.md` injected every turn, but `allmight list` and
`AGENTS.md` ignore it. Reconciliation reuses `allmight add --force` —
there is no separate command, and it is **additive only**: `ROLE.md`,
memory data, `STATUS.md` and workspace configs all carry write-once
guards, so nothing you wrote is overwritten. What it actually does is
append the registry row, recompose `AGENTS.md`, and write
`.opencode/agents/<name>.md`.

1. Compare `allmight list` against `ls personalities/`.
2. For each orphan with a `ROLE.md`, infer capabilities from the
   subdirs present (`database/`, `memory/`). Skip directories with no
   `ROLE.md` or no capability subdir — they are not personalities.
3. Snapshot first so any surprise is recoverable:
   `allmight memory snapshot --message "before reconcile <names>"`
4. Show the user the list with detected capabilities and confirm.
5. `allmight add --force <name> --capabilities <list>` for each.
6. Run `allmight list` and report which were registered.

Reconciliation never removes registry entries whose directory is
gone; to prune those, edit `.allmight/personalities.yaml` directly.

## Compose conflicts (`.opencode/` entries you authored)

`allmight init` never overwrites a `.opencode/<kind>/<name>` you wrote
yourself. It leaves your file alone and lists every skipped target in
`.allmight/templates/conflicts.yaml`:

```yaml
compose_conflicts:
  - instance: stdcell_owner          # who wanted to install this
    kind: commands                   # skills | commands
    basename: search.md
    dst: .opencode/commands/search.md       # what currently exists
    source: personalities/stdcell_owner/commands/search.md
    existing: file                   # file | directory | symlink-to-elsewhere
```

For each entry, read both files (`dst` and `source`), then:

- **Keep yours** — leave `dst` alone and drop the entry.
- **Take ours** — delete `dst`, then
  `ln -sfn ../../<source> <dst>` (target relative to `dst`'s parent).
- **Merge** — splice your changes into the All-Might version, write
  the result back to the **source** file, then symlink as above so
  future re-inits keep your merged content.

Delete `conflicts.yaml` once every entry is resolved.

`existing: symlink-to-elsewhere` is a hand-rolled link of yours —
treat it like `file`. `existing: directory` means a non-All-Might
directory sits at our target; inspect it before touching anything.

## Personality agent files (`.opencode/agents/<name>.md`)

One OpenCode subagent file per personality, regenerated on every
add/import. It is a thin pointer —
`prompt: "{file:../personalities/<name>/ROLE.md}"` — so ROLE.md stays
the single source of truth.

- **You only edited ROLE.md** (typical): drop your working file and
  take the staged version.
- **You customised the agent file itself**: merge the staged
  frontmatter into yours, keeping extra fields (`model`, `tools`, …),
  and keep one `<!-- all-might generated -->` line so the next re-init
  recognises ownership.

## File mapping reference

| Staged location | Working location |
|-----------------|-----------------|
| `.allmight/templates/skills/**` | `.opencode/skills/**` |
| `.allmight/templates/commands/**` | `.opencode/commands/**` |
| `.allmight/templates/agents/<name>.md` | `.opencode/agents/<name>.md` |
| `.allmight/templates/<name>.ts` | `.opencode/plugins/<name>.ts` |
| `.allmight/templates/opencode.json` | `.opencode/opencode.json` |
| `.allmight/templates/{claude,memory}-md-section.md` | `AGENTS.md`, inside the fence |
| `.allmight/templates/AGENTS.md` | staged composition (opt-out only) |
| `.allmight/templates/AGENTS.md.prev` | backup of a pre-fence `AGENTS.md` |
| `.allmight/templates/conflicts.yaml` | manifest of skipped compose targets |
| `.allmight/templates/remove.txt` | commands to retire (marker-gated) |

## Important

- **MEMORY.md** is never staged or overwritten — it is agent-writable.
- `.claude/` is a **generated bridge** (settings.json, hooks, dir
  symlinks), not legacy cruft. Do not delete it.
- If workspace configs changed, rebuild the SMAK index out-of-band
  via `smak ingest`.
"""

SYNC_COMMAND_BODY = """\
Merge staged All-Might templates with your customized files.

Run after `allmight init` on an already-initialized project to
reconcile new templates.

## What happens

1. Reads `.allmight/templates/` for staged template updates
2. For each file: compares staged vs. working, merges intelligently
3. Reports anything `init` retired into `.allmight/attic/`
4. Cleans up staging directory when done

## How to execute

Load the `sync` skill for the full operational guide, then:

1. Read `.allmight/templates/` to see what changed
2. For each file, compare with your working copy
3. Merge user customizations with new template content
4. Delete `.allmight/templates/` when done
"""
