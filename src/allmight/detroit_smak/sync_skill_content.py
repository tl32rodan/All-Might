"""Bundled /sync skill and command content.

Installed when ``allmight init`` detects a re-init or after
``allmight merge``.  Teaches the agent how to reconcile staged
templates or incoming workspaces with existing files.
"""

SYNC_SKILL_BODY = """\
# Sync — Reconcile Staged Changes

> Run this skill after `allmight init` (re-init) or `allmight merge`
> to merge new templates or incoming workspaces with your current files.

## When to use

- After `allmight init` on an already-initialized project
  (templates are staged in `.allmight/templates/`)
- After `allmight merge <source>` when conflicts exist
  (merge report at `.allmight/merge-report.yaml`)

## How it works

### Template sync (after re-init)

1. List all files in `.allmight/templates/`
2. For each staged file, find the corresponding working file:
   - `.allmight/templates/commands/search.md` → `.claude/commands/search.md`
   - `.allmight/templates/hooks/memory-nudge.sh` → `.claude/hooks/memory-nudge.sh`
   - `.allmight/templates/claude-md-section.md` → `CLAUDE.md` (within `<!-- ALL-MIGHT -->` markers)
   - `.allmight/templates/memory-md-section.md` → `CLAUDE.md` (within `<!-- ALL-MIGHT-MEMORY -->` markers)
   - `.allmight/templates/opencode.json` → `.opencode/opencode.json`
   - `.allmight/templates/memory-load.ts` → `.opencode/plugins/memory-load.ts`
3. Compare staged vs. working file:
   - **Identical or nearly identical**: overwrite working file with staged version
   - **User has meaningful customizations**: merge — keep user customizations,
     incorporate new template changes. Present a summary to the user.
4. For CLAUDE.md section files (`claude-md-section.md`, `memory-md-section.md`):
   - Replace only the content between the markers (`<!-- ALL-MIGHT -->`, `<!-- ALL-MIGHT-MEMORY -->`)
   - Never touch content outside the markers
5. After all files are merged, delete `.allmight/templates/`

### Mode-aware cleanup (after mode change)

If `.allmight/mode` exists, check whether the project's access mode has changed:

1. Read `.allmight/mode` to determine the current access mode (`read-only` or `writable`)
2. If `.allmight/templates/remove.txt` exists:
   - Read the list of command files to remove (one filename per line)
   - Delete each listed file from `.claude/commands/`
   - Delete `remove.txt` when done
3. Verify only commands appropriate for the current mode remain:
   - **read-only**: only `search.md` (remove `enrich.md`, `ingest.md` if present)
   - **writable**: `search.md`, `enrich.md`, `ingest.md`
4. Update the CLAUDE.md ALL-MIGHT section to match the staged `claude-md-section.md`

### Merge conflict resolution (after `allmight merge`)

1. Read `.allmight/merge-report.yaml` for the merge summary
2. For each conflicting workspace (`knowledge_graph/<name>.incoming/`):
   - Compare configs: `<name>/config.yaml` vs `<name>.incoming/config.yaml`
   - Ask the user which indices to keep, merge, or discard
   - Apply the decision and remove the `.incoming` directory
3. For each conflicting memory file (`memory/understanding/<name>.incoming.md`):
   - Compare with existing `<name>.md`
   - Merge knowledge or ask the user to choose
   - Remove the `.incoming.md` file
4. If the report mentions path warnings, review and fix paths in config.yaml
5. After all conflicts resolved, delete `.allmight/merge-report.yaml`

## File mapping reference

| Staged location | Working location |
|-----------------|-----------------|
| `.allmight/templates/skills/**` | `.claude/skills/**` |
| `.allmight/templates/commands/**` | `.claude/commands/**` |
| `.allmight/templates/hooks/**` | `.claude/hooks/**` |
| `.allmight/templates/claude-md-section.md` | `CLAUDE.md` (ALL-MIGHT marker) |
| `.allmight/templates/memory-md-section.md` | `CLAUDE.md` (ALL-MIGHT-MEMORY marker) |
| `.allmight/templates/opencode.json` | `.opencode/opencode.json` |
| `.allmight/templates/memory-load.ts` | `.opencode/plugins/memory-load.ts` |

## Important

- **MEMORY.md** is never staged or overwritten — it is agent-writable
- **Hook scripts** may need `chmod +x` after merging
- After syncing, run `/ingest` if workspace configs changed
- This skill handles both init-update and merge conflicts — same workflow
"""

SYNC_COMMAND_BODY = """\
Merge staged All-Might templates or resolve merge conflicts.

Run after `allmight init` (re-init) or `allmight merge` to reconcile
new templates with your customized files.

## What happens

1. Reads `.allmight/templates/` for staged template updates
2. Reads `.allmight/merge-report.yaml` for merge conflicts
3. For each file: compares staged vs. working, merges intelligently
4. Cleans up staging directory when done

## How to execute

Load the `sync` skill for the full operational guide, then:

1. Read `.allmight/templates/` to see what changed
2. For each file, compare with your working copy
3. Merge user customizations with new template content
4. Delete `.allmight/templates/` when done

If `.allmight/merge-report.yaml` exists, also resolve workspace and
memory conflicts listed in the report.
"""
