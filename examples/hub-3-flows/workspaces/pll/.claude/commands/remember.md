Record an observation worth persisting beyond this session.

## What to remember

- **User corrections**: "User clarified that X means Y"
- **Discovered patterns**: "All handlers follow middleware pattern Z"
- **Important decisions**: "Chose Redis over Memcached for pub/sub"
- **User preferences**: "User prefers concise answers"
- **Environment facts**: "Build requires Node 18+"

## How to execute

1. Write the observation as a YAML episode file in `memory/episodes/YYYY/MM/`:

```yaml
# memory/episodes/2026/04/sess_<session_id>.episode.yaml
id: ep_<random_12hex>
session_id: <current_session_id>
started_at: <ISO timestamp>
ended_at: <ISO timestamp>
summary: "Brief session summary"
observations:
  - "The observation you want to remember"
key_decisions: []
files_touched: []
topics: []
outcome: ""
importance: 0.5
consolidated: false
```

2. Or append to an existing episode file for this session if one exists.

## What to expect

- The observation is stored as part of the session episode
- It will surface when `/recall` searches for related queries
- During `/consolidate`, recurring observations become lasting facts
- Observations are append-only — never modify past episodes

## When NOT to remember

- Trivial observations the agent can re-derive from code
- Information already captured in sidecar enrichment
- Temporary debug notes
