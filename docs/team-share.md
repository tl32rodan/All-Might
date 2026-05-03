# Team Share — How To

This is the how-to guide for sharing All-Might personalities across
your team. It walks through three scenarios you'll actually hit.
For deeper schema reference, jump to [Reference](#reference) at the
end.

> **A note on names**: the export / import verbs also answer to
> ``/one-for-all`` and ``allmight all-for-one``. The names mirror
> the *direction* — One-for-All **passes** a personality on,
> All-for-One **gathers** one in. Both old and new names are
> first-class and stay forever. Use whichever reads better at the
> call site. This guide uses the directional names where they're
> clearer.

---

## Two patterns, in 60 seconds

| Pattern | When | One-line summary |
|---|---|---|
| **Bundle share** | A teammate wants their own copy of your personality | You publish a bundle to a git remote; they pull it down, customise it locally |
| **Instance share** | The whole team uses the same review/CI/dispatcher personality | Everyone `cd`'s into one NFS-hosted All-Might project |

Bundle share = "dotfiles for your role". Instance share = "one
shared service, many users". They are independent — your project
can use both at once for different personalities.

---

## Scenario A — You made a personality your teammates want

You spent a week building the ``stdcell_owner`` role: agent
prompts, knowledge in ``memory/understanding/``, the right SMAK
indices wired up. Now Lin and Chen want to use it on their machines.

### Step 1 — Bundle the personality (One-for-All)

Inside Claude Code or OpenCode, ask the agent to export it:

```
> /one-for-all stdcell_owner
```

(or ``/export stdcell_owner`` — same procedure.) The agent walks
your personality's data, applies per-capability rules, asks for
your consent on anything that looks like PII (names, emails,
hardcoded paths to your home directory), and writes a bundle
directory at ``./stdcell_owner-export/``:

```
stdcell_owner-export/
├── manifest.yaml         # framework versions, capability versions, lineage,
│                         # database subscriptions (if you opted-in)
├── ROLE.md               # the role description
├── database/
│   └── config.yaml       # which SMAK indices the role uses (no store/)
└── memory/
    ├── understanding/    # agent-curated knowledge that survived your review
    └── journal/          # only if you explicitly said yes
```

The vector index (``memory/store/``, ``database/.../store/``) is
intentionally absent — it's huge, machine-specific, and trivially
rebuildable from the source files.

### Step 2 — Push the bundle to a git remote

The bundle is on your disk. To get it to teammates, push to any
git URL the local ``git`` can reach. The simplest is a bare repo on
shared NFS:

```bash
allmight share publish ./stdcell_owner-export/ \
    --to file:///nfs/team/personalities/stdcell_owner.git \
    --message "stdcell_owner v1.0"
```

If the bare repo doesn't exist yet, ``share publish`` runs
``git init --bare`` automatically (for ``file://`` URLs). For SSH
or HTTPS remotes, the repo must already exist; create it once on
your git server.

After publish, ``.allmight/upstream.yaml`` records the URL +
the bundle's ``bundle_id`` so future re-publishes carry lineage
forward in ``derived_from``.

### Step 3 — Tell your teammates

Just tell them the URL. Their step is Scenario B below.

---

## Scenario B — A teammate made a personality you want

Lin pings: "I published ``stdcell_owner`` at
``file:///nfs/team/personalities/stdcell_owner.git``."

### One command (All-for-One)

In any All-Might project on your machine:

```bash
allmight share pull file:///nfs/team/personalities/stdcell_owner.git
```

This:
1. ``git clone``s Lin's bundle to a temp dir.
2. Calls ``allmight all-for-one`` (== ``allmight import``) against
   the cloned tree.
3. Records Lin's URL in your ``.allmight/upstream.yaml`` so you
   can pull updates later.

After pull:

```bash
ls personalities/stdcell_owner/    # ROLE.md, memory/, database/, …
```

Run ``/ingest`` once to rebuild your local SMAK store from the
imported config. (Vector indices don't travel in bundles; you
build your own from the source files the personality references.)

### Variations

```bash
# Rename on import (avoid collision with your own stdcell_owner)
allmight share pull <url> --as stdcell_v2

# Two-step if you want to inspect the bundle before importing
git clone <url> /tmp/inspect-bundle
ls /tmp/inspect-bundle              # eyeball it
allmight all-for-one /tmp/inspect-bundle
```

### What if the personality depends on a SMAK index you can't reach?

If the bundle's ``manifest.yaml`` declares
``database_subscriptions`` (e.g. ``/nfs/smak/stdcell``) and that
path doesn't exist on your machine, ``share pull`` (and
``allmight import``) emit a warning per missing path **but the
import still succeeds**. You can then either mount the team NFS or
edit ``personalities/stdcell_owner/database/config.yaml`` to point
at a local index.

---

## Scenario C — The team uses one shared personality (instance share)

This pattern is for service-style roles: one canonical "code
review agent" that ten engineers all consult, the same way they'd
all consult a shared CI server. Each engineer doesn't need their
own customised copy — they need the same role to keep memory
across all of them.

### The setup

A dedicated unix account owns an All-Might project on NFS:

```
/nfs/team/review-allmight/                ← owned by review-bot:review-team
├── AGENTS.md
├── MEMORY.md
├── .allmight/
├── .opencode/
└── personalities/
    └── review/
        ├── ROLE.md
        ├── memory/
        │   ├── understanding/            ← curator-edited canonical knowledge
        │   ├── journal/                  ← session logs
        │   ├── lessons_learned/
        │   │   ├── _inbox/               ← engineers write here during sessions
        │   │   └── _reviewed/            ← curator's audited landing
        │   └── store/
        └── database/
            └── config.yaml               ← points at /nfs/smak/<index>
```

Recommended permissions:

```bash
chown -R review-bot:review-team /nfs/team/review-allmight
chmod -R 770 /nfs/team/review-allmight
find /nfs/team/review-allmight -type d -exec chmod g+s {} +
```

The setgid bit keeps group ownership consistent on new files.
All-Might itself doesn't enforce these — your umask + the dir's
setgid own permissions.

### The user's flow

To consult the review agent, an engineer just `cd`'s in and starts
their agent client:

```bash
cd /nfs/team/review-allmight/
opencode      # or: claude
```

Their session sees the team's MEMORY.md, the review personality's
ROLE.md, and the shared SMAK indices. When they're done, anything
worth flagging for the curator goes to:

```
memory/lessons_learned/_inbox/<ISO-8601>-<unix_user>.md
```

The agent does this automatically when ``/remember`` recognises
"this is a lesson worth flagging for the curator", per the
routing rule in the memory keeper's ROLE.md. The filename is
per-user-per-timestamp, so two engineers reviewing simultaneously
never collide on the same file.

### The curator's flow

A weekly cron (or a manual session) sweeps ``_inbox/``, optionally
cross-references with recent SOS revisions, and presents the
curator with each entry. For each one:

* **Keep**: move to ``_reviewed/``
* **Promote**: distill into ``understanding/canonical.md``
* **Discard**: delete

The framework ships only the layout and the routing rule. The
audit job itself is a project-side script — All-Might doesn't
prescribe what the audit packet looks like.

### Why this avoids file locks

The split between user-side ``_inbox/`` (per-user, append-only)
and curator-side ``understanding/`` / ``MEMORY.md`` (single-writer,
the curator) means **no two writers ever target the same file**.
You don't need distributed locks; the design sidesteps the
collision.

---

## Sharing SMAK as the team's source of truth

Most chip-design teams want one canonical SMAK index per library
(``stdcell``, ``io_phy``, ``pll``…), not one per engineer. The
canonical pattern:

```
/nfs/smak/<index>/                   ← bot writes, group reads
  ├── faiss.index
  ├── metadata.json
  └── ...
```

A dedicated unix account ("the bot") performs **atomic-rename
ingest** to avoid partial reads:

```bash
ingest_to /nfs/smak/<index>.tmp/         # write to a side directory
mv /nfs/smak/<index> /nfs/smak/<index>.old
mv /nfs/smak/<index>.tmp /nfs/smak/<index>
rm -rf /nfs/smak/<index>.old
```

POSIX `mv` is atomic on the same filesystem; readers holding old
inodes finish their search against the old index, while new opens
hit the new one. Single-writer eliminates the multi-tenant SMAK
problem at its root.

A personality that relies on a shared SMAK index records the
dependency in its bundle manifest under
``database_subscriptions``:

```yaml
database_subscriptions:
  - index: stdcell
    nfs_path: /nfs/smak/stdcell
    last_validated_against: 2026-04-15
    required: true        # warn loudly if missing on import
```

When a teammate ``share pull``s the bundle on a machine that
hasn't mounted ``/nfs/smak/``, they get a warning per missing
path; the import still succeeds so they can mount NFS later.

### SMAK update request payload

When a personality finishes a review and wants its findings
ingested into the canonical SMAK index, it submits a request to a
**SMAK update service** (a separate repository — All-Might
documents only the payload format):

```json
{
  "changed_files": ["src/cell_A.v", "src/cell_B.v"],
  "submitted_by": "<unix_user>",
  "review_id": "<uuid>"
}
```

The receiver fetches the named files from SOS and queues them for
the bot's atomic-rename ingest. ``review_id`` lets the bot trace
each ingestion back to the review session that produced it.

The framework does **not** ship a generator for these requests —
each personality author writes a skill that fits their specific
review flow.

---

## Reference

### Manifest schema (v2)

Produced by ``/one-for-all`` (== ``/export``). Consumed by
``allmight all-for-one`` (== ``allmight import``).

```yaml
allmight_version: '0.1.0'
schema_version: 2
personality_name: stdcell_owner
exported_at: '2026-05-04T10:00:00Z'

# Lineage (optional, omitted on first export)
bundle_id: 7c4f3a2e-1111-2222-3333-444455556666     # uuid4, fresh per export
bundle_version: 1.0.0                                # semver of THIS bundle's content
derived_from:                                        # ancestry, may be empty
  - 11111111-2222-3333-4444-555555555555

# Capabilities the personality has (with template versions)
capabilities:
  database:
    capability_version: 1.0.0
  memory:
    capability_version: 1.0.0

# Shared-SMAK subscriptions (optional, omit if no shared SMAK)
database_subscriptions:
  - index: stdcell                                   # matches database/config.yaml entry
    nfs_path: /nfs/smak/stdcell                      # where the shared SMAK index lives
    last_validated_against: 2026-04-15
    required: true                                   # warn loudly if missing on import
```

The three version concepts are independent:
* ``allmight_version`` — framework version
* ``capabilities.<cap>.capability_version`` — per-template version
* ``bundle_version`` — content-level semver of *this* bundle

Bump ``bundle_version`` when the personality's content reaches a
milestone. The framework does not auto-bump it.

### Command pairs

| Mnemonic | Direction | Names |
|---|---|---|
| One-for-All | passes a personality on | ``/one-for-all``, ``/export`` (slash) |
| All-for-One | gathers a personality | ``allmight all-for-one``, ``allmight import`` (CLI) |
| Publish | pushes the bundle to git | ``allmight share publish`` |
| Pull | clones bundle from git + imports | ``allmight share pull`` |

### Files this guide references

| File | Owner | Lifecycle |
|---|---|---|
| ``manifest.yaml`` (in bundle) | One-for-All / Export | Generated each export |
| ``.allmight/upstream.yaml`` | ``share publish`` / ``share pull`` | Persists per-personality URL + last-seen bundle_id |
| ``.allmight/personalities.yaml`` | ``allmight import`` / ``all-for-one`` | Records lineage on import |
| ``personalities/<p>/memory/lessons_learned/_inbox/`` | User session ``/remember`` | Append-only, per-user-per-timestamp |
| ``personalities/<p>/memory/lessons_learned/_reviewed/`` | Curator audit | Curator-only writer |

### What's not covered yet

These limitations are documented, not bugs:

* **Audit packet generation** — project-side script.
* **Multi-user attribution** in canonical memory — ``understanding/``
  is anonymous-to-the-role; provenance lives in journal narrative.
* **Conflict resolution UI for memory merges** — not needed in
  practice because the design sidesteps overlapping writers.
* **Per-team SMAK partitioning** — whole-index sharing only;
  file-level filtering needs SMAK-side namespace support that
  doesn't exist yet.
* **Subscription-update notifications** — pulling a fresh upstream
  is a manual ``allmight share pull --force``; no push.
