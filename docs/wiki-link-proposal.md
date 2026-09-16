# Linked Personalities — one wiki repo, N flow repos (proposal)

Status: **draft for review**. Nothing in this document is implemented.

## 1. Problem

A team runs one All-Might project per EDA flow (`flow-stdcell`,
`flow-pll`, …; each its own Gitea repo, each driven by a *flow-owner*
agent) plus one dedicated *wiki* project (`wiki`, one Gitea repo)
whose agent builds the team wiki out of what the flows know.

Every flow project carries a personality called `wiki` — the role
that writes flow knowledge *for the team*, as opposed to the flow's
own working memory. Today the only way to move that personality is
`/one-for-all` → `allmight share publish` → `allmight share pull`,
which is a **copy**: after the pull the two sides diverge, nothing
tells the wiki agent a flow changed, and nothing carries a curator's
fix back to the flow (`docs/team-share.md`, "What's not covered yet":
*no subscription-update notifications*).

What is wanted instead is a **link**: the same personality checked
out in two projects, with git as the sync medium, Gitea PRs as the
review gate, and the existing hooks providing the "you have unsynced
changes" nudge.

Constraints given:

- exactly one repo per flow, one repo for the wiki — no third
  "bundle hub" repo per flow;
- use Gitea submodules;
- a flow-owner update must surface on the wiki side as a PR.

## 2. Topology (decision)

The **wiki repo is the hub**. Each flow's `wiki` personality lives on
its own orphan branch of the wiki repo, `flow/<flow>`, whose root is
the personality directory (the same layout `/one-for-all` bundles
already use). The flow repo mounts that branch as a submodule at
`personalities/wiki/`; the wiki repo's own checkout mounts every
`flow/*` branch under `personalities/<flow>/` as a git worktree.

```
Gitea: team/flow-stdcell.git                 Gitea: team/wiki.git
  main                                         main            ← wiki agent's project
  ├── AGENTS.md, MEMORY.md, .opencode/          ├── AGENTS.md, MEMORY.md, .opencode/
  ├── personalities/                            ├── personalities/
  │   ├── stdcell_owner/   (real dir)           │   ├── editor/          (real dir, wiki agent's own role)
  │   └── wiki/            (SUBMODULE ──────┐   │   ├── stdcell/         (worktree of flow/stdcell, gitignored)
  └── .gitmodules                          │   │   └── pll/             (worktree of flow/pll,     gitignored)
        url    = ../wiki.git               │   ├── wiki/                (built output — see §7)
        branch = flow/stdcell              │   └── .allmight/personalities.yaml  lists editor + stdcell + pll
                                           │
                                           │  flow/stdcell     ← orphan branch = ONE personality dir
                                           └─▶ ├── manifest.yaml   (schema_version 3, link: {...})
                                               ├── ROLE.md
                                               ├── commands/  skills/
                                               ├── memory/{config.yaml, understanding/, journal/}
                                               ├── .gitignore        (memory/store/)
                                               └── .gitattributes    (memory/understanding/_index.md merge=union)
                                              flow/stdcell-wip  ← flow owner's push target; PR → flow/stdcell
                                              flow/pll, flow/pll-wip, …
```

Why this shape and not the alternatives considered:

| Alternative | Rejected because |
|---|---|
| Submodule → flow repo's `wiki-export` branch produced by `git subtree split` (flow repo is the source of truth) | Reverse direction (curator fix → flow) needs a `subtree merge` + a PR *in every flow repo*; the wiki side needs a pointer-bump PR per flow per change. Two automation paths instead of one. |
| Submodule → wiki repo `main`, plus `personalities/wiki → ../.hub/personalities/stdcell` symlink | Every flow clone carries every flow's knowledge; personality dir becomes a symlink, which none of the hooks / `compose` / memory-history were written for (`Path.rglob` symlink semantics differ by Python version). |
| One bundle repo per flow (`wiki-stdcell.git`) | Violates the two-repo-kinds constraint; also 2N+1 repos to protect. |
| Wiki `main` holds flows as self-referencing submodules (`url = ./`) | Every flow merge needs a pointer-bump commit on `main`; `clone --recurse-submodules` clones the repo into itself N times. Worktrees give the same "live view" with no pointer to maintain. Kept as an opt-in (`--mode submodule`) for teams that want the pinned SHA visible in Gitea's tree view. |

Properties that fall out of the chosen shape:

- `personalities/wiki/` in the flow repo is a **plain directory** at
  runtime. `compose`, `compose_agents_md`, `role-load`, the
  memory-history mirror and the L3 ingest closure all work unchanged.
