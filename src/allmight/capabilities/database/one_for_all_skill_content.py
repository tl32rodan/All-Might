"""Bundled ``/one-for-all`` skill and command content.

``/one-for-all`` is the agent-driven personality export skill. Named
after All-Might's iconic quirk, which transfers one being's power to
a chosen successor — the cardinality is **1 personality → 1 bundle**.
The complementary ``/all-for-one`` skill handles the inverse,
many-to-one absorption.

Export remains agent-driven (rather than a CLI command) because the
decisions are inherently judgement calls — what counts as PII, what's
worth sharing — and have to be confirmed with the user. The skill body
is the procedure the agent follows to walk one personality's data,
apply per-capability rules, obtain consent, and write a portable
bundle that ``allmight import`` (single-bundle install) or
``/all-for-one`` (merge) can later restore.

Why ``database`` owns it: same reason it owns ``/onboard`` — a
cross-capability skill needs one home, and ``database`` is the lead
capability during bootstrap. (The skill itself iterates over every
capability the chosen personality has installed.)
"""

ONE_FOR_ALL_SKILL_BODY = """\
# One For All — bundle a personality for transfer to another project

> Run this skill when the user asks to export a personality (e.g.
> "export stdcell_owner", "share my pll_owner"). The agent applies
> per-capability export rules, asks for consent on sensitive content,
> and writes a directory bundle that ``allmight import`` or
> ``/all-for-one`` can later restore.
>
> Cardinality: **one personality → one bundle**. To absorb multiple
> sources into one personality, use ``/all-for-one`` (the inverse
> skill).

## When to use

- The user explicitly asks: "export ``stdcell_owner``", "share my
  pll_owner with the other team", "one-for-all stdcell_owner", etc.
- Before deleting a project but wanting to keep one personality.

## Procedure

### 1. Pick the personality

If the user named one explicitly, use it. Otherwise list the
registered personalities (`allmight list`) and ask which to export.

### 2. Pick the destination

Default to ``./<name>-export/`` in the current project. Confirm
with the user. The directory must not already exist.

### 3. Apply per-capability export rules

Read the personality's ``capabilities`` from
``.allmight/personalities.yaml``. For each capability, walk its
data dir and decide what to bundle:

| Capability | File / Subdir | Default action |
|-----------|---------------|----------------|
| ``database`` | ``config.yaml`` | **Export** (no PII) |
| ``database`` | ``store/`` (vector index) | **Skip** (rebuild on import) |
| ``database`` | sidecars | Sidecars live beside source, **not** inside the personality dir; nothing to do here. |
| ``memory`` | ``MEMORY.md`` (project root) | **Export with review** — show content to user, confirm. |
| ``memory`` | ``memory/understanding/<topic>.md`` | **Export with review** — for each file, show summary + check for PII (names, emails, paths, secrets); ask user before including. |
| ``memory`` | ``memory/journal/<topic>/...`` | **Ask** the user yes/no per topic; default no. |
| ``memory`` | ``memory/store/`` (SMAK index) | **Skip** (rebuild on import from journal + understanding). |
| any | ``ROLE.md`` | **Export** (the role description). |

### 4. Review for sensitive content

For every file you're about to bundle, scan for likely PII:

- Personal names, email addresses, phone numbers
- Hard-coded paths to a user's machine (``/home/<user>/...``)
- API keys, tokens, passwords, internal URLs
- Anything the user marked as private earlier in the conversation

For each hit, show the line and ask:

> "Found '<offending text>' in <file>. Include in export? (yes / no /
> redact-this-line)"

If redacting, replace with ``<REDACTED>`` and continue.

### 5. Write the bundle

Layout:

```
<name>-export/
├── manifest.yaml
├── ROLE.md
├── database/
│   └── config.yaml          (no store/)
└── memory/
    ├── understanding/        (only files that passed review)
    └── journal/              (only if user opted in)
```

``manifest.yaml`` format:

```yaml
allmight_version: '<current package version>'
schema_version: 3
personality_name: <name>
bundle_id: <fresh uuid4>               # generated at every export
bundle_version: 0.1.0                  # semver of THIS bundle's content
derived_from:                          # source descriptors this bundle was built from
  - kind: bundle                       # entry per prior bundle ancestor
    bundle_id: <prior_bundle_id>
    bundle_version: <prior_version>
  - kind: personality                  # entry per in-project source (if any)
    name: <source_personality_name>
capabilities:
  <capname>:
    capability_version: <X.Y.Z>
exported_at: '<iso-8601 timestamp>'
database_subscriptions:                # optional; omit if no shared SMAK
  - index: <index_name>                # matches an entry in database/config.yaml
    nfs_path: /nfs/smak/<index_name>   # where the shared SMAK index lives
    last_validated_against: <ISO date> # when the personality last ran clean against this index
    required: true                     # if true, import warns when nfs_path is missing
```

**On the lineage fields**:

- ``bundle_id``: generate a fresh ``uuid4`` for **every** export.
  Even re-exporting the same personality minutes later produces a new
  id — the id identifies the bundle, not the personality.
- ``bundle_version``: a semver string for *this bundle's content*.
  Distinct from ``allmight_version`` (framework) and
  ``capability_version`` (per-capability template). When unsure, keep
  it at ``0.1.0`` — the user can bump explicitly when their bundle's
  content reaches a milestone.
- ``derived_from``: a **list of source descriptors** that this bundle
  was built from. Each entry is either ``{kind: bundle, bundle_id,
  bundle_version}`` (a prior bundle ancestor) or ``{kind: personality,
  name}`` (an in-project source consumed during ``/all-for-one``).
  When exporting a personality that was itself imported, copy the
  ``derived_from`` list from
  ``.allmight/personalities.yaml::derived_from`` (preserving the full
  multi-step lineage). Personalities created locally and never derived
  from anything start with ``derived_from: []``.

Read the current ``allmight`` package version with
``python -c "import allmight; print(allmight.__version__)"`` (or
fallback to the version baked into ``.allmight/personalities.yaml``).

### 5b. Populate ``database_subscriptions`` (Mode-1 + shared-SMAK case)

If this personality reads from a **team-shared** SMAK index hosted on
NFS (the canonical Mode-1 + shared-SMAK pattern: one index per team,
single bot writer, everyone reads), record those subscriptions in
the manifest so the receiver can verify access on import.

Procedure:

1. Read ``personalities/<name>/database/config.yaml`` and list its
   indices.
2. For each index, ask the user:

   > "Index ``<name>`` — is this hosted on a shared NFS path the
   > receiver will need access to? (yes / no)"

3. If yes, ask for the canonical NFS path and whether it is
   ``required`` (import will warn loudly when missing) or optional
   (warn quietly).
4. Emit one entry under ``database_subscriptions`` per
   user-confirmed index. If the user says no for every index, omit
   the field entirely.

If the source personality is a fully-local installation (no NFS
sharing at all), skip this section — the manifest's
``database_subscriptions`` stays absent.

### 6. Tell the user what you wrote

Short summary:

> One For All! Exported ``<name>`` to ``<path>``. Capabilities:
> database, memory. Files included: ROLE.md, database/config.yaml,
> memory/understanding (3 files), memory/journal (skipped — user opted
> out). The vector index (``store/``) is not exported — re-run
> ``/ingest`` after import to rebuild it.

## Important

- **Never include ``store/``** under any capability. Vector indices
  are large, machine-specific, and rebuildable.
- **Never bundle absolute paths to user home dirs.** Rewrite to
  ``~/`` or ``$HOME/`` if the user wants to keep them.
- The bundle is a directory, not a tarball — keep file names
  obvious so the receiving user can inspect before importing.
- After writing the bundle, do **not** modify the source
  personality. One For All is read-only with respect to its source.
"""

