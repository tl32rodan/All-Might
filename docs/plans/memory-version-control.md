# Plan: memory version control + `/remember` & `/recall` staleness fix

Two scopes, one capability (memory). Order: do the staleness fix first
(text only, fast feedback), then memory VC on top of the cleaned bodies.

## Part A: `/remember` + `/recall` staleness

### Symptom

Both bodies pre-date Part-D. They reference `memory/...` paths as if
memory lived at project root, but in Part-D each personality has its
own `personalities/<active>/memory/`. An agent reading the bodies
cannot tell which personality's memory to operate on. The
`ROUTING_PREAMBLE` is prepended (teaches `<active>` resolution) but
the body itself never uses the `<active>` placeholder.

### Concrete fix — `/remember`

In `_remember_command_body` (memory/initializer.py:803):

| Current | Fixed |
|---|---|
| `memory/understanding/<workspace>.md` | `personalities/<active>/memory/understanding/<workspace>.md` |
| `memory/<kind>/<workspace>.md` | `personalities/<active>/memory/<kind>/<workspace>.md` |
| `memory/journal/<workspace>/…` | `personalities/<active>/memory/journal/<workspace>/…` |
| `memory/lessons_learned/_inbox/...` | `personalities/<active>/memory/lessons_learned/_inbox/...` |
| `memory/.l1-over-cap` | `personalities/<active>/memory/.l1-over-cap` |
| `memory/usage.log` | `personalities/<active>/memory/usage.log` |
| `smak ingest --config memory/smak_config.yaml` | `smak ingest --config personalities/<active>/memory/smak_config.yaml` |
| `MEMORY.md` (project root) | unchanged — L1 is project-wide |
| `AGENTS.md` | unchanged — composed from per-personality ROLE.md, lives at root |

Add a short paragraph clarifying `<workspace>` semantics for the
two personality shapes:

- **Database + memory personality** (e.g. `stdcell_owner`): `<workspace>`
  is the SMAK workspace name from `personalities/<active>/database/`.
- **Memory-only personality** (e.g. `code_reviewer`): no SMAK workspaces
  exist; treat `<workspace>` as a topic slug the agent picks (e.g.
  `code_review`, `release_qa`). Keep `general` for cross-topic notes.

### Concrete fix — `/recall`

Same path-prefix substitutions, plus:

- `ls memory/` → `ls personalities/<active>/memory/`
- `cat memory/<kind>/<workspace>.md` → `cat personalities/<active>/memory/<kind>/<workspace>.md`
- `smak search ... --config memory/smak_config.yaml` →
  `smak search ... --config personalities/<active>/memory/smak_config.yaml`

### Tests

Existing `tests/test_memory_init.py` pins the substrings I'm not
removing (`<kind>/<workspace>.md`, `lessons_learned/_inbox`, `smak
search`, `journal`, `understanding`, `todo`, `scope=`). All substring
asserts still pass after I add the prefix.

Add to `tests/test_command_body_generic.py` (or a new file —
`test_memory_command_routing.py`) two pinning tests:

- `/remember.md` and `/recall.md` bodies must include
  `personalities/<active>/memory/` (the routing-correct prefix), not
  bare `memory/` for data references.
- Both bodies still get the `ROUTING_PREAMBLE` (already pinned by
  `test_routing_preamble.py` — verify it covers these two too; if not,
  extend).

### Out of scope for Part A

- `MEMORY.md`'s own format / cap — that's an L1 concern, not a path-
  prefix concern.
- `lessons_learned/_inbox` directory creation — already done in
  initializer; only the prose mentions it.

---

## Part B: memory version control (誤刪 backup)

### Decisions confirmed

1. **`.git` location**: `.allmight/memory-history/` as a separate bare
   repo. Doesn't collide with the user's project git; doesn't need to
   be ignored (the project's main `.git` doesn't recurse into nested
   `.allmight/memory-history/.git`, but having it under `.allmight/`
   keeps everything All-Might owns under one prefix).
