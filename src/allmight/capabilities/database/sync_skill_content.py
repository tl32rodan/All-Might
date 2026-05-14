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
   - `.allmight/templates/agents/<name>.md` → `.opencode/agents/<name>.md`
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

### Deprecated-command cleanup

1. If `.allmight/templates/remove.txt` exists:
   - Read the list of command files to remove (one filename per line)
   - Delete each listed file from `.opencode/commands/`
   - Delete `remove.txt` when done
2. The legacy slash commands `/enrich` and `/ingest` were retired —
   delete `.opencode/commands/enrich.md` and `.opencode/commands/ingest.md`
   if they are still present. The knowledge graph is now read-only from
   the agent surface; SMAK CLI handles ingest/enrich out-of-band.
3. Update the AGENTS.md ALL-MIGHT section to match the staged `claude-md-section.md`

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
| `.allmight/templates/agents/<name>.md` | `.opencode/agents/<name>.md` |
| `.allmight/templates/claude-md-section.md` | `AGENTS.md` (ALL-MIGHT marker) |
| `.allmight/templates/memory-md-section.md` | `AGENTS.md` (ALL-MIGHT-MEMORY marker) |
| `.allmight/templates/opencode.json` | `.opencode/opencode.json` |
| `.allmight/templates/memory-load.ts` | `.opencode/plugins/memory-load.ts` |
| `.allmight/templates/conflicts.yaml` | manifest of skipped compose targets |

### Personality agent files (`.opencode/agents/<name>.md`)

All-Might emits one OpenCode subagent file per personality. The file
itself is a thin pointer — `prompt: "{file:../personalities/<name>/ROLE.md}"` —
so editing ROLE.md updates the agent's behaviour without re-running
`allmight init`. The agent file is regenerated on every personality
add / import; if you customised `.opencode/agents/<name>.md` directly
(without ROLE.md), the fresh template is staged at
`.allmight/templates/agents/<name>.md` and resolved here:

- **Your customisation matters**: merge the staged frontmatter
  (`description` / `mode` / `prompt`) into your working file, keeping
  any per-agent fields you added (e.g. `model`, `temperature`,
  `tools`). The body comment block is the source of the All-Might
  marker — keep at least one of those `<!-- all-might generated -->`
  lines so the next re-init recognises ownership.
- **You only edited ROLE.md (the typical case)**: drop your working
  file and replace it with the staged version. `ROLE.md` is the
  single source of truth; the agent file is just a frontmatter
  pointer.

## Important

- **MEMORY.md** is never staged or overwritten — it is agent-writable
- If workspace configs changed, rebuild the SMAK index out-of-band via
  the `smak ingest` CLI — All-Might no longer ships an `/ingest` slash command
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