- A flow's clone contains **only its own** wiki personality.
- The branch root **is** a bundle. `share publish --branch
  flow/<flow>` already pushes a bundle dir to a branch root of a
  remote (`share/git_share.py::publish_bundle`), so first-time
  registration is the existing publish path plus a `git submodule
  add`.
- The wiki agent sees every flow **live** after `git pull --ff-only`
  in each worktree — no pointer bump, no bump-PR bot.
- All review happens in **one** repo (`wiki`), under a single branch
  protection rule (`flow/*`).

## 3. Branch and review policy

| Branch (in `wiki.git`) | Writer | Reviewer | Merge style |
|---|---|---|---|
| `flow/<flow>` | nobody directly — **protected** | — | — |
| `flow/<flow>-wip` | flow-owner agent (`allmight share push`) | wiki curator | PR → `flow/<flow>`, **fast-forward only** |
| `curated/<flow>-<topic>` | wiki agent (curator edits inside its worktree) | flow owner | PR → `flow/<flow>`, fast-forward only |
| `main` | wiki agent / admin | as the team likes | any |

Fast-forward-only (Gitea ≥ 1.22 merge style) matters: after the PR
merges, `flow/<flow>` and `flow/<flow>-wip` point at the **same**
commit, so the submodule pointer the flow repo recorded (which pointed
at a wip commit) is now also on the accepted branch. No history
rewrite, no divergence, no post-merge reset. Gitea auto-updates an
open PR when its head branch receives new pushes, so `share push`
opens a PR only when none is open — one PR per flow at a time, not
one per session.

Symmetric review: the curator approves what flows publish; the flow
owner approves what the curator changes in their knowledge. Both go
through the same protected branch. Gitea branch protection (set once
by the admin, project-side, not All-Might's job):

```
pattern: flow/*        required approvals: 1     merge: fast-forward-only
```

Conflict surface is small by construction:

| Path | Both sides write? | Resolution |
|---|---|---|
| `memory/journal/**` | yes | never conflicts — one timestamped file per entry (`journal_schema.py`) |
| `memory/understanding/_index.md` | yes (both append rows) | `.gitattributes: merge=union`, written by `share link` into the branch root |
| `memory/understanding/<page>.md` | rarely | ordinary git conflict; `share sync` stops, leaves markers, prints the file list. The agent resolves them like any code conflict — no new dialog skill. |
| `ROLE.md` | curator via PR only | the flow owner reviews |
| `manifest.yaml` | `share link` once, `share push` bumps `bundle_version`/`exported_at` | last writer wins, nothing semantic in it |

## 4. Alignment mechanisms

Four movements, two of them automatic, two agent-triggered on a
nudge. Every automatic step is a marker touch or an async `git fetch`;
nothing does network I/O on a turn's hot path (same rule as the L3
ingest closure).

### 4.1 Flow write → `.allmight/share.pending` (automatic, per turn)

`memory-history.ts` / `memory_history.py` (Stop hook) already walk
`personalities/*/memory/` for the ingest marker. Add one check next to
`maybeMarkIngestPending`: if any file under a **linked** personality
is newer than `.allmight/last_share`, touch `.allmight/share.pending`.
"Linked" = names listed under `links:` in `.allmight/upstream.yaml`
(read once per invocation; ≤ 1 ms). Both surfaces, one shared Python
generator for any emitted text — dual-platform invariant.

### 4.2 Nudge → `allmight share push` (agent, on nudge)

`memory-load.ts` / `memory_load.py` (session start) already drain
`ingest.pending`. Add: if `share.pending` exists, inject one line —
`_share_nudge_text()`, a single Python generator substituted into both
surfaces — telling the agent to run `allmight share push` when the
session's writing is done. No slash-command body grows (size budget
test); the CLI is the canonical reference.

`allmight share push [<name>]`:

1. `git -C personalities/<name> add -A && commit` — message from the
   memory-history summary of the same paths (`MemoryHistory._summarise_changes`).
2. Rebase local commits onto `origin/flow/<flow>` (picks up curator
   merges; conflicts → stop with file list, exit 2).
3. `git push origin HEAD:flow/<flow>-wip`.
4. Ensure a PR `flow/<flow>-wip → flow/<flow>` exists. With
   `GITEA_TOKEN` in the environment: `POST /api/v1/repos/{owner}/{repo}/pulls`
   (idempotent: list open PRs for that head first). Without a token:
   print the Gitea compare URL and stop — the human clicks. API base
   is derived from the `https://` remote; `ssh://` remotes need
   `api_url:` in the link record.
