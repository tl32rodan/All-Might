# Team Share

Two patterns for sharing All-Might across a team. They serve
different needs and both are first-class.

| | Mode 1: Bundle share | Mode 2: Instance share |
|---|---|---|
| Unit | One personality, packaged | A whole All-Might project |
| Use | Receiver imports + customises | Multiple users `cd` into the same path |
| Transport | Git remote (NFS bare repo, internal Gerrit/Gitea, https/ssh) | Filesystem-shared NFS path |
| Suits | General starter kits, individual personalities | Service-style roles (e.g. team review agent) |

## Mode 1 — Bundle share via git-as-hub

### Setup

Pick any URL the local `git` can reach. The simplest is a bare repo
on shared NFS:

```bash
# One-time, on a host that can write to the team NFS:
mkdir -p /nfs/team/personalities/stdcell_owner.git
cd /nfs/team/personalities/stdcell_owner.git
git init --bare --initial-branch=main
```

Or skip the manual step — `allmight share publish` runs `git init
--bare` automatically when the target is a `file://` URL that
doesn't yet exist.

### Publishing

`/one-for-all` is the canonical way to produce a reviewed bundle.
It is agent-driven so it can ask for consent on every file
containing likely PII. The CLI's `share publish` is a pure
transport — it takes an existing bundle directory and pushes it.

```bash
# Inside Claude Code or OpenCode, run:
> /one-for-all

# That writes ./stdcell_owner-export/. Then on the shell:
allmight share publish ./stdcell_owner-export/ \
    --to file:///nfs/team/personalities/stdcell_owner.git \
    --message "stdcell_owner v1.0"
```

The publish step:
1. Validates the bundle has a `manifest.yaml`.
2. Initialises the bare repo if it's a local path that doesn't exist.
3. Clones the remote, copies the bundle on top, commits, pushes.
4. Records the upstream URL + bundle_id in
   `.allmight/upstream.yaml` (per personality).

### Pulling

```bash
allmight share pull file:///nfs/team/personalities/stdcell_owner.git
allmight share pull file:///nfs/team/personalities/stdcell_owner.git \
    --as stdcell_v2     # rename on import
```

Pull is `git clone` + `allmight import` + upstream bookkeeping. The
imported personality's lineage lands in
`.allmight/personalities.yaml` as a single-entry `derived_from`
list (`kind: bundle`, with `bundle_id` and `bundle_version`).
Re-exporting via `/one-for-all` carries that ancestry forward into
the new bundle's `derived_from` field, so multi-hop provenance is
preserved across teams.

If the receiver wants to fold the bundle into an existing
personality instead of installing it under a fresh name, `share
pull` will fail (it inherits `allmight import`'s collision
behaviour) and the receiver should run `/all-for-one` in the agent
to perform the merge — that skill takes the bundle path plus the
existing personality's name and dialogs through the per-file
conflicts.

### Manifest schema (schema_version 3)

```yaml
allmight_version: '0.1.0'
schema_version: 3
personality_name: stdcell_owner

# Lineage (all optional, omitted on first export from a freshly-
# created personality with no derivation history)
bundle_id: 7c4f3a2e-1111-2222-3333-444455556666     # uuid4, fresh per export
bundle_version: 1.0.0                                # semver of THIS bundle's content
derived_from:                                        # source descriptors, may be empty
  - kind: bundle                                     # prior bundle ancestor
    bundle_id: 11111111-2222-3333-4444-555555555555
    bundle_version: 0.9.0
  - kind: personality                                # in-project source consumed by /all-for-one
    name: pll_owner

capabilities:
  database:
    capability_version: 1.0.0
  memory:
    capability_version: 1.0.0

exported_at: '2026-05-04T10:00:00Z'

# Shared-SMAK subscriptions (optional, omit if no shared SMAK)
database_subscriptions:
  - index: stdcell                                   # matches database/config.yaml entry
    nfs_path: /nfs/smak/stdcell                      # where the shared SMAK index lives
    last_validated_against: 2026-04-15
    required: true                                   # warn loudly if missing on import
```

The three version concepts are independent:

* `allmight_version` — framework version
* `capabilities.<cap>.capability_version` — per-template version
* `bundle_version` — content-level semver of *this* bundle

Bump `bundle_version` when the personality's content reaches a
milestone. The framework does not auto-bump it.

## Mode 2 — Instance share over NFS

### Layout

A team-shared All-Might project lives at a NFS path that all members
can reach:

```
/nfs/team/review-allmight/                ← owned by a dedicated unix account
├── AGENTS.md
├── MEMORY.md
├── .allmight/
├── .opencode/
└── personalities/
    └── review/
        ├── ROLE.md
        ├── memory/
        │   ├── MEMORY.md                 ← canonical, curator-edited
        │   ├── understanding/
        │   ├── journal/
        │   ├── lessons_learned/
        │   │   ├── _inbox/               ← users write here during sessions
        │   │   └── _reviewed/            ← curator's "kept after audit" landing
        │   └── store/
        └── database/
            └── config.yaml               ← points at /nfs/smak/<index>
```

