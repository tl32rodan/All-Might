# Part D — Implementation Plan (Cognitive Alignment Doc)

This file is the kickoff artefact for a fresh session resuming the
Part D refactor. It leads with **why** before **what** so the next
agent inherits the same mental model the user has already pinned
down — twice, after two pivots in the planning conversation.

The full design discussion lives at
`/root/.claude/plans/detorit-smak-reactive-bee.md` (Parts A–D, ~2000
lines). Read this PLAN.md first, then dip into that file for the
detail of any specific commit.

---

## 1. Core philosophy

### 1.1 A personality is a *role*, not a *tool*

The single biggest mental shift in Part D: **personalities are roles
the user defines** (e.g. `stdcell_owner`, `pll_owner`,
`code_reviewer`), not framework-internal toolkits. A personality
bundles:

* A `ROLE.md` that tells the agent who this is and what it cares
  about.
* Zero-or-more **capabilities** — internal data subdirs the agent can
  use to act in that role (`database/` for an external knowledge
  graph, `memory/` for conversational memory).

The framework owns the capabilities. The user owns the personalities.
"Adding a new personality" is a directory + a ROLE.md, not a code
change.

> Pre-Part-D, the framework had it backwards: `corpus_keeper` and
> `memory_keeper` were the personalities, and topics like *stdcell*
> were data scattered inside them. Part D inverts that.

### 1.2 One global agent surface; the agent routes by context

There is **one** `.opencode/` per project, with **one** set of slash
commands (`/search`, `/remember`, `/recall`, `/enrich`, `/ingest`,
`/sync`, `/onboard`). The user types the same command regardless of
how many personalities the project has.

The agent reads `MEMORY.md` (which contains the project map of
personalities + scopes + a `default_personality` hint) plus the
current conversation, and **decides which personality to act for**.
Once it picks `<p>`, it operates on `personalities/<p>/database/`
and `personalities/<p>/memory/`.

> Personality names **never** appear in slash-command syntax. No
> `/stdcell_owner:search`. The hierarchy is a data-and-reasoning
> structure, not a UX prefix.

### 1.3 Composition is build-time, not runtime

Symlinks are written at install time; OpenCode resolves them on file
open; no Python process mediates dispatch at runtime. "The agent
routes by context" is the agent's job, not a runtime dispatcher.

This is why command bodies become **generic**: one `search.md` body
that says "read MEMORY.md, pick the active personality, run smak
search against `personalities/<active>/database/config.yaml`". Not
N pre-rendered bodies with bound paths.

### 1.4 A template owns its directory, nothing else

Capability templates (`database`, `memory`) write only into:
1. Their share of the global `.opencode/` set (commands, skills,
   plugins they own — generic bodies).
2. Their data subdir under each personality
   (`personalities/<p>/database/` or `personalities/<p>/memory/`).

They do not touch other capabilities' files. They do not write
outside their dirs except for the documented exceptions (root
`AGENTS.md`, root `MEMORY.md`, `.allmight/personalities.yaml`,
staging at `.allmight/templates/...`).

### 1.5 Hierarchy is for management, not the user

Personalities and topics structure the data tree
(`personalities/<p>/memory/{understanding/<topic>.md, journal/<topic>/}`).
The user does not see them in the slash-command surface; they only
see them when inspecting a specific personality's dir for debug.

---

## 2. Architectural invariants (don't violate)

These rules are enforceable by reading a diff. Each came out of the
planning conversation as a non-negotiable.

1. **`corpus_keeper` is deprecated as a *personality* name.** It
   becomes the `database` *capability* internally. The legacy name
   `detroit_smak` was already deprecated in Part A and stays so.
2. **No per-personality command/skill/plugin namespacing.** Slash
   commands are flat. If a future capability ships its own
   `/whatever`, it lands at `.opencode/commands/whatever.md` once,
   not per-personality.
3. **Command bodies are generic.** No body may reference a concrete
   personality name. Every reference is the placeholder
   `personalities/<active>/...` resolved by the agent at runtime.
   Negative test in `test_command_body_generic.py` (commit 3 / 11).