5. Commit the superproject pointer bump? **No.** The flow repo's own
   commit is the user's (the flow project is their repo). `share push`
   prints `personalities/wiki` pointer moved: commit it with your next
   change.
6. Touch `.allmight/last_share`, remove `share.pending`.

Refuses to push when the diff matches a small secret denylist
(private keys, `token=`, AWS-style ids) — advisory guard, the real
PII discipline lives in the personality's ROLE.md (§6).

### 4.3 Wiki side ← flows (automatic fetch, agent pull)

The wiki agent's session-start hook spawns `allmight share status
--fetch` async (one `git fetch origin 'refs/heads/flow/*'`). Its
output — `stdcell: 3 behind`, `pll: up to date` — is written to
`.allmight/share.stale` and injected on the *next* session start,
same delay trade-off as L3 ingest. The agent runs `allmight share
sync` (`git pull --ff-only` in every stale worktree, then `allmight
compose` so `AGENTS.md` and `.opencode/agents/<flow>.md` track ROLE.md
changes).

A Gitea Action in `wiki.git` (`on: pull_request: types: [closed]`)
is **optional** and project-side; it would only shorten the delay.

### 4.4 Flow side ← curated edits

Identical to 4.3 with one worktree: `share status --fetch` on the flow
repo compares `personalities/wiki` HEAD with `origin/flow/<flow>`;
`share sync` fast-forwards. If the flow has local unpushed commits,
`sync` rebases them (same step as 4.2 / 2).

## 5. CLI surface

All new verbs live under the existing `share` group; `cli.py` stays
closed against templates (they are lifecycle commands, like `pull`).
Git and Gitea mechanics go to `share/link.py` and `share/gitea.py`;
`cli.py` only parses and prints.

```
allmight share link <git-url> --as <local-name> --branch flow/<flow>
                    [--capabilities memory] [--mode submodule|worktree]
allmight share push   [<local-name>]        commit + push wip branch + ensure PR
allmight share sync   [<local-name>|--all]  ff-only pull (rebase local commits), then compose
allmight share status [--fetch]             ahead/behind per link; --fetch does one git fetch
allmight share unlink <local-name>          remove the mount; quarantine nothing — the branch stays on the hub
```

### `share link` — two cases

**Branch does not exist on the hub (first registration, flow side):**

1. `allmight add`-equivalent install into a temp dir (the *memory*
   template's `install`, nothing else — see §6 on capabilities), plus
   `manifest.yaml` (schema 3, `link:` block below), `.gitignore`
   (`memory/store/`), `.gitattributes` (`_index.md merge=union`).
2. `publish_bundle(tmp, url, branch="flow/<flow>")` — existing code
   path, pushes an orphan root.
3. `git submodule add -b flow/<flow> <url> personalities/<local-name>`.
4. Registry row: `derived_from: [{kind: link, url, branch}]`; link
   record in `.allmight/upstream.yaml`; `compose`; `compose_agents_md`;
   `compose_role_agents`.

**Branch exists (wiki side, or a second flow checkout):**

Step 1–2 are skipped. `--mode worktree` (default on the hub itself,
detected by `origin` == the link URL) does `git worktree add
personalities/<local-name> flow/<flow>` and appends the path to
`.gitignore`; `--mode submodule` does step 3.

`manifest.yaml` gains one optional block; everything else is
schema-3 as documented in `team-share.md`:

```yaml
link:
  hub: ../wiki.git          # relative URL — resolves from any clone of the org
  branch: flow/stdcell
  wip_branch: flow/stdcell-wip
  api_url: https://gitea.example/api/v1   # optional; derived from hub when https
```

### `.allmight/upstream.yaml` extension

```yaml
personalities:            # existing bundle records, untouched
  ...
links:
  wiki:                    # local personality name
    hub: ../wiki.git
    branch: flow/stdcell
    wip_branch: flow/stdcell-wip
    mode: submodule
    last_share: '2026-09-16T08:00:00Z'
    last_synced_commit: 3fa2c…
