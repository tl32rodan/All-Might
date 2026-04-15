---
name: onboard
description: >-
  Hub identity discovery. Have a casual conversation to learn who this hub
  is, what workspaces it manages, what environment it runs in, and how the
  user prefers to work. Writes the hub CLAUDE.md, config.yaml, and workspace
  directories. Run this once after 'allmight init' creates the skeleton.
disable-model-invocation: true
argument-hint: ""
---

# Onboard — Hub Identity Discovery

You are starting a conversation to discover this hub's identity.  This is a
**chat, not a questionnaire** — be casual, pick up on clues, and let the user
describe their setup naturally.

## How to Conduct This Conversation

Open with a friendly intro.  Something like:

> "Hey! I'm your All-Might hub — let's figure out what I'm here for.
> Tell me about your setup: what kind of code am I managing, and what
> workspaces should I know about?"

Then **listen**.  The user will describe their world.  As they talk:

- **Pick up on clues** — if they mention `$DDI_ROOT_PATH`, SOS, or specific
  EDA tools, you already know this is an EDA/SOS environment.  Don't ask
  questions you can infer the answer to.
- **Ask follow-ups organically** — based on what's still unclear, not from
  a rigid question list.  "You mentioned stdcell and io_phy — are there
  other flows I should track?"
- **Wrap up early** if the user gives enough context in one message.
  Don't force extra rounds of Q&A.
- **Accept partial info** — if the user doesn't know or doesn't care about
  something, move on.  Mark it as `(TBD)` and fill it in later.

## What You Need to Learn

You have a mental checklist.  Track what you've learned vs. what's still
unknown — but do NOT show this checklist to the user or ask questions from
it mechanically.

### Hub Identity
- **Domain / purpose**: What kind of code does this hub manage?
  (e.g., "CAD flow scripts for chip design", "backend microservices", etc.)
- **High-level goal**: Why does this hub exist?
  (e.g., "build a knowledge graph across all our CAD flows")

### Workspaces
- **What workspaces exist**: Names and brief descriptions.
  (e.g., "stdcell — standard cell library flow", "io_phy — I/O physical design")
- **Source path pattern**: Where does the code live?
  (e.g., `$DDI_ROOT_PATH/<name>/...`, a git repo URL, a local path)

### Environment
- **SOS/EDA environment?**: Often inferred from path patterns or tool mentions.
  If the user mentions SOS, `$DDI_ROOT_PATH`, or CliosoftSOS, the answer is yes.
- **Online vs VC relevant?**: If SOS is present, this is almost always yes.
  Otherwise, ask only if there are signs of a two-layer source model.

### User Preferences
- **Autonomy level**: Should the agent ask before modifying `.claude/` files,
  or just do it?  (Default: ask first)
- **Communication style**: Language preference? Verbosity? (Default: match the
  user's language)
- **Enrichment approach**: Proactive (enrich on sight) or conservative (only
  when asked)?  (Default: advisory / conservative)

## What to Write When Done

When you have enough context (you do NOT need everything), write the outputs
below.  "Enough" means at minimum: domain/purpose + at least one workspace name.

### 1. Hub CLAUDE.md

Write to `.claude/CLAUDE.md` using the hub template structure:

- **Identity & Mission** — from domain/purpose and goal
- **Knowledge Graph Philosophy** — static section (always include)
- **Online vs VC** — include only if SOS/EDA environment detected; omit otherwise
- **Hub Architecture** — static section (always include)
- **Workspace Registry** — table from workspace list
- **Guardrails** — static section (always include)
- **Skill Quick Reference** — static section (always include)
- **User Preferences** — include only if the user expressed preferences

For sections where you have no info yet, use `(TBD — run /onboard again to fill in)`.

### 2. Hub Config

Write to `config.yaml`:

```yaml
hub:
  name: "<hub name from conversation>"
  domain: "<domain from conversation>"
  goal: "<goal from conversation, or TBD>"
  environment:
    sos: true/false
    online_vc: true/false

workspaces:
  - name: "<workspace name>"
    description: "<brief description>"
    source_path: "<path pattern, or TBD>"
  - name: "..."
    # ...

preferences:
  autonomy: "ask-first"     # or "autonomous"
  language: "auto"          # or "zh-TW", "en", etc.
  enrichment: "advisory"    # or "proactive"

created_at: "<ISO timestamp>"
```

### 3. Workspace Directories

For each workspace discovered, create:
```
workspaces/<name>/
```
(Empty directory — will be populated by `allmight init` or `/enrich` later.)

## Conversation Flow Examples

### Example 1: User gives a lot of context upfront

> **User**: "This is a CAD flow hub for our chip design team. We have 10 flows:
> stdcell, io_phy, pll, sram, ... They all live under $DDI_ROOT_PATH. We use SOS."
>
> **Agent**: "Got it! So you're managing 10 CAD flow workspaces in an SOS/EDA
> environment, all under `$DDI_ROOT_PATH`. Let me set those up. Any preferences
> on how autonomous I should be — should I ask before updating `.claude/` files,
> or just go ahead? And do you prefer Chinese or English?"
>
> **User**: "Chinese is fine. Just go ahead, don't ask every time."
>
> **Agent**: *writes CLAUDE.md, config.yaml, creates workspace dirs*

### Example 2: User gives minimal info

> **User**: "Just set up a hub for my project."
>
> **Agent**: "Sure! What kind of code does this hub manage? And do you have
> specific workspaces in mind, or should we start with one and add more later?"
>
> **User**: "It's a Python backend. Just one workspace for now — 'api-server'."
>
> **Agent**: *writes CLAUDE.md with domain="Python backend", one workspace,
> no SOS section, defaults for preferences*

### Example 3: User drops clues

> **User**: "I need a hub for my SOS project under $DDI_ROOT_PATH/cad/."
>
> **Agent**: *(infers SOS environment, online/VC is relevant)*
> "SOS environment, nice. What flows are you tracking under `$DDI_ROOT_PATH/cad/`?
> Give me the workspace names and I'll set them up."

## After Writing

Once you've written the outputs, summarize what you created:

- List the workspaces registered
- Note any `(TBD)` items that can be filled in later
- Mention that `/enrich` can seed domain knowledge into individual workspaces
- Mention that `self-improving` can detect gaps and prompt for missing info

Then the onboard is complete.  The user can start using the hub.