### Recommended permissions

```bash
# Dedicated unix account owns the tree. Group write so members can
# contribute to lessons_learned/_inbox/. Setgid bit on directories
# keeps group ownership consistent on new files.
chown -R review-bot:review-team /nfs/team/review-allmight
chmod -R 770 /nfs/team/review-allmight
find /nfs/team/review-allmight -type d -exec chmod g+s {} +
```

The framework does not enforce these — it writes files; the user's
umask and the dir's setgid bit own permissions.

### Lessons-learned curation workflow

The split between `_inbox/` and `_reviewed/` exists because in a
shared instance, every session writing into the canonical
understanding/ surface would create wiki-style chaos with no audit
trail.

**Write-side** (during a user's session):

The user runs `/remember` and the agent — guided by the memory
keeper's ROLE.md — recognises that the observation is a
"lesson-learned-worth-flagging-for-curator" rather than authoritative
canonical knowledge. It writes:

```
memory/lessons_learned/_inbox/<ISO-8601>-<unix_user>.md
```

The filename is per-user-per-timestamp, so concurrent reviewer
sessions never collide on the same file. No file locks needed.

**Audit-side** (curator's periodic job, project-side):

A periodic script (out of scope for All-Might itself) walks
`_inbox/`, optionally cross-references with the SOS revision
summary, and produces an audit packet for the curator to walk
through. For each `_inbox/` entry:

* **Keep**: move to `_reviewed/`
* **Promote**: distill into `understanding/canonical.md`
* **Discard**: delete

The framework ships only the layout, not the audit job. A simple
weekly cron + markdown report is enough to start.

### Concurrency

The instance-share design sidesteps file-level locking by keeping
write boundaries non-overlapping:

| Action | Writer | Collision risk |
|---|---|---|
| `/remember` to lessons_learned/_inbox/ | per-user-per-timestamp file | none |
| Append to journal/<workspace>/ | per-session timestamped file | none |
| Edit canonical understanding/ files | curator only | none |
| Search SMAK | read-only | none |

If a curator edits canonical files while a session is reading, the
session sees a snapshot until its next read. Acceptable for the
low-frequency human curation cycle this design assumes.

## Shared SMAK as source of truth

The canonical pattern: one NFS-hosted SMAK index per team, written
by a single dedicated unix account ("the bot"), read by everyone.
Single-writer eliminates the multi-tenant SMAK problem at its root.

```
/nfs/smak/<index>/                        ← bot writes, group reads
  ├── faiss.index
  ├── metadata.json
  └── ...
```

The bot performs **atomic-rename ingest** to avoid partial reads:

```bash
# In the bot's ingest job:
ingest_to /nfs/smak/<index>.tmp/        # write to a side directory
mv /nfs/smak/<index> /nfs/smak/<index>.old
mv /nfs/smak/<index>.tmp /nfs/smak/<index>
rm -rf /nfs/smak/<index>.old
```

Personality-side `database/config.yaml` points at the canonical
path:

```yaml
indices:
  - name: stdcell
    description: "Standard cell library characterisation data"
    paths: ["/nfs/smak/stdcell"]
```

When this personality is exported, the resulting `manifest.yaml`
records the dependency under `database_subscriptions`. On import in
a project that hasn't mounted the team NFS yet, the receiver sees a
warning per missing subscription but the import still succeeds —
the receiver can mount NFS and re-run `/ingest` later.

## SMAK update request schema

Personalities submit SMAK update requests when their reviewed
content needs to make it into the canonical index. The framework
documents the payload format but does **not** ship a generator —
each personality author writes a skill that fits their review flow.

Recommended Level-1 payload:

```json
{
  "changed_files": ["src/cell_A.v", "src/cell_B.v"],
  "submitted_by": "<unix_user>",
  "review_id": "<uuid>"
}
```

The receiver service (out of scope for All-Might — lives in a
separate repo) takes this payload, fetches the named files from
SOS, and appends to the bot's atomic-rename ingest queue.
`review_id` lets the bot trace each ingestion back to the review
session that produced it.

## What's not covered yet

These limitations are documented, not bugs:

* **Audit packet generation**: project-side script, not in framework.
* **Multi-user attribution in canonical memory**: `understanding/`
  files are anonymous-to-the-role. Disagreement and provenance live
  in journal narrative, not metadata.
* **Conflict resolution UI for memory merges**: not provided.
  Concurrent edits to the same canonical file are last-writer-wins;
  the layout above sidesteps this in normal operation.
* **Per-team SMAK partitioning**: the framework assumes whole-index
  sharing. File-level filtering of an NFS-hosted index requires
  SMAK-side namespace support that doesn't exist yet.
* **Subscription-update notifications**: pulling a fresh upstream
  bundle is a manual `allmight share pull --force`. There is no
  push notification when an upstream personality changes.
