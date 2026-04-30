"""Bundled /onboard skill and command content.

Installed by ``corpus_keeper`` on every init (legacy and registry-driven).
The skill walks the agent through the second stage of bootstrap that
``allmight init`` deferred: capturing the user's intent in each
personality's ``ROLE.md`` and classifying any folders the user
listed during init.

Why corpus_keeper owns it: ``/onboard`` is a cross-personality skill,
but it has to live in *one* template. Corpus is the lead personality
during bootstrap (the user's first question is "what knowledge should
I manage?") so it's the natural home.
"""

ONBOARD_SKILL_BODY = """\
# Onboard — finish All-Might setup inside the agent

> Run this skill after `allmight init` to capture the user's intent in
> each personality's `ROLE.md` and classify any folders they listed.

## When to use

- Right after `allmight init` (the CLI prints "Run /onboard to finish
  setup"). The marker file `.allmight/onboard.yaml` exists and has
  `onboarded: false`.
- The user explicitly asks to re-onboard (re-classify a folder, edit a
  role description). `.allmight/onboard.yaml` exists with `onboarded:
  true`; ask the user what specifically to change before re-running
  the full procedure.

## Procedure

### 1. Read the captured state

```bash
cat .allmight/onboard.yaml
```

You'll see something like:

```yaml
onboarded: false
personalities:
  - template: corpus_keeper
    instance: knowledge
  - template: memory_keeper
    instance: memory
folders:
  - path: src/
  - path: docs/
```

If `onboarded: true`, ask the user which step to redo (role text,
folder classification, both) and skip the rest of the procedure
accordingly.

### 2. Customize the corpus role

Ask the user a single open-ended question:

> **"What knowledge do you want to manage in this project?"**

Keep the answer short — a paragraph or two. Then rewrite
`personalities/<corpus-instance>/ROLE.md`'s body section to reflect
the answer. Preserve the leading `<!-- all-might generated -->`
marker and the `# Corpus Keeper` heading; you're editing the prose
that follows. Make the role-specific (e.g. "You manage the EDA
flow's standard cells and PLL design knowledge") rather than generic.

### 3. Customize the memory role

Ask:

> **"What kind of assistant do you want to build?"**

Rewrite `personalities/<memory-instance>/ROLE.md` similarly.
Keep the marker and the `# Memory Keeper` heading; replace the
body's introductory paragraph with what the user described.

### 4. Classify and register the folders

For each entry in `onboard.yaml`'s `folders` list:

1. **Classify** as `corpus` or `memory`:
   - **corpus** — source code, design files, anything the agent should
     search by meaning (e.g. `src/`, `rtl/`, `tests/`).
   - **memory** — notes, docs, reference material the agent should
     *know about* but not index (e.g. `docs/`, `notes/`, `decisions/`).
   When unsure, prefer `corpus` — the user can always reclassify later.
2. **Show the classification** to the user in one line per folder and
   ask for overrides:
   ```
   Classified:
     src/    → corpus  (source code, ingest with /ingest)
     docs/   → memory  (reference; recorded in MEMORY.md)
   Override any? (e.g. "docs/ as corpus" or just "ok")
   ```
3. **Register every classified folder in `MEMORY.md`** under a
   "Project Map" table. Read the existing project map and append rows;
   don't duplicate. Format:
   ```markdown
   ## Project Map

   | Path | Kind | Notes |
   |------|------|-------|
   | src/ | corpus | source code |
   | docs/ | memory | reference material |
   ```
   Don't create knowledge_graph workspace stubs yet — the user runs
   `/ingest` later for that, and the corpus keeper's commands tell the
   agent how.

### 5. Re-stitch the root AGENTS.md

After editing the ROLE.md files, the root `AGENTS.md` is stale
(composed from ROLE.md content at init time). Re-compose it:

```bash
python -c "from pathlib import Path; \\
from allmight.core.personalities import compose_agents_md, \\
    Personality, read_registry, discover; \\
root = Path('.').resolve(); \\
templates = {t.name: t for t in discover()}; \\
instances = [Personality(template=templates[r.template], project_root=root, name=r.instance) \\
             for r in read_registry(root)]; \\
compose_agents_md(root, instances)"
```

(That snippet is the closest thing to a CLI today; future versions
may surface a `allmight compose` subcommand.)

### 6. Mark onboarding complete

Edit `.allmight/onboard.yaml` and flip the flag:

```yaml
onboarded: true
```

Don't touch the rest of the file — it remains the record of what was
captured at init time. The next session will see `onboarded: true`
and skip the procedure unless the user explicitly asks to re-onboard.

### 7. Tell the user what changed

One short summary:

> Onboarded. Customized:
> - corpus role: "<one-line summary>"
> - memory role: "<one-line summary>"
> - registered N folders (<corpus count> as corpus, <memory count> as memory)
>
> Next: try `/search "<query>"` to explore — or `/ingest` first if you
> want to build the index over the corpus folders.

## Important

- **Never overwrite the markers** at the top of each ROLE.md
  (`<!-- all-might generated -->`). They mark the file as All-Might-
  owned for re-init's overwrite guard.
- **MEMORY.md is agent-authored from here on.** Don't replace its
  existing sections; append to the project map table.
- If `onboard.yaml` is missing entirely, the project wasn't initialized
  by the new interactive flow. Tell the user to run `allmight init`
  first.
"""

ONBOARD_COMMAND_BODY = """\
Finish All-Might setup by capturing your intent for each personality.

Run this once after `allmight init` (or any time you want to
re-classify a folder or rewrite a role description).

## What happens

1. Reads `.allmight/onboard.yaml` (created by `allmight init`).
2. Asks two open-ended questions:
   - "What knowledge do you want to manage?" — shapes the corpus
     keeper's role description.
   - "What kind of assistant do you want to build?" — shapes the
     memory keeper's role description.
3. Classifies each folder you listed during init as `corpus` or
   `memory`, registers them in MEMORY.md's project map, and shows you
   the classification for confirmation.
4. Re-stitches the root `AGENTS.md` from the updated ROLE.md files.
5. Marks `onboarded: true` in `.allmight/onboard.yaml`.

## How to execute

Load the `onboard` skill and follow its procedure. The skill body
covers each step (read state, customize ROLE.md files, classify
folders, re-compose, mark complete) and what to ask the user.

## When NOT to run

- The project was migrated from an older All-Might layout — onboarding
  data isn't there. Use `/sync` or `allmight migrate` instead.
- You're partway through a session that's already onboarded — the
  skill is idempotent but will ask the user what to redo.
"""
