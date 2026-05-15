"""Bundled ``/split`` skill and command content.

``/split`` is the agent-driven personality **refactor** skill. It
extracts a slice of one personality's scope — memory data plus the
matching ROLE.md prose — into a different personality in the **same
project**. Cardinality: **1 → 1, in-project**.

It is the third corner of the personality-lifecycle triangle:

* ``/onboard`` — initial configuration (0 → N).
* ``/one-for-all`` — cross-project export (1 → 1, outward).
* ``/all-for-one`` — cross-project absorb (N → 1, inward).
* ``/split`` — in-project refactor (1 → 1, same project).

``/split`` deliberately does **not** move database workspaces. SMAK
indexes source files in-place (paths inside ``database/<ws>/config.yaml``
point outside the All-Might project); moving the workspace dir would
require rewriting every path, with risk far exceeding the value. The
user can index whatever the new role needs by running ``smak ingest``
out-of-band — the target's ROLE.md, which ``/split`` writes, is the
indexing hint.

Trigger is **manual only**. ``/split`` is not listed in AGENTS.md's
"When to suggest user actions" table — agent self-evaluation of
"these responsibilities should be split" produces too many false
positives. Users invoke ``/split`` when they explicitly recognise a
scope drift.
"""

SPLIT_SKILL_BODY = """\
# Split — extract a slice of one personality into another (in-project)

> Run this skill when the user asks to refactor responsibilities
> **inside the project** — pull a chunk of an active personality's
> scope into a different personality (new or existing). Memory data
> moves; database workspaces stay put.
>
> Cardinality: **1 → 1, same project**. For cross-project transfer
> use ``/one-for-all`` (bundle out) or ``/all-for-one`` (absorb in).
> For initial setup use ``/onboard``.

## When to use

- "Split the PLL stuff off ``stdcell_owner`` into a new ``pll_owner``"
- "Move my code-review notes from ``stdcell_owner`` into a new
  ``code_reviewer`` personality"
- "Pull the verification chunk out of ``rtl_owner`` and fold it into
  the existing ``verif_owner``"

Manual only — there is no plugin or proactive prompt. Do **not**
volunteer ``/split`` just because the conversation has drifted; wait
for the user to raise it explicitly.

## Procedure

### 1. Confirm source and target

- **Source** is usually the active personality. If ambiguous, ask.
  Read ``.allmight/personalities.yaml`` to confirm the name exists.
- **Target** — ask the user. Two cases:

  | Target state | Action |
  |---|---|
  | New name (not in ``allmight list``) | Shell out: ``allmight add <target> --capabilities <subset>``. Capabilities default to a subset of the source's; ask the user which to copy (the target may legitimately need fewer — e.g. a ``code_reviewer`` split off from ``stdcell_owner`` may want only ``memory``, not ``database``). |
  | Existing personality | Use as-is. Will merge into existing data. |

### 2. Draft the migration plan (no writes yet)

Show the user a plan covering three buckets. Get **per-item**
confirmation before any write. Default action for each item is
*include*; the user can drop individual files.

| Bucket | What to list |
|---|---|
| Memory — understanding | Files under ``personalities/<src>/memory/understanding/*.md`` that match the slice's topic. Per file: filename + the first non-empty line. |
| Memory — journal | Subdirs under ``personalities/<src>/memory/journal/<scope>/`` that match the slice. Per subdir: name + entry count. |
| ROLE.md | The exact paragraphs to **strip** from the source's ``ROLE.md``, and the proposed text to **write** (new target) or **append** (existing target). |

For ROLE.md prose, when the target already exists with non-trivial
content, do the same prose reconciliation step as ``/all-for-one``
step 4e: draft the merged section, show it to the user, iterate on
feedback, write only after explicit confirmation.

### 3. Database workspaces — **not touched**

``/split`` does **not** move any ``personalities/<src>/database/<ws>/``
directory. Re-confirm with the user if they ask:

> "The new role's ``/search`` workspace stays empty. SMAK indexes
> source files in-place, and moving a workspace would require
> rewriting every path inside ``config.yaml``. Once you decide what
> the new role should index, run ``smak ingest`` against those
> source paths out-of-band — the target's ROLE.md (which we'll
> write next) is the canonical hint for what to index."

The first ``/search`` returning empty results is the natural signal
that ``smak ingest`` needs to run. Do not write a "pending bootstrap"
section into the target's ROLE.md.

### 4. Execute (only after the plan is confirmed)

For each approved item, in order:

1. **Memory files** — use ``git mv`` from source to target:

   ```bash
   git mv personalities/<src>/memory/understanding/<topic>.md \\
          personalities/<tgt>/memory/understanding/<topic>.md
   ```

   Same for journal subdirs (use ``git mv`` on the whole dir). The
   post-turn hook (``memory-history.ts`` / ``memory_history.py``)
   auto-snapshots the move into ``.allmight/memory-history/.git``;
   if the user later regrets a move, ``allmight memory log`` +
   ``allmight memory restore`` recover the file.

2. **Source ``ROLE.md``** — read the current body, strip exactly the
   user-confirmed paragraphs, write the result back. Preserve:

   - The All-Might marker on line 1 (``<!-- all-might generated -->``).
   - Every section the user did **not** mark for removal — do not
     refactor unrelated prose; this is a focused edit.

3. **Target ``ROLE.md``**:

   - **New target** — ``allmight add`` already wrote a starter
     ``ROLE.md``. Replace its body (keeping the marker) with the
     role description for the migrated slice.
   - **Existing target** — append the new responsibility section. If
     the existing prose disagrees with the new section's scope
     statement, draft a reconciled version and confirm with the user
     before writing (same as step 2's note).

### 5. Update the registry

Edit ``.allmight/personalities.yaml`` so the target's row records the
split. **Prepend** a fresh entry to the target's ``derived_from``
list (preserving any prior ancestry):

```yaml
- name: <target>
  capabilities: [<unchanged>]
  versions: {<unchanged>}
  derived_from:
    - kind: personality
      name: <src>
      action: split
    # ...any prior derived_from entries follow here
  derived_at: '<iso-8601 timestamp>'
```

Notes:

- ``kind: personality`` matches the schema ``/all-for-one`` uses for
  in-project sources. The optional ``action: split`` field
  distinguishes split-derived ancestry from merge-derived ancestry —
  ``/all-for-one`` entries do not carry ``action``.
- ``derived_at`` is the registry row's most recent derivation
  timestamp (a single ISO-8601 string, not per-entry).
- The **source** personality's row is unchanged. Splitting *out of*
  a personality is not part of its own ancestry.

### 6. Tell the user what you did

One-line summary:

> Split! Moved <N> understanding files + <M> journal subdirs from
> ``<src>`` to ``<tgt>``. Source ROLE.md trimmed; target ROLE.md
> updated. ``derived_from`` records ``<src>`` (action: split).
> Database workspaces untouched — run ``smak ingest`` on
> ``<tgt>``'s source paths when you want ``/search`` over the new
> scope.

## Important

- **No database workspace migration.** Even if a workspace
  semantically belongs to the new role (e.g. a ``pll`` workspace
  being split off from ``stdcell_owner`` to ``pll_owner``), do not
  move it. The user re-indexes via ``smak ingest`` when ready.
- **Source data is moved, not copied.** ``/split`` is destructive on
  the source side; the post-turn snapshot in
  ``.allmight/memory-history/.git`` is the safety net.
- **ROLE.md edits on an existing target require explicit
  confirmation** when the target has non-trivial existing content.
  Treat it the same as ``/all-for-one`` step 4e.
- **No auto-trigger.** Even if conversation context strongly
  suggests a split would help, do not propose ``/split`` unless the
  user explicitly raises it. There is no plugin and no
  "When to suggest" entry — ``/split`` is fully user-initiated.
- **No "pending bootstrap" annotation.** Do not write a TODO
  section into the target's ROLE.md about indexing. The role
  description itself is the indexing hint; an empty ``/search``
  result is the natural reminder.
"""