2. **Commit timing**: file watcher (granular) + session-end fallback.
3. **Tracked**: `MEMORY.md` (root), `personalities/*/memory/{understanding,journal,lessons_learned}/**`, `personalities/*/ROLE.md`, `personalities/*/database/*/config.yaml`. Excluded: `personalities/*/memory/store/`, `personalities/*/database/*/store/` (rebuildable derived data).

### Storage layout

```
<project>/
├── .allmight/
│   └── memory-history/             ← non-bare git repo, content tree
│       ├── .git/                   ← the bookkeeping
│       ├── MEMORY.md               ← copies of the tracked files,
│       ├── personalities/          ← mirroring the project's relative
│       │   └── <name>/             ← layout
│       │       ├── ROLE.md
│       │       ├── memory/
│       │       │   ├── understanding/...
│       │       │   ├── journal/...
│       │       │   └── lessons_learned/...
│       │       └── database/<ws>/config.yaml
│       └── .gitignore              ← belt-and-suspenders: refuses store/
└── personalities/...                ← live tree, agent operates here
```

Why mirror instead of repo-at-project-root: the project's main `.git`
already exists in many cases; All-Might tracking the same files would
create a shadow repo and confuse `git status`. Mirror = clean
isolation.

### Commit triggers

**1. File watcher (OpenCode plugin + Claude hook).** Watch the live
paths listed under "Tracked" above. On file write/delete, copy the
file into the mirror and commit with a generated message:

```
auto: <op> <relpath> [(+ N other files)]

triggered_by: <plugin-name>
session_id: <id-if-known>
```

`<op>` ∈ {update, delete, create}. Coalesce writes within a 2 s window
into a single commit so a `/remember` that touches both
`understanding/<ws>.md` and `journal/<ws>/<entry>.md` is one commit,
not two.

**2. Session-end fallback.** On `experimental.session.compacting` and
`session.deleted` (OpenCode) / `Stop` hook (Claude Code), do a final
sync — copy any drift between live and mirror, commit if dirty.
Catches anything the watcher missed (binary edit out-of-band, batch
script, etc.).

### Recovery surface — CLI only, no skill

```
allmight memory log [<personality>] [-n <count>]
    Print commit history. With <personality>, filter to commits that
    touched files under personalities/<name>/.

allmight memory diff <rev> [<file>]
    Show what changed at <rev>. With <file>, narrow to one path
    (live-tree relative — the CLI translates to mirror path).

allmight memory restore <file> [--rev <rev>] [--to <dest>]
    Restore <file> from <rev> (default: last commit before HEAD,
    i.e. one step back) into <dest> (default: the live path).
    Confirms before overwriting an existing file.

allmight memory gc
    Run `git gc` inside the mirror. No-op for normal use; provided
    for hygiene on long-running projects.
```

No `/restore` skill — recovery is mechanical, no judgment to dialog.

### Files touched

#### New

- `src/allmight/capabilities/memory/history.py`
  - `MemoryHistory` class wrapping the mirror repo:
    - `init(project_root)` — create `.allmight/memory-history/.git`,
      seed with current state, write `.gitignore`.
    - `sync(project_root)` — copy live files into mirror, return list
      of changed paths.
    - `commit(project_root, message, *, allow_empty=False)` — runs
      `_run_git` (reuses the `share/git_share.py` signing-bypass
      pattern; or imports `_run_git` directly).
    - `log(project_root, personality=None, n=20)` — return list of
      `Commit` records (sha, ts, message, files).
    - `restore(project_root, relpath, rev, dest)` — checkout one path
      from `<rev>`, copy into `dest`.
  - Reuses `_run_git` from `share/git_share.py` so signing is already
    disabled. (Refactor: pull `_run_git` up to a small `utils/git.py`
    helper module so both `share` and `memory.history` import it
    without one depending on the other.)