4. **`personalities/<p>/{skills,commands}` are upward symlinks** to
   `.opencode/{skills,commands}`. They exist purely so a
   personality dir is browsable as a unit; they share the global
   surface.
5. **Project-wide plugins iterate `personalities/*/`** at runtime.
   No plugin hard-codes "the corpus instance" or "the memory
   instance".
6. **Markers are the contract.** Every framework-generated file
   carries an `ALLMIGHT_MARKER_*` token. Files without one are
   user-authored and preserved on re-init.
7. **`cli.py` is closed.** Per-template flags belong in
   `template.cli_options`, not in `cli.py`'s parameter list.
8. **`core/` does not import `capabilities/*`.** Dependency arrow
   points one way.

---

## 3. Status snapshot (where we are)

**Branch:** `claude/refactor-kg-memory-S4TiV`. Pushed.

**Commits done in Part D so far:**

| # | Hash | Summary |
|---|------|---------|
| 1 | `f350f90` | Renamed `allmight.personalities` → `allmight.capabilities`. Meta-path-finder shim at the legacy path so external code still resolves with a `DeprecationWarning`. 32 files moved, 338 tests green. |
| 2 | `4235e59` | `Personality` gains `capabilities: list[str]` + `role_summary`; `RegistryEntry` accepts both Part-C (`template`/`instance`/`version`) and Part-D (`name`/`capabilities`/`versions`) row shapes; writer always emits Part-D. 345 tests green. |

**Test count:** 345 passing as of `4235e59`.

**No semantic changes have shipped yet** — the directory rename
and data-model extension are scaffolding. The user-visible
behaviour of `allmight init` is unchanged: same prompts, same
output layout, same slash commands. The remaining 10 commits land
the actual Part D semantics.

---

## 4. Remaining commits (ordered)

Each commit must keep `PYTHONPATH=src python -m pytest tests/`
green. After commits that touch generated TypeScript, also run
`tsc --noEmit` per CLAUDE.md.

### Commit 3 — Capability templates write the global `.opencode/` once, with generic bodies
**Touch:** `capabilities/corpus_keeper/initializer.py` (rename to
`capabilities/database/`? — see open question Q2 in §6),
`capabilities/memory_keeper/initializer.py`, plus the body
templates they emit.

**What changes:** today each `template.install` renders command
bodies with hard-coded paths (`personalities/<instance>/...`).
After this commit, each capability writes its share of
`.opencode/{commands,skills,plugins}/` exactly once per project
with **generic bodies**: instructions that read MEMORY.md's
project map, pick the active personality, and address
`personalities/<active>/<capability>/...`.

The personality-side install (`template.install(ctx, personality)`)
now only writes the data subdir
(`personalities/<p>/{database,memory}/...`) and the `ROLE.md`.

**Critical test:** `test_command_body_generic.py` — `grep` every
emitted body for concrete personality names; the only
`personalities/...` substring allowed is the literal placeholder.

**Watch out:** the existing test suite has many assertions like
`"personalities/knowledge/commands/search.md" in result`. Those
now point at `.opencode/commands/search.md` instead. Expect a
wide test sweep; do it carefully, one test file at a time.

### Commit 4 — Project-wide plugins iterate `personalities/*/`
**Touch:** `core/personalities.py` (the `role-load.ts` writer),
`capabilities/memory_keeper/initializer.py` (the memory plugins
like `memory-load.ts`, `todo-curator.ts`).

**What changes:** every TS plugin currently fans out across two
hard-coded paths (`personalities/<corpus>/...`,
`personalities/<memory>/...`). Rewrite each to iterate
`personalities/*/` directories at runtime so adding a personality
needs no plugin edit.

**Critical test:** negative assertion that no plugin contains a
hard-coded two-path fan-out. Verify with `tsc --noEmit`.

### Commit 5 — Simplify `compose()`; write upward symlinks
**Touch:** `core/personalities.py::compose`.