```

The hooks read `links:` to know which personality dirs count for
`share.pending` (§4.1). `allmight list` renders linked rows with a
`↔ flow/stdcell` suffix and `(not checked out)` when the submodule is
uninitialised — a fresh `git clone` without `--recurse-submodules`
leaves an empty dir; `share sync` runs `git submodule update --init`
in that case instead of failing on a missing ROLE.md.

### `DerivedFrom` — third kind

```python
kind == "link": url, branch populated; bundle_id / bundle_version / name empty.
```

`/one-for-all` on a linked personality carries the link descriptor
forward in the bundle's `derived_from`, so a bundle exported from a
flow's wiki personality still says where its upstream is.

## 6. What the linked personality is

- **Capabilities: `memory` only.** `database/` workspaces reference
  flow-local source paths and a flow-local SMAK store; neither exists
  on the wiki side. The wiki agent's *editor* personality owns the
  `database` capability and indexes what it needs (§7). `share link
  --capabilities database,…` is rejected with that explanation.
- **`memory/store/` is per-side.** Gitignored in the branch; each side
  rebuilds its L3 index through the existing auto-ingest closure.
- **One ROLE.md serves both roles.** In the flow project it reads as
  "you are `wiki`: write what the *team* needs to know about this
  flow"; in the wiki project the same file makes `personalities/stdcell/`
  the stdcell knowledge source. The `allmight add`-time template for a
  linked personality adds one paragraph: everything written under this
  personality is pushed to the team hub and reviewed by people outside
  this flow — no credentials, no personal data, no customer names.
  PII discipline moves from export time (`/one-for-all`'s per-file
  consent) to write time, which is the only place it can live for a
  personality whose purpose is to be shared.
- **`commands/` and `skills/` travel with it.** A flow-specific skill
  the flow owner wrote under `personalities/wiki/skills/` is composed
  into the wiki agent's `.opencode/skills/` on the next `share sync`;
  basename clashes across flows land in
  `.allmight/templates/conflicts.yaml` for `/sync` like any compose
  conflict.

## 7. The wiki agent's own role and the built wiki

The wiki agent's project has one real personality, `editor`
(`database` + `memory`), plus N linked `personalities/<flow>/`. The
framework ships `editor` only as a **suggestion-catalog entry**
(`personality_suggestions.py`: `wiki_editor`, keywords `wiki`,
`curate`, `handbook`, `documentation`) so `/onboard` can create it.
Its ROLE.md describes the job — read every linked personality's L2
`understanding/`, reconcile, write the team pages, open
`curated/<flow>-<topic>` PRs when a flow's page needs a fix rather than
editing the flow's file in place. The *how* is a runtime skill the
agent writes under `personalities/editor/skills/` (the `/reflect`
skill-check path), not a framework-shipped body: it is one team's
editorial process, not a capability.

Cross-flow integration is where `/all-for-one` is **not** used: the
flow personalities stay separate sources; the editor composes.
`/all-for-one` remains available for the one-off case of folding a
retired flow's branch into another.

Built output lives in `wiki.git:main:/wiki/` — plain markdown,
versioned with the sources it was built from, reviewable by PR. Each
page carries a footer `built from flow/stdcell@3fa2c…` (the worktree
HEAD at build time) — that is the provenance a pointer-less worktree
would otherwise lose. Mirroring `/wiki/` into Gitea's built-in Wiki
(`wiki.wiki.git`) is a five-line project-side Gitea Action on
`push: paths: [wiki/**]`; All-Might does not ship it.

## 8. Bootstrap walkthrough

```bash
# Admin, once — the hub
git clone ssh://gitea/team/wiki.git && cd wiki
allmight init . && /onboard          # → editor (wiki_editor suggestion)
git add -A && git commit -m "wiki agent scaffold" && git push
# Gitea UI: protect flow/*, 1 approval, fast-forward-only

# Flow owner stdcell — register the link
cd flow-stdcell
allmight share link ../wiki.git --as wiki --branch flow/stdcell
#   → pushes orphan flow/stdcell, adds submodule personalities/wiki
git commit -am "link wiki personality" && git push

# Wiki agent — mount it
cd wiki
allmight share link ../wiki.git --as stdcell --branch flow/stdcell   # worktree mode auto-detected
git commit -am "mount stdcell" && git push        # registry row + .gitignore line only

# Daily, flow side
… /remember … (Stop hook touches share.pending)
allmight share push          # commit → flow/stdcell-wip → PR opened or refreshed

# Daily, wiki side
allmight share sync --all    # ff-only pull every flow, compose
… /wiki-build (editor's runtime skill) … git push main
```

## 9. Rules check (against CLAUDE.md)

| Rule | How the design complies |
|---|---|
| `cli.py` closed against templates | `share link/push/sync/status/unlink` are lifecycle commands like `share pull`; git + Gitea mechanics live in `share/link.py`, `share/gitea.py`. |
| `core/` closed against capabilities | `DerivedFrom.kind == "link"` is a data-model addition in `core/personalities.py`; `share/` imports core, never the reverse. |
| Template owns its dir only | The memory template writes `personalities/<name>/` exactly as today; `share link` (not the template) adds `manifest.yaml`, `.gitignore`, `.gitattributes` to the branch root — the same way `/one-for-all` writes a bundle's manifest outside any template. |
| Markers | `manifest.yaml`, `.gitattributes`, the ROLE.md paragraph all carry `ALLMIGHT_MARKER_*`. |
| init is additive | `share link` never deletes; `share unlink` removes the mount (`git submodule deinit` / `worktree remove`) and the registry row but the branch on the hub is untouched — that *is* the quarantine. |
| Re-init skips skill writes | No new skill or command body. The two nudges are hook-emitted one-liners from shared Python generators. |
| Dual-platform invariant | `memory-history` + `memory-load` change on **both** surfaces; `_share_nudge_text()` is the single generator; `PLUGIN_MANIFEST.requires` unchanged (marker touch + async spawn are already-used capabilities). |
| No Composer pattern | Cross-side state flows through git and `.allmight/upstream.yaml`, never process memory. |
| OFA / AFO asymmetry | Untouched. A link is a *mount*, not a transfer; `/one-for-all` and `/all-for-one` keep their roles (§7). |
| Add a flag, not a capability | No new capability; the wiki personality is a `memory` personality with a link record. |
| Body size budget | Zero body growth. |

## 10. Implementation tracks

Each track ends green on `PYTHONPATH=src python -m pytest tests/`;
T3 also type-checks the generated plugins (`tsc --noEmit`).

| Track | Scope | Tests (TDD — written first) |
|---|---|---|
| **T1 — link model + mount** | `DerivedFrom` kind `link`; `links:` in `upstream.yaml` (`read_links` / `write_links`); `share/link.py`: `link()` both cases, `sync()`, `status()`, `unlink()`; `share link/sync/status/unlink` CLI; `allmight list` suffix. Submodule and worktree modes. | Two local bare repos as hub + flow (`file://`); assert branch root layout, `.gitmodules`, registry row, `compose` output; `sync` ff-only, rebase of local commits, conflict → exit 2 with file list; uninitialised submodule → `update --init`; `--capabilities database` rejected. |
| **T2 — push + Gitea PR** | `share/gitea.py`: minimal client (`urllib`, `GITEA_TOKEN`), `ensure_pull_request(head, base, title)`; `share push` end-to-end incl. secret denylist and `last_share` bookkeeping; `api_url` derivation from https remotes. | Fake Gitea via `http.server` in-test: PR created once, second push only pushes; no token → compare URL printed, exit 0; denylist hit → exit 3, nothing pushed. |
| **T3 — hooks** | `maybeMarkSharePending` next to `maybeMarkIngestPending` (TS + PY); `share.pending` nudge in `memory-load` (TS + PY); `_share_nudge_text()`; `share.stale` async fetch on session start; `KNOWN_*` unchanged (no new plugin files). | `test_memory_init.py` siblings on both surfaces incl. negative assertions; `TestHooksRunCleanly` still passes; `test_hook_output_budget.py` covers the added line. |
| **T4 — wiki side** | `wiki_editor` suggestion + linked-personality ROLE.md paragraph generator; `docs/team-share.md` gains "Mode 3 — Linked personality" (pointing here); README compatibility note. | Suggestion seeded with marker; ROLE.md paragraph present only for linked installs. |

Deferred, deliberately: a Gitea Action that opens PRs or bumps
pointers (project-side, not framework), a `/share` slash command
(the CLI + nudge suffice; a body would restate `--help`), and any
cross-flow merge tooling (the editor composes, it does not merge).

## 11. Open questions for review

1. **wip branch per flow vs. per host.** One `flow/<flow>-wip` assumes
   one writer per flow. If a flow project is Mode-2 instance-shared
   (several people, same NFS checkout) that still holds — one
   checkout, one branch. If several *clones* of one flow exist,
   `share push` should use `flow/<flow>-wip-<user>`; cheap to add,
   not in T2 unless wanted.
2. **Who commits the flow repo's pointer bump.** The proposal leaves
   it to the user's next commit of the flow project (the flow repo is
   theirs; All-Might's memory-history mirror is a separate `.git`).
   Alternative: `share push --commit-superproject`.
3. **Fast-forward-only** needs Gitea ≥ 1.22. On older Gitea use
   "rebase then fast-forward"; `share sync` then has to reset the
   local wip branch to `origin/flow/<flow>` after a merge (detects
   "PR merged and branches diverged"). One extra branch in T1's tests.
4. **`GITEA_TOKEN` scope.** `write:repository` on the wiki repo is
   enough for PR creation; the token is read from the environment
   only, never written to any `.allmight/` file.