- `src/allmight/capabilities/memory/history_skill_content.py`
  - Not strictly needed (no skill), but a short prose file documenting
    the recovery flow for the user. **Skip for now** — README covers
    it.

- `tests/test_memory_history.py`
  - Init creates a non-bare repo with a HEAD commit on `main`
  - Sync copies tracked files; ignores store/ subdirs
  - Commit produces a commit with the expected message format
  - Restore round-trip: edit live, commit, edit again, restore from
    earlier rev → live matches the earlier content
  - `allmight memory log/diff/restore` CLI integration

#### Edited

- `src/allmight/capabilities/memory/initializer.py`
  - `MemoryInitializer.initialize` calls `MemoryHistory.init` once
    (after the rest of memory dir is laid out).
  - **`/remember` body** — the staleness fix from Part A.
  - **`/recall` body** — the staleness fix from Part A.
  - **OpenCode plugin** — new file `memory-history.ts` that watches
    the tracked paths and calls into the bookkeeping. Or extend
    `memory-load.ts` (probably new file — separation of concerns).
  - **Claude Code hook** — sibling Python script
    `memory_history.py` that mirrors the OpenCode plugin (per
    CLAUDE.md's dual-platform invariant).

- `src/allmight/cli.py`
  - New `memory` group already exists (`memory init`, `memory export`).
    Add `log`, `diff`, `restore`, `gc` subcommands that thin-wrap
    `MemoryHistory`.

- `src/allmight/share/git_share.py`
  - If I extract `_run_git` to `utils/git.py`, this file imports from
    there. Otherwise unchanged.

- `CLAUDE.md`
  - Add a row to the "Editor Compatibility / Dual-platform invariant"
    table for `memory-history.ts` ↔ `memory_history.py`.
  - Mention `.allmight/memory-history/` in the "Project Structure"
    block as the bookkeeping mirror.
  - Add a short paragraph in the memory capability section explaining
    that data deletes are recoverable via `allmight memory restore`.

- `tests/test_claude_bridge.py` — add a `TestHooksRunCleanly` case
  for `memory_history.py` (per the dual-platform contract).

- `tests/test_plugin_typecheck.py` — already typechecks every plugin
  file; the new `memory-history.ts` is picked up automatically.

### Test plan

After all edits:

1. `PYTHONPATH=src python -m pytest tests/` — full suite green.
2. `tsc --noEmit --skipLibCheck .opencode/plugins/*.ts` after a fresh
   `allmight init` — generated TypeScript valid.
3. Manual smoke:
   ```
   allmight init /tmp/x && cd /tmp/x
   echo "edit" >> personalities/x/memory/understanding/general.md
   sleep 3   # watcher window + plugin batch
   allmight memory log         # one auto-commit visible
   rm personalities/x/memory/understanding/general.md
   sleep 3
   allmight memory log         # second commit, deletion
   allmight memory restore personalities/x/memory/understanding/general.md
   cat personalities/x/memory/understanding/general.md   # restored
   ```

### Order of work (commits)

Two commits, separable for review:

1. **`fix(memory): /remember and /recall path placeholders to Part-D shape`**
   - Edit two body strings in `memory/initializer.py`
   - Add the two new pinning tests in `test_command_body_generic.py`
     (or a dedicated `test_memory_command_routing.py`)
   - ~50 lines diff

2. **`feat(memory): version-control mirror at .allmight/memory-history/ for data recovery`**
   - Add `memory/history.py`
   - Add OpenCode plugin + Claude hook
   - Add `allmight memory log/diff/restore/gc` CLI
   - Update `MemoryInitializer.initialize` to seed the mirror
   - Update CLAUDE.md (Project Structure, Dual-platform table)
   - Tests
   - ~600–800 lines diff

If `_run_git` extraction is needed, it goes in commit 2 as a small
mechanical move (`share/git_share.py` keeps a thin re-export for
backward compat with its own callers).