SPLIT_COMMAND_BODY = """\
Refactor responsibilities within a project — extract memory and scope
from one personality into another.

Run this command when the user explicitly asks to split, refactor, or
extract a slice of an active personality's responsibility into a
different personality (existing or new). Same-project **1 → 1**.

For cross-project transfer use ``/one-for-all`` (bundle outward) or
``/all-for-one`` (absorb inward). For initial setup use ``/onboard``.

## What happens

1. Confirms source (usually the active personality) and target
   (existing personality, or new name — new triggers
   ``allmight add <target> --capabilities <subset>`` first).
2. Drafts a migration plan: which ``memory/understanding/*.md`` files,
   which ``memory/journal/<scope>/`` subdirs, and which paragraphs
   from source ``ROLE.md`` to strip / target ``ROLE.md`` to add.
3. Gets **per-item** confirmation. Database workspaces are **not**
   touched.
4. ``git mv`` approved memory files; rewrite source ``ROLE.md``;
   write or append target ``ROLE.md`` (with prose reconciliation if
   the target already exists).
5. Updates ``.allmight/personalities.yaml``: prepends
   ``{kind: personality, name: <src>, action: split}`` to the
   target's ``derived_from`` list.
6. Prints a summary; reminds the user to ``smak ingest`` if they want
   ``/search`` over the new target's scope.

## How to execute

Load the ``split`` skill and follow its procedure. The skill body
covers the migration-plan dialog, ROLE.md handling, and registry
update rules.

## Why this is rare

``/split`` is a personality lifecycle event — typical use is weeks to
months apart. It is triggered manually by the user; there is no
plugin and no "When to suggest" entry in AGENTS.md. Cross-project
transfer goes through ``/one-for-all`` / ``/all-for-one``; initial
setup goes through ``/onboard``.
"""
