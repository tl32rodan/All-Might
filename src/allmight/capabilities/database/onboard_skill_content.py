"""Bundled /onboard skill and command content (Track A).

The /onboard skill is the personality-decision phase of bootstrap.
``allmight init`` is scaffold-only — no personality is created at
install time. This skill:

* Reads ``.allmight/onboard.yaml`` (``onboarded: false``).
* Asks the user a single question about their purpose.
* Matches their words against the suggestion catalog at
  ``.allmight/suggestions/personalities/*.yaml`` (seeded by init).
* For each chosen suggestion, runs ``allmight add <name>
  --capabilities <list>`` so the marker / capability table /
  registry entry are written by deterministic Python — never by the
  agent free-form.
* Updates ``MEMORY.md``'s Project Map and the
  ``> **Default personality**: <name>`` callout.
* Flips ``onboarded: true``.

The previous (Part-D) skill body was 154 lines and asked the agent
to free-form ROLE.md and infer a capability table. Track A moves
that work into ``allmight add`` and the suggestion YAMLs so weaker
models (Kimi K2.5, Minimax-M2.5) execute the skill cleanly.

Why ``database`` owns it: ``/onboard`` is a cross-capability skill,
but it has to live in *one* template. ``database`` is the lead
capability during bootstrap so it's the natural home.
"""

ONBOARD_SKILL_BODY = """\
# Onboard — create personalities

Run after `allmight init` to create the project's personalities.
State: `.allmight/onboard.yaml` has `onboarded: false, personalities: []`.

## Steps

### 1. Read state
```bash
cat .allmight/onboard.yaml
```
If `onboarded: true`, ask the user what to change before re-running.

### 2. Ask once
> "Do you have a specific purpose for this project, or should I set up
> a general-purpose assistant?"

### 3. Match suggestions
Read the suggestion catalog:
```bash
ls .allmight/suggestions/personalities/
```
Each YAML has `name`, `capabilities`, `scope`, `keywords`. If the
user described a purpose, score each suggestion's `keywords` against
their words and present the top 1-3 candidates. Always include
`general` as the fallback. Let the user pick one or more.

### 4. Create personalities (mechanical — DO NOT free-form)
For each chosen suggestion `<name>`:
```bash
allmight add <name> --capabilities <comma-separated-list-from-yaml>
```
This writes:
- `personalities/<name>/` directory with capability subdirs
- `personalities/<name>/ROLE.md` with the marker + capability table
  (correct by construction — do not edit the marker or table)
- A registry row in `.allmight/personalities.yaml`

### 5. (Optional) Refine ROLE.md scope
If the user gave specific scope words, edit only the `## Scope`
section of `personalities/<name>/ROLE.md` to reflect them. Leave the
marker (`<!-- all-might generated -->`) and capability table alone.

### 6. Update MEMORY.md
- Append one row per created personality to the `## Project Map` table.
- Write `> **Default personality**: <name>` at the very top of
  `MEMORY.md` (above any existing content):
  - 1 personality created → use that name
  - N personalities → ask the user which is the default

The exact format `> **Default personality**: <name>` is parsed by
command bodies — keep it verbatim (blockquote, bold label, single
space, name).

### 7. Mark complete
Edit `.allmight/onboard.yaml` and set `onboarded: true`. Don't touch
the rest of the file.

### 8. Closing message
> Created: <name1>, <name2>. Default: <name>.
> Try `/search "<query>"` or just start asking questions.

## Important
- The capability table inside each ROLE.md is written by
  `allmight add` — never edit it manually. To change a personality's
  command set, edit the suggestion YAML and re-run.
- Suggestions are at `.allmight/suggestions/personalities/`, NOT
  `.allmight/templates/` (which is the `/sync` re-init staging area).
- If `.allmight/onboard.yaml` is missing entirely, the project
  wasn't initialised — tell the user to run `allmight init` first.
"""

ONBOARD_COMMAND_BODY = """\
Create the project's personalities.

Run once after `allmight init`. The init step is scaffold-only — no
personality exists yet. This command asks you about purpose,
proposes from the suggestion catalog at
`.allmight/suggestions/personalities/`, and creates whichever you
pick by shelling out to `allmight add`.

## What happens

1. Reads `.allmight/onboard.yaml` (written by `allmight init`).
2. Asks ONE question about your purpose.
3. Proposes 1-3 suggestions matched against your purpose, plus the
   `general` fallback.
4. For each chosen suggestion, runs
   `allmight add <name> --capabilities <list>` so the marker,
   capability table, and registry entry are correct by construction.
5. Updates `MEMORY.md` with the `## Project Map` rows and the
   `> **Default personality**: <name>` callout.
6. Marks `onboarded: true` in `.allmight/onboard.yaml`.

## How to execute

Load the `onboard` skill and follow its checklist. The skill body
covers each step; the agent should not free-form ROLE.md content.

## When NOT to run

- The project has no `.allmight/onboard.yaml` — run `allmight init`
  first.
- You're partway through a session that's already onboarded — the
  skill will ask what to redo.
"""
