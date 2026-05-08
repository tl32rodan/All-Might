"""Bundled ``/recover`` skill and command content.

``/recover`` is the agent-driven wrapper around the memory-history
recovery CLI (``allmight memory log/diff/restore``). The CLI is
fine for scripting but unfriendly for the typical recovery moment
("I just deleted that file, get it back") — the user usually doesn't
know which sha to pass, doesn't want to read the diff, and just
needs the right thing to come back. The skill walks the agent
through that conversation: identify the file, surface recent
snapshots, pick the right revision, restore, prompt to re-ingest if
database/ files were involved.

The CLI surface (``allmight memory log``, ``allmight memory
restore``, etc.) stays — it's the layer scripts and power users
talk to. ``/recover`` is the human-friendly facade that targets the
common case.
"""

RECOVER_SKILL_BODY = """\
# Recover — restore memory data from the local snapshot mirror

> Run this skill when the user says they want to undo a memory
> change — accidental delete, bad edit, "go back to how it looked
> earlier today". The skill wraps ``allmight memory`` CLI subcommands
> with the dialog needed to pick the right revision and target.

## When to use

Trigger phrases (non-exhaustive):

- "I just deleted that, can we get it back?"
- "Restore X from before <event>"
- "Undo the last few edits to my memory"
- "What did MEMORY.md look like an hour ago?"
- "Roll my journal back to <date>"

Don't run ``/recover`` for live source code recovery — that's a job
for the project's own ``git`` (or whatever VCS the user uses).
``/recover`` only touches what the memory-history mirror tracks:
``MEMORY.md``, ``personalities/<p>/ROLE.md``,
``personalities/<p>/memory/{understanding,journal,lessons_learned}/``,
``personalities/<p>/memory/usage.log``,
``personalities/<p>/database/<ws>/config.yaml``.

## Procedure

### 1. Pin down what to recover

Ask the user — or infer from the conversation:

- **Which file?** (project-relative path; resolve relative to
  project root)
- **Recover to what point?** Common answers map cleanly to a
  revision:
  - "Right before I deleted it" → ``HEAD~1`` (the snapshot taken
    after the previous turn, before the delete)
  - "How it was at the start of this session" → use ``allmight
    memory log`` to find the first commit with the session-id of
    the current session and restore from the parent of that commit
  - "Roll back the last N changes" → ``HEAD~N``
  - "A specific date / time" → use ``allmight memory log`` to find
    the commit closest to the requested time

If the user is vague, show them the recent log first (step 2) and
let them pick.

### 2. Show the relevant snapshot history

```bash
# Whole-project recent activity
allmight memory log -n 10

# Filter to one personality (more focused for per-personality data)
allmight memory log --personality <name> -n 10
```

The output is one line per commit:

```
<short-sha>  <iso-timestamp>  <subject>
```

Trigger labels live in the commit body; show them via ``memory
diff`` only if the subject line isn't enough to disambiguate.

### 3. Confirm the choice with the user

For non-trivial recoveries (anything other than "yes, that one"),
show the diff first:

```bash
allmight memory diff <sha>            # whole commit
allmight memory diff <sha> --file <path>   # restrict to one file
```

Summarise the diff in plain language and ask "restore from this
revision?" before running step 4.

### 4. Restore

```bash
allmight memory restore <file> --rev <sha> --yes
```

Notes:

- ``--yes`` skips the CLI's interactive overwrite prompt — you've
  already confirmed with the user in step 3, so a second prompt is
  noise.
- ``<file>`` is the project-relative path (same as it appears in
  ``memory log`` / ``memory diff`` output).
- For non-destructive inspection, restore to a different
  destination first: ``--to /tmp/old-version.md``. Useful when the
  user wants to compare before clobbering.

### 5. Tell the user what changed and what's next

A one-line summary, plus two follow-ups:

- If the restored file is under ``personalities/<p>/database/``,
  remind the user to re-run ``/ingest`` so the SMAK index reflects
  the restored content.
- If the restored file is ``MEMORY.md`` or ``memory/journal/``,
  remind the user that the next ``/remember`` cycle will re-index
  the journal automatically — no manual ``/ingest`` needed.

Example:

> Restored ``personalities/stdcell_owner/memory/understanding/stdcell.md``
> from ``cb398861`` (2 commits back, before today's accidental
> delete). Next: nothing — understanding/ files don't need
> re-indexing.

## Other operations the skill can run

The CLI exposes a few less-common subcommands. Use them when the
user explicitly asks; don't run them as part of the default
recovery flow:

- ``allmight memory snapshot -m "<reason>"`` — manual snapshot.
  Useful when the user is about to do something risky and wants an
  explicit save point.
- ``allmight memory diff <sha>`` — read-only inspection.
- ``allmight memory gc`` — housekeeping for long-running projects.

## Important

- **The mirror only covers memory data**, not source code. If the
  user wants to undo a source-code edit, hand it back to the
  project's own ``git`` (or ``git stash``, ``git restore``, etc.).
- **Never restore without confirming with the user.** ``--yes`` on
  the CLI bypasses the *CLI's* prompt; it doesn't bypass the
  agent's responsibility to ask.
- **``--to`` for non-destructive inspection.** If the user is
  unsure, restore to ``/tmp/<name>.bak.md`` first and let them
  ``diff`` against the live file before overwriting.
- **One file at a time.** The CLI doesn't currently support
  multi-file restore. If the user needs to roll back many files,
  loop the procedure per file (and confirm each).
"""

RECOVER_COMMAND_BODY = """\
Restore memory data from the recovery snapshot mirror.

Wraps ``allmight memory log/diff/restore`` with the dialog needed to
pick the right snapshot for the typical recovery moment ("I just
deleted that, get it back"). For scripting / power-user flows the
CLI subcommands stay available.

## What happens

1. Identifies the file to recover (from the user's request, or by
   showing recent snapshots and asking).
2. Picks the revision: ``HEAD~1`` for "right before the mistake",
   or a specific sha from ``allmight memory log``.
3. Confirms with the user (shows ``allmight memory diff <sha>`` if
   the choice isn't obvious).
4. Runs ``allmight memory restore <file> --rev <sha> --yes``.
5. Prompts ``/ingest`` if the restored file lives under
   ``personalities/<active>/database/``.

## How to execute

Load the ``recover`` skill and follow its procedure. The skill body
covers the trigger phrases, the dialog steps, and the CLI
invocations.
"""
