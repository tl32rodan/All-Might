Convert session episodes into lasting semantic facts.

## When to run

- After several productive sessions
- When you notice recurring patterns across episodes
- Periodically (weekly recommended)
- When the user asks to consolidate knowledge

## How to execute

1. List all episode files in `memory/episodes/` that have
   `consolidated: false`.
2. Extract recurring observations and decisions across episodes.
3. For each extracted pattern, search existing facts in
   `memory/semantic/` for overlap (Jaccard similarity >= 0.5).
4. Based on the match:
   - **No match**: create a new fact file in `memory/semantic/`:
     ```yaml
     # memory/semantic/fact_<random_12hex>.fact.yaml
     id: fact_<random_12hex>
     content: "The extracted pattern or knowledge"
     category: "domain_knowledge"  # or: user_preference, convention,
                                   #     correction, architecture_decision
     confidence: 1.0
     created_at: <ISO timestamp>
     updated_at: <ISO timestamp>
     last_accessed: <ISO timestamp>
     access_count: 0
     importance: 0.5
     source_episodes:
       - ep_<source_episode_id>
     supersedes: null
     namespace: default
     ```
   - **Match, consistent**: bump the existing fact's `confidence`
     (min +0.1, max 1.0) and add the source episode to its list
   - **Match, contradictory** (new info negates old): create a new fact
     with `supersedes: <old_fact_id>`, reduce old fact's confidence to 30%
5. Mark processed episodes as `consolidated: true`.
6. Report: facts created, updated, superseded, conflicts detected.

## What to expect

- New `.fact.yaml` files in `memory/semantic/`
- Updated confidence scores on existing facts
- Supersession chains for corrected knowledge
- Episodes marked as consolidated (won't be reprocessed)

## Working memory

If consolidation produces high-importance facts relevant to the user
model or environment, also update `memory/working/MEMORY.md` sections
(`user_model`, `environment`, `active_goals`, `pinned_memories`).
