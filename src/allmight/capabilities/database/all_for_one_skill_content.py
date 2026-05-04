"""Bundled ``/all-for-one`` skill and command content.

``/all-for-one`` is the agent-driven personality merge skill. Named
after All-Might's antagonist's quirk, which absorbs many quirks into
one body — the cardinality is **N source personalities → 1 target
personality**. The complementary ``/one-for-all`` skill handles the
inverse, single-source export.

Sources may be:

* External bundles produced by ``/one-for-all`` (or by the legacy
  ``allmight import``-compatible bundle layout).
* In-project personalities by name. This makes ``/all-for-one``
  double as a refactoring tool ("merge ``stdcell_owner`` and
  ``pll_owner`` into ``eda_owner``").

Targets may be:

* A new personality name (created from the merge).
* An existing personality (sources are folded into it).

Why a skill instead of a CLI: the merge requires per-file judgement
that a CLI flag cannot capture — ROLE.md prose reconciliation,
``memory/understanding/`` overwrites, ``database/`` workspace name
clashes. The companion ``allmight import`` CLI remains for the
**single-bundle, no-merge** install case (CI / scripting / fresh
project bootstrap).
"""

ALL_FOR_ONE_SKILL_BODY = """\
# All For One — absorb N source personalities into 1 target

> Run this skill when the user asks to merge personalities. Sources
> can be ``/one-for-all`` bundles, in-project personalities, or any
> mix. The target can be a new personality or an existing one.
>
> Cardinality: **N → 1**. To export a single personality outward,
> use ``/one-for-all`` (the inverse skill).

## When to use

- "Merge stdcell_owner and pll_owner into eda_owner" (in-project
  consolidation; no bundles involved).
- "Import this bundle and fold it into my existing pll_owner"
  (bundle + existing personality → existing).
- "Take these three bundles and combine them into a new
  shared_owner" (multiple bundles → new).
- Any single-bundle install where the target name **already exists**
  — ``allmight import`` will refuse and redirect here.

For a single-bundle install into a *fresh* target name, prefer
``allmight import <bundle>`` (CLI); it's faster and no merge dialog
is needed.

## Procedure

### 1. Identify sources

Ask the user for each source. Sources are either:

- **Bundle path** — a directory containing ``manifest.yaml`` (output
  of ``/one-for-all``). Validate by reading the manifest.
- **In-project personality name** — must appear in
  ``allmight list``. Validate by reading
  ``.allmight/personalities.yaml``.

Build a normalised internal list of source descriptors. For each
source, record:

- ``kind``: ``"bundle"`` or ``"personality"``
- ``name``: bundle's ``personality_name`` or the in-project name
- ``capabilities``: from manifest or registry row
- ``data_root``: filesystem path to walk (bundle dir or
  ``personalities/<name>/``)

### 2. Identify the target

Ask the user for a target name. Three cases:

| Target state | Action |
|---|---|
| New name (no existing personality) | Run capability install for the union of sources' capabilities into a fresh ``personalities/<target>/``. |
| Existing personality, capability sets agree | Merge directly into existing dir. |
| Existing personality, capability sets differ | Ask user: "Source has ``database`` but target doesn't. Install ``database`` into target now? (yes / no)". On yes, run that template's install. On no, drop the capability for the merge. |

### 3. Compute the union of capabilities

The target ends up with the **union** of capabilities across sources
(plus any pre-existing capabilities on an existing target). Capability
templates the receiving project doesn't have installed are an error —
fail with a clear message.

For each capability in the union, run that template's install hook
in the target directory if it isn't already installed. This ensures
the target dir layout conforms to the receiving project's
``allmight`` version.

### 4. Per-capability merge

Walk each capability across all sources and apply the merge rules
below. Order matters only when conflicts must be resolved
deterministically — process sources in the order the user listed them
(left-to-right precedence for "pick one" decisions).

#### 4a. ``database/<workspace>/``

The merge unit is **the workspace** (a single directory under
``database/``). For each source:

1. Enumerate ``database/*/`` subdirs.
2. For each workspace, look at the target's existing workspaces:
   - **No name clash** → copy the workspace dir into the target as-is
     (only ``config.yaml`` and any non-``store/`` content; never
     ``store/``).
   - **Name clash** → ask the user:
     > "Workspace ``<name>`` exists in both source ``<src>`` and the
     > target. Choose: (1) rename source's workspace to
     > ``<name>_<src>``, (2) keep target's, drop source's, (3) merge
     > corpora lists from both ``config.yaml`` files into one."
   - On choice 3, union the ``corpora`` array in ``config.yaml``,
     dedupe by canonical path, and write the merged ``config.yaml``.
     Other top-level keys (e.g. ``model``, ``index_settings``) take
     the target's value; warn the user when they differ from the
     source.

3. **Never copy ``store/``.** It's the SMAK vector index — derived
   data, machine-specific, large. The user re-runs ``/ingest`` after
   the merge to rebuild it.

#### 4b. ``memory/understanding/<topic>.md``

Each understanding file is prose. Mechanical merge is wrong here.

For each source's ``understanding/*.md``:

- **No name clash** → copy as-is.
- **Name clash** → for each clashing file, show both files' content
  to the user and ask:
  > "Both ``<src>`` and target have ``understanding/<topic>.md``.
  > Choose: (1) keep target's, drop source's, (2) keep source's,
  > overwrite target's, (3) concatenate (target then source), (4)
  > rewrite — I'll draft a merged version for you to review."

  On choice 4, draft a unified version that captures the union of
  facts from both files, present it to the user, and write it only
  after explicit confirmation.

#### 4c. ``memory/journal/<scope>/``

Journal entries are append-only by design (timestamped records).
Concatenation is safe.

For each source's ``journal/<scope>/``:

1. Copy all entries into the target's ``journal/<scope>/``.
2. After copying, sort the resulting directory by entry timestamp.
3. Dedupe identical entries (same timestamp + same body) — they
   indicate the same record was bundled twice along different
   lineage paths.

No user dialog needed for journals unless dedupe finds near-but-not-
identical entries (same timestamp, slightly different body); then
ask which to keep.

#### 4d. ``memory/store/``

Never copy. Rebuilt by the next ``/remember`` cycle on the merged
journal.

#### 4e. ``ROLE.md``

The single most expensive merge step. ``ROLE.md`` is pure prose
describing what the personality is responsible for; concatenating
two roles produces nonsense.

Procedure:

1. Read every source's ``ROLE.md``.
2. Read the target's existing ``ROLE.md`` if it exists.
3. Draft a merged ``ROLE.md`` that captures:
   - The union of responsibilities (deduped where they overlap).
   - The reconciled scope statement (ask the user if sources disagree
     on scope — e.g. one says "stdcell library", another says "PLL
     library", merged target probably needs "stdcell + PLL libraries").
   - The combined access mode (most permissive wins, but warn the
     user if it changes).
4. Show the draft to the user. Iterate on their feedback. Write only
   after explicit confirmation.

### 5. Update the registry

Update ``.allmight/personalities.yaml`` to reflect the merge. The
target's row gets a ``derived_from`` list with one entry per source:

```yaml
- name: <target>
  capabilities: [<union>]
  versions: {<cap>: <version>, ...}
  derived_from:
    - kind: bundle
      bundle_id: <uuid>
      bundle_version: 0.1.0
    - kind: personality
      name: stdcell_owner
  derived_at: '<iso-8601 timestamp>'
```

Order entries the same way the user listed sources. If the target
already had a ``derived_from`` list (it was previously merged or
imported), **prepend** the new entries — the field is a complete
ancestry record, not just the most recent merge.

### 6. Source disposition (in-project sources only)

After the merge succeeds, ask:

> "Merge complete. Keep source personalities (``<list>``) installed,
> or remove them now that they've been folded into ``<target>``?
> (keep / remove)"

Default is **keep** (``git merge --squash`` style). On remove:

1. Delete each source's ``personalities/<src>/`` directory.
2. Drop the source's row from ``.allmight/personalities.yaml``.
3. Run ``compose_agents_md`` (or the equivalent of regenerating
   ``AGENTS.md``) so the removed personalities disappear from the
   agent surface.

Bundle sources are never touched — they live outside the project.

### 7. Tell the user what you did

Short summary:

> All For One! Absorbed <N> sources into ``<target>``. Capabilities:
> <union>. Merged: <count> understanding files (<conflicts> needed
> review), <count> journal entries (<dupes> deduped), <count>
> database workspaces. Sources kept: <list>. Re-run ``/ingest`` in
> any merged database workspace to rebuild SMAK indices.

## Important

- **The target's old data is part of the merge input** when the
  target is an existing personality. Do not skip step 4 just because
  you're "importing into" — the target is itself a source for
  conflict resolution.
- **``store/`` is never touched** under any capability. Always end
  with the ``/ingest`` reminder for database, and let
  ``/remember``-cycle rebuilds happen for memory.
- **ROLE.md merge always requires explicit user confirmation.**
  Never write a merged ROLE.md without the user signing off on the
  draft.
- **Bundle sources are read-only.** Never modify a bundle dir during
  the merge — they may be shared between projects.
- **Failure semantics**: if any per-capability merge step fails (user
  aborts a dialog, capability install fails), roll back the target's
  filesystem changes for that capability. Partial merges are
  confusing to debug.
"""