ONE_FOR_ALL_COMMAND_BODY = """\
Bundle a personality for transfer to another All-Might project.

Run this command when the user asks to export a personality. The
agent applies per-capability rules, reviews content for PII, asks
for user consent on sensitive files, and writes a directory bundle.

Named after All-Might's quirk: **one personality → one bundle**.
For the inverse (absorb multiple sources into one personality), use
``/all-for-one``.

## What happens

1. Identifies the target personality (explicit user name or
   ``allmight list`` + prompt).
2. Picks the destination dir (default ``./<name>-export/``).
3. For each capability, applies export rules:
   - ``database``: ``config.yaml`` yes; ``store/`` no.
   - ``memory``: ``understanding/`` with review; ``journal/`` only
     with explicit yes; ``store/`` no.
4. Reviews every file for PII; asks user about each hit.
5. Writes ``manifest.yaml`` (version + capabilities + ``derived_from``
   lineage list) plus the approved files.
6. Prints a one-line summary of what was bundled and what was
   skipped.

## How to execute

Load the ``one-for-all`` skill and follow its procedure. The skill
body covers each step (capability rules, PII review, manifest
format, bundle layout) and what to ask the user.

## Receiving end

Two paths on the receiver side, depending on what the receiver wants
to do:

- **Single-bundle install into a fresh name** — run ``allmight
  import <bundle>`` (CLI). Mechanical, no merge, fails if the target
  name already exists.
- **Merge into an existing personality, or combine multiple
  bundles, or fold a bundle in with an existing personality** — run
  ``/all-for-one`` (skill) in the agent. Handles per-file conflicts
  and ROLE.md prose reconciliation.
"""
