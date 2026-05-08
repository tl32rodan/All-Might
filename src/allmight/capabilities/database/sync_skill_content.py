"""Bundled /sync skill and command content.

Installed when ``allmight init`` detects a re-init (existing
``.allmight/`` dir).  Teaches the agent how to reconcile staged
templates with existing files, and how to resolve compose conflicts
where the user authored a file All-Might also wanted to write.
"""

SYNC_SKILL_BODY = """\
# Sync — Reconcile Staged Changes

> Run this skill after `allmight init` (re-init) to merge new
> templates with your current files.

## When to use

- After `allmight init` on an already-initialized project
  (templates are staged in `.allmight/templates/`)
- After `allmight init` reports `.opencode/` **compose conflicts**
  (manifest at `.allmight/templates/conflicts.yaml`) — you authored a
  file All-Might also wanted to write

## How it works

### Template sync (after re-init)

1. List all files in `.allmight/templates/`
2. For each staged file, find the corresponding working file:
   - `.allmight/templates/commands/search.md` → `.opencode/commands/search.md`
   - `.allmight/templates/claude-md-section.md` → `AGENTS.md` (within `<!-- ALL-MIGHT -->` markers)
   - `.allmight/templates/memory-md-section.md` → `AGENTS.md` (within `<!-- ALL-MIGHT-MEMORY -->` markers)
   - `.allmight/templates/opencode.json` → `.opencode/opencode.json`
   - `.allmight/templates/memory-load.ts` → `.opencode/plugins/memory-load.ts`
3. **Verify the working file is All-Might-owned before merging.**
   Read the working file's first lines and check for one of:
   - `<!-- all-might generated -->` (markdown — commands, SKILL.md)
   - `// all-might generated` (TypeScript — plugins)

   If the working file exists **without** that marker, the user authored
   it (or it pre-existed before All-Might). Do **NOT** merge or
   overwrite — surface a warning naming the file and ask the user
   whether to delete/rename their version or skip this template.
4. If the working file is ours (or doesn't exist), compare staged vs. working:
   - **Identical or nearly identical**: overwrite working file with staged version
   - **User has meaningful customizations**: merge — keep user customizations,
     incorporate new template changes. Present a summary to the user.
5. For AGENTS.md section files (`claude-md-section.md`, `memory-md-section.md`):
   - Replace only the content between the markers (`<!-- ALL-MIGHT -->`, `<!-- ALL-MIGHT-MEMORY -->`)
   - Never touch content outside the markers
6. After all files are merged, delete `.allmight/templates/`

### Mode-aware cleanup (after mode change)

If `.allmight/mode` exists, check whether the project's access mode has changed:

1. Read `.allmight/mode` to determine the current access mode (`read-only` or `writable`)
2. If `.allmight/templates/remove.txt` exists:
   - Read the list of command files to remove (one filename per line)
   - Delete each listed file from `.opencode/commands/`
   - Delete `remove.txt` when done
3. Verify only commands appropriate for the current mode remain:
   - **read-only**: only `search.md` (remove `enrich.md`, `ingest.md` if present)
   - **writable**: `search.md`, `enrich.md`, `ingest.md`
4. Update the AGENTS.md ALL-MIGHT section to match the staged `claude-md-section.md`

### Compose conflicts (`.opencode/` entries you authored)

`allmight init` never overwrites a `.opencode/<kind>/<name>` you wrote
yourself. When it detects one, it leaves your file alone and stages a
manifest at `.allmight/templates/conflicts.yaml` listing every
skipped composition target.

Each entry has:

```yaml
compose_conflicts:
  - instance: <project>-corpus       # who wanted to install this
    kind: commands                   # skills | commands | plugins
    basename: search.md
    dst: .opencode/commands/search.md       # what currently exists
    source: personalities/<project>-corpus/commands/search.md
    existing: file                   # file | directory | symlink-to-elsewhere
```

To resolve each entry:

1. Read both files: `cat <dst>` and `cat <source>`.
2. Decide:
   - **Keep yours, drop ours** — leave `dst` as-is and remove the
     entry from `compose_conflicts`. Optionally delete the unused
     `<source>` if you're sure you don't want it.
   - **Replace yours with ours** — delete `dst`, then create a
     relative symlink:
     ```bash
     ln -sfn ../../<source> <dst>
     ```
     (`<source>` and `<dst>` come from the manifest; the symlink
     target is `<source>` relative to `<dst>`'s parent dir.)
   - **Merge** — splice your customizations into the All-Might
     version, write the merged content back to the **source** file
     (`personalities/<instance>/<kind>/<basename>`), then replace
     `dst` with a symlink as in the previous bullet. Future re-inits
     will then pick up your merged content via the symlink.
3. After resolving every entry, delete
   `.allmight/templates/conflicts.yaml`.

`existing: symlink-to-elsewhere` means `dst` is a symlink that points
somewhere other than the All-Might instance — likely a hand-rolled
link to your own command file. Treat it the same as `existing: file`.

`existing: directory` means `dst` is a non-All-Might directory at our
target. Inspect its contents before deleting; only the user can
decide whether the directory is still wanted.

## File mapping reference

| Staged location | Working location |
|-----------------|-----------------|
| `.allmight/templates/skills/**` | `.opencode/skills/**` |
| `.allmight/templates/commands/**` | `.opencode/commands/**` |
| `.allmight/templates/claude-md-section.md` | `AGENTS.md` (ALL-MIGHT marker) |
| `.allmight/templates/memory-md-section.md` | `AGENTS.md` (ALL-MIGHT-MEMORY marker) |
| `.allmight/templates/opencode.json` | `.opencode/opencode.json` |
| `.allmight/templates/memory-load.ts` | `.opencode/plugins/memory-load.ts` |
| `.allmight/templates/conflicts.yaml` | manifest of skipped compose targets |

## Important

- **MEMORY.md** is never staged or overwritten — it is agent-writable
- After syncing, run `/ingest` if workspace configs changed
- Any legacy `.claude/` directory can be deleted manually once sync is complete
"""

SYNC_COMMAND_BODY = """\
Merge staged All-Might templates with your customized files.

Run after `allmight init` on an already-initialized project to
reconcile new templates.

## What happens

1. Reads `.allmight/templates/` for staged template updates
2. For each file: compares staged vs. working, merges intelligently
3. Cleans up staging directory when done

## How to execute

Load the `sync` skill for the full operational guide, then:

1. Read `.allmight/templates/` to see what changed
2. For each file, compare with your working copy
3. Merge user customizations with new template content
4. Delete `.allmight/templates/` when done
"""
