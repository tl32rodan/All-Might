"""Bundled /onboard skill and command content (Part-D rewrite).

Installed by the ``database`` capability on every init. The skill
walks the agent through the qualitative half of bootstrap that
``allmight init`` deferred:

* Capture each personality's role description in
  ``personalities/<name>/ROLE.md``.
* Build (or update) the project-map table in ``MEMORY.md``.
* Add the leading ``> **Default personality**: <name>`` callout when
  there is more than one personality, so plugins and command bodies
  can route by context.

Why ``database`` owns it: ``/onboard`` is a cross-capability skill,
but it has to live in *one* template. ``database`` is the lead
capability during bootstrap so it's the natural home.
"""

ONBOARD_SKILL_BODY = """\
# Onboard — finish All-Might setup inside the agent

> Run this skill after `allmight init` to capture each personality's
> role in `ROLE.md`, populate `MEMORY.md`'s project map, and add the
> default-personality routing hint.

## When to use

- Right after `allmight init` (the CLI prints "Run /onboard to finish
  setup"). The marker file `.allmight/onboard.yaml` exists and has
  `onboarded: false`.
- The user explicitly asks to re-onboard (edit a role description,
  change the default). `.allmight/onboard.yaml` exists with
  `onboarded: true`; ask the user what specifically to change before
  re-running the full procedure.

## Procedure

### 1. Read the captured state

```bash
cat .allmight/onboard.yaml
```

You'll see something like:

```yaml
onboarded: false
personalities:
  - name: my-chip
    capabilities: [database, memory]
folders: []
```

Each personality block has a `name` and a list of `capabilities` it
was installed with. There may be one personality (the default after
`allmight init --yes`) or several (if the user followed up with
`allmight add ...`).

### 2. Customize each personality's ROLE.md

For every personality entry, ask the user one open-ended question:

> **"Tell me about the `<name>` role. What does it cover, and how
> should I act when answering questions in this role?"**

Take the answer and rewrite `personalities/<name>/ROLE.md`. The file
**must** keep the leading `<!-- all-might generated -->` marker so
re-init's overwrite guard recognises the file as ours.

A good ROLE.md skeleton:

```markdown
<!-- all-might generated -->
# <Name>

You are <one-sentence role from user>.

### Scope

<2-3 bullets describing what the role covers, in the user's words>

### Capabilities

| Command | What it does |
|---------|-------------|
| `/search <query>` | Search this personality's database/ workspaces |
| `/remember` | Persist findings into this personality's memory/ |
| `/recall <query>` | Retrieve past findings from this personality |

(Only list commands that match the personality's installed
capabilities — see the `capabilities:` field in `onboard.yaml`.)

### Getting Started

1. <first-step from user's answer>
2. <second-step>
```

### 3. Update MEMORY.md's project map

Read `MEMORY.md` at the project root. Find the `## Project Map`
section (create it if absent — the section is one heading + a
markdown table). For each personality, ensure there is a row:

```markdown
## Project Map

| Personality | Capabilities | Scope |
|-------------|--------------|-------|
| my-chip     | database, memory | Standard-cell library design and verification |
```

Update existing rows in place; append new ones at the end of the
table. Don't disturb other sections of `MEMORY.md` — the user may
already have prefs/goals captured.

### 4. Add the default-personality routing hint

If `onboard.yaml` lists more than one personality, ask the user:

> **"Which personality should I default to when the conversation isn't
> clearly about a specific one?"**

Insert (or update) a leading blockquote at the very top of
`MEMORY.md`, above the project map:

```markdown
> **Default personality**: <chosen-name>
```

If there is only one personality, skip the question — the lone
personality is the implicit default; you may still write the callout
for clarity.

The exact format matters: command bodies and agent-routing logic
parse this line. Use `> **Default personality**: <name>` verbatim
(blockquote, bold label, single space, name).

### 5. Mark onboarding complete

Edit `.allmight/onboard.yaml`:

```yaml
onboarded: true
```

Don't touch the rest of the file — it remains the record of what was
captured at init time. The next session will see `onboarded: true`
and skip the procedure unless the user explicitly asks to re-onboard.

### 6. Tell the user what changed

One short summary:

> Onboarded. Wrote ROLE.md for: <name1>, <name2>, ...
> Default personality: <chosen-name>.
> Try `/search "<query>"` to explore — or `/ingest` first if you want to
> build the index.

## Important

- **Never overwrite the markers** at the top of each ROLE.md
  (`<!-- all-might generated -->`). They mark the file as All-Might-
  owned for re-init's overwrite guard.
- **MEMORY.md is agent-authored from here on.** Update sections in
  place; never replace the file from a template.
- If `onboard.yaml` is missing entirely, the project wasn't initialized
  by the new flow. Tell the user to run `allmight init` first.
- Folder classification is **not** part of /onboard anymore. The
  agent learns the project structure from `MEMORY.md`'s project map
  and from running `/search` against the database/ workspaces.
"""

ONBOARD_COMMAND_BODY = """\
Finish All-Might setup by capturing each personality's role.

Run once after `allmight init` (or any time you want to rewrite a
role description or change the default personality).

## What happens

1. Reads `.allmight/onboard.yaml` (written by `allmight init`).
2. For each personality, asks the user a single open-ended question
   about the role and rewrites `personalities/<name>/ROLE.md`.
3. Updates `MEMORY.md`'s project map with one row per personality.
4. Adds (or updates) the leading
   `> **Default personality**: <name>` callout in `MEMORY.md` so
   plugins and command bodies can route by context.
5. Marks `onboarded: true` in `.allmight/onboard.yaml`.

## How to execute

Load the `onboard` skill and follow its procedure. The skill body
covers each step (read state, customize ROLE.md files, update the
project map, add the default-personality hint, mark complete) and
what to ask the user.

## When NOT to run

- You're partway through a session that's already onboarded — the
  skill is idempotent but will ask what to redo.
- The project has no `.allmight/onboard.yaml` — run `allmight init`
  first to create one.
"""