**What changes:** drop the per-instance command/skill/plugin
composition (capability templates wrote them once in commit 3).
`compose()` now only:
1. Writes the upward symlinks
   `personalities/<p>/skills → ../../.opencode/skills` and
   `personalities/<p>/commands → ../../.opencode/commands`.
2. Detects user-authored files in `.opencode/` and stages them in
   `.allmight/templates/conflicts.yaml` (existing logic, kept).

**Critical test:** `test_upward_symlinks.py` — symlinks resolve
correctly; `--force` heals broken ones; adding a personality
recreates them.

### Commit 6 — `allmight personality` subgroup (`add` / `list`)
**Touch:** `cli.py`, new `personalities_runtime/manager.py`.

**What changes:** new CLI surface for personality lifecycle.
`add <name> --capability database --capability memory` creates
the dir, calls each capability's install, recomposes, appends to
`personalities.yaml`. `list` is a table.

`remove` is **out of scope** — still `NotImplementedError`.

### Commit 7 — `merge --personality`
**Touch:** `merge/merger.py`.

**What changes:** rename the current `--instance` flag (already
shipped in Part C) to `--personality`. A merge now moves the
personality's data dirs + `ROLE.md`; the global `.opencode/` is
untouched (it's already shared). Keep `--instance` as a
deprecated alias that warns.

### Commit 8 — Part-C → Part-D migrator
**Touch:** new `migrate/part_d.py`, chained from
`migrate/migrator.py`.

**What changes:** detect Part-C layout
(`personalities/knowledge/`, `personalities/memory/`,
`personalities/<x>/knowledge_graph/`, flat `.opencode/commands/`)
and rewrite to Part-D. Decision: **one personality per workspace**
(see §5). Topics survive as memory sub-organisation
(`memory/understanding/<topic>.md`,
`memory/journal/<topic>/`).

The Part-A → Part-C migrator (already shipped) chains into this:
running `allmight migrate` on a legacy project applies both
passes in order.

**Critical test:** `test_migrate_part_d.py` — fixture project with
Part-C layout; dry-run reports the rename table; apply produces
the Part-D layout exactly, including the `default_personality`
hint in MEMORY.md.

### Commit 9 — Simplify `init` UX
**Touch:** `cli.py::_init_callback`, `cli.py::_collect_onboard_answers`.

**What changes:** drop the three Part-C prompts (corpus name,
memory name, folders). One prompt: "Personality name?" with the
default = project-root dir name. Folders prompt deferred entirely
to `/onboard`.

`--yes` accepts the default and skips the prompt.

### Commit 10 — `/onboard` skill update
**Touch:** `capabilities/corpus_keeper/onboard_skill_content.py`
(or wherever the body lives after commit 3's rename).

**What changes:** procedure now classifies *personalities* (not
folders). Asks "what role?" and writes the answer to that
personality's `ROLE.md`. Populates the project map in `MEMORY.md`
with one row per personality + the `default_personality` hint
that drives runtime routing.

### Commit 11 — Generic command body rewrite
**Touch:** the actual content of
`.opencode/commands/{search,enrich,ingest,remember,recall}.md`.

**What changes:** rewrite each body so it (a) reads MEMORY.md's
project map, (b) picks the active personality from explicit
mention / conversation context / default, (c) operates on that
personality's data dir.

This is the **routing-by-agent contract** the architecture rests
on. If the bodies are unclear or under-specify the routing
discipline, the agent will guess wrong at runtime.

> Strongly consider co-authoring the bodies with the user — they
> have the clearest picture of how the agent should resolve
> ambiguous mentions.

### Commit 12 — Docs
**Touch:** `README.md`, `CLAUDE.md`.

**What changes:**
- README: explain personalities-as-roles, one-global-surface,
  agent-routes-by-context. Replace any layout examples that show
  per-personality command dirs.
- CLAUDE.md: add invariants from §2 above. Mark
  one-global-surface and command-bodies-are-generic as guardrails
  alongside the existing "no Composer pattern" / "deprecated:
  detroit_smak" rules.

---

## 5. Decisions already logged (do not re-litigate)

* **Default at `init --yes`** = project-root dir name. `init` in
  `/path/to/my-chip` creates `personalities/my-chip/`.
* **Migrator split rule** = one personality per workspace. Topics
  are memory sub-organisation, not separate personalities.
* **Slash-command surface** = one global set, no namespacing,
  agent routes by context.
* **`personalities/<p>/{skills,commands}`** = upward symlinks.
* **Personality vs topic** = personality is a role (`ROLE.md`);
  topic is a sub-subject inside one personality's memory.
* **`cli.py` stays template-agnostic.** Flags come from
  `cli_options`; no per-template branches in `cli.py`.

---

## 6. Open questions (settle before they bite)

1. **Capability vs personality wording in user docs.** README still
   calls bundles "personalities". Should `database` be the
   user-facing word, or stay "knowledge graph" in prose with
   `database/` only as the directory name?
2. **Capability templates as a new package or stay under
   `capabilities/`?** Plan §D.12 sketched
   `src/allmight/capabilities/` for the rename and that's where
   commit 1 landed. The internal subpackage names (`corpus_keeper`,
   `memory_keeper`) still use the old vocabulary. Open: rename to
   `capabilities/database/`, `capabilities/memory/`? Or keep the
   subpackage names and only rename the symbols
   (`PersonalityTemplate` → `CapabilityTemplate`)?
3. **Default-personality hint format in MEMORY.md.** §D.11 sketched
   it as a leading callout (`> Default personality: stdcell_owner
   ...`). Confirm the agent reliably picks it up at routing time
   with that format, or pick a more structured representation
   (frontmatter? a dedicated table column?).

---

## 7. How to know Part D is done

End-to-end success criteria — verify these at the end of commit 12:

```bash
PYTHONPATH=src python -m pytest tests/                          # all green

# Fresh init
rm -rf /tmp/demo_d && mkdir /tmp/demo_d && cd /tmp/demo_d
allmight init . --yes
ls personalities/                  # → demo_d/
ls personalities/demo_d/           # → ROLE.md, skills→.., commands→.., database/, memory/
ls .opencode/commands/             # → search.md, remember.md, … (one set)
ls -la personalities/demo_d/skills # → symlink to ../../.opencode/skills
tsc --noEmit .opencode/plugins/*.ts

# Add a personality
allmight personality add code_reviewer --capability memory
ls personalities/code_reviewer/    # → ROLE.md, symlinks, memory/  (no database/)
ls .opencode/commands/             # → unchanged (still one set)

# Migrate Part-C
cd /tmp/old_part_c
allmight migrate --dry-run         # → reports knowledge → <workspace_owner>
allmight migrate                   # → applies; layout matches /tmp/demo_d
```

Negative greps that must come back empty:

```bash
grep -rn "knowledge_graph/" personalities/                          # capability dir is database/
grep -rn "personalities/knowledge\|personalities/memory" .          # post-migration
grep -rn "personalities/[a-z_]*/" .opencode/commands/               # only <active>/ placeholder
```

OpenCode lists the same flat slash-command set as today —
`/search`, `/remember`, etc. No personality prefix.

---

## 8. Process discipline (from CLAUDE.md, restated)

* **Write plan files incrementally.** Stream-idle timeouts have
  lost whole plans before; this PLAN.md is *the* artefact.
* **Confirm core premises before drafting.** If something here
  reads ambiguous, ask in 30 seconds rather than redraft after
  rejection. Especially the open questions in §6.
* **Close every design session with a written artefact.** PLAN.md
  is updated as commits land — append a status row in §3 after
  each push.
* **After code changes, run `pytest` *and* `tsc --noEmit`** when
  generated TypeScript changed (commits 3, 4, 5 all qualify).

---

## Cross-references

* Full design: `/root/.claude/plans/detorit-smak-reactive-bee.md`
  Parts A–D.
* Part D detail: §D.1 onwards in that file (D.4 verdict, D.7
  composition, D.9 migrator, D.13 commit plan).
* Project conventions: `/home/user/All-Might/CLAUDE.md`.
