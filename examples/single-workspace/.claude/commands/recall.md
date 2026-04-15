Search past memories across all layers.

## How to execute

1. Search `memory/semantic/` for fact files (`.fact.yaml`) whose content
   matches the query keywords.
2. Search `memory/episodes/` for episode files (`.episode.yaml`) whose
   summary or observations match.
3. Score each result using composite scoring:
   - **Recency** (30%): `e^(-hours_since_access / (168 * ln(1 + access_count)))`
   - **Importance** (30%): the entry's stored importance (0–1)
   - **Relevance** (40%): keyword overlap or semantic similarity
4. Return top results sorted by composite score.
5. For each returned fact, bump its `last_accessed` timestamp and
   `access_count` in the YAML file (this makes it resist future decay).

## What to expect

Results from two sources:
- **Semantic facts** (`memory/semantic/fact_*.fact.yaml`): consolidated,
  high-confidence knowledge with categories and source episodes
- **Episodes** (`memory/episodes/YYYY/MM/*.episode.yaml`): raw session
  records with observations, decisions, and file lists

## When to recall

- Before making assumptions about user preferences
- When facing a problem that seems familiar
- When starting work in an area visited in past sessions
- When the user asks "did we discuss X before?"

## Memory decay

Memories that are never accessed decay over time. The Ebbinghaus
forgetting curve `M(t) = e^(-t/S)` means:
- Frequently accessed memories persist (high S from access_count)
- Never-accessed memories fade after ~2 weeks
- Decayed memories still exist on disk but score too low to surface
