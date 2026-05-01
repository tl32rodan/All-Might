"""Bundled /export skill and command content (Part-D commit 10).

``/export`` is agent-driven because export decisions are
inherently judgement calls — what counts as PII, what's worth
sharing — and have to be confirmed with the user. The skill body
is the procedure the agent follows to walk one personality's
data, apply per-capability rules, obtain consent, and write a
portable bundle that ``allmight import`` can later restore.

Why ``database`` owns it: same reason it owns ``/onboard`` — a
cross-capability skill needs one home, and ``database`` is the
lead capability during bootstrap. (The skill itself iterates over
every capability the chosen personality has installed.)
"""

EXPORT_SKILL_BODY = """\
# Export — bundle a personality for transfer to another project

> Run this skill when the user asks to export a personality. The
> agent applies per-capability export rules, asks for consent on
> sensitive content, and writes a directory bundle that
> ``allmight import`` can later restore in another project.

## When to use

- The user explicitly asks: "export ``stdcell_owner``", "share my
  pll_owner with the other team", etc.
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
schema_version: 1
personality_name: <name>
capabilities:
  <capname>:
    capability_version: <X.Y.Z>
exported_at: '<iso-8601 timestamp>'
```

Read the current ``allmight`` package version with
``python -c "import allmight; print(allmight.__version__)"`` (or
fallback to the version baked into ``.allmight/personalities.yaml``).

### 6. Tell the user what you wrote

Short summary:

> Exported ``<name>`` to ``<path>``. Capabilities: database, memory.
> Files included: ROLE.md, database/config.yaml, memory/understanding
> (3 files), memory/journal (skipped — user opted out).
> The vector index (``store/``) is not exported — re-run ``/ingest``
> after import to rebuild it.

## Important

- **Never include ``store/``** under any capability. Vector indices
  are large, machine-specific, and rebuildable.
- **Never bundle absolute paths to user home dirs.** Rewrite to
  ``~/`` or ``$HOME/`` if the user wants to keep them.
- The bundle is a directory, not a tarball — keep file names
  obvious so the receiving user can inspect before importing.
- After writing the bundle, do **not** modify the source
  personality. Export is read-only.
"""

EXPORT_COMMAND_BODY = """\
Export a personality bundle for transfer to another All-Might project.

Run this command when the user asks to export a personality. The
agent applies per-capability rules, reviews content for PII, asks
for user consent on sensitive files, and writes a directory bundle.

## What happens

1. Identifies the target personality (explicit user name or
   ``allmight list`` + prompt).
2. Picks the destination dir (default ``./<name>-export/``).
3. For each capability, applies export rules:
   - ``database``: ``config.yaml`` yes; ``store/`` no.
   - ``memory``: ``understanding/`` with review; ``journal/`` only
     with explicit yes; ``store/`` no.
4. Reviews every file for PII; asks user about each hit.
5. Writes ``manifest.yaml`` (version + capabilities) plus the
   approved files.
6. Prints a one-line summary of what was bundled and what was
   skipped.

## How to execute

Load the ``export`` skill and follow its procedure. The skill body
covers each step (capability rules, PII review, manifest format,
bundle layout) and what to ask the user.

## Receiving end

Run ``allmight import <bundle>`` in the target project to restore.
``allmight import`` re-runs each capability's install so the
imported structure conforms to the receiving project's
``allmight`` version, then copies the bundle's data into place.
"""