ALL_FOR_ONE_COMMAND_BODY = """\
Absorb multiple personalities (bundles or in-project) into a single target.

Run this command when the user asks to merge personalities, fold a
bundle into an existing one, or consolidate in-project roles. Named
after All-Might's antagonist's quirk: **N sources → 1 target**.

For the inverse (export one personality outward as a bundle), use
``/one-for-all``. For a single-bundle install into a *fresh* target
name with no merge needed, prefer the ``allmight import`` CLI.

## What happens

1. Collect sources from the user — each is either a bundle path
   (``/one-for-all`` output) or an in-project personality name.
2. Identify the target — new name or existing personality.
3. For each capability in the union of sources' capabilities:
   - ``database``: per-workspace; name clashes → user dialog
     (rename / pick / merge corpora).
   - ``memory/understanding/``: per-file; clashes → dialog
     (pick / overwrite / concat / agent-rewrite).
   - ``memory/journal/``: append + sort by timestamp + dedupe.
   - ``ROLE.md``: agent drafts a merged version, user confirms.
   - ``store/`` (any): never copied; rebuild via ``/ingest``.
4. Update ``.allmight/personalities.yaml`` with a ``derived_from``
   list recording every source.
5. Ask whether to keep or remove the in-project source personalities
   (default: keep).
6. Print a summary and remind the user to ``/ingest`` merged
   workspaces.

## How to execute

Load the ``all-for-one`` skill and follow its procedure. The skill
body covers source discovery, per-capability merge rules, ROLE.md
drafting, and registry updates.
"""
