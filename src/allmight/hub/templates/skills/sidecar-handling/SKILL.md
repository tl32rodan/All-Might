---
name: sidecar-handling
description: >-
  SOS-based sidecar update SOP. The complete standard operating procedure
  for updating sidecar enrichment files through CliosoftSOS — three-layer
  model, schema reference, step-by-step workflow, and strict rules. Use
  when you need to modify sidecar YAML files in any workspace.
disable-model-invocation: true
---

# Sidecar Handling — SOS-Based Update SOP

The complete standard operating procedure for updating sidecar enrichment files
in an SOS environment.  This is a **global SOP** — it applies to any workspace
managed by this hub.

## Three-Layer Model

Sidecar files (`.{filename}.sidecar.yaml`) store per-symbol metadata (intent,
relations) beside source files.  In an SOS environment, three layers exist:

```
Layer 1: Online ($DDI_ROOT_PATH)    <- Live source + sidecars (corpus indexes THIS)
Layer 2: VC release (e.g. rel1.0)   <- Frozen snapshot (immutable)
Layer 3: SOS workspace (/users/you/ws_xxx/)  <- Personal checkout (read-write)
```

| Layer | Source | Sidecars | Mutable? | Indexed? |
|-------|--------|----------|----------|---------------|
| Online | Latest | Latest | Yes (after check-in) | **Yes** |
| VC release | Frozen | Frozen | No | No (uses online data) |
| SOS workspace | Checked-out copy | Editable | Yes | No (personal) |

## Sidecar File Schema

Each sidecar file follows this schema:

```yaml
# .example_module.py.sidecar.yaml
symbols:
  - name: ClassName
    intent: "Brief description of the symbol's purpose"
    relations:
      - $DDI_ROOT_PATH/other/file.py::OtherSymbol
      - $DDI_ROOT_PATH/lib/base.py::BaseClass
  - name: ClassName.method_name
    intent: "What this method does and why"
    relations:
      - $DDI_ROOT_PATH/other/file.py::OtherSymbol.helper
```

### UID Format

```
$DDI_ROOT_PATH/relative/path/to/file.py::SymbolName
$DDI_ROOT_PATH/relative/path/to/file.py::ClassName.method_name
$DDI_ROOT_PATH/relative/path/to/file.py::*          (whole file)
```

### Common Mistakes to Avoid

| Mistake | Why it breaks | Correct form |
|---------|--------------|--------------|
| Absolute path in relation | Won't resolve across environments | `$DDI_ROOT_PATH/rtl/mod.v::sym` |
| Invented symbol name | Won't link to indexed symbol | Use `/search` to find real UIDs |
| Wrong nesting level | Schema violation | `symbols[].name`, not `symbols[].symbols` |
| Missing `$DDI_ROOT_PATH` prefix | Path won't expand correctly | Always prefix with `$DDI_ROOT_PATH` |

## SOP: Updating Sidecars

### Prerequisites

- `$DDI_ROOT_PATH` is set and points to online
- An SOS workspace exists (or you will create one)
- The target workspace's corpora are ingested

### Step 1: Identify What to Enrich

Use `detroit-smak` to search the target workspace:

```
/search "the concept or symbol you want to enrich" --index <index_name>
```

Note the file path and symbol name from the search results.

### Step 2: Check Existing Sidecar

Before enriching, check if a sidecar already exists:

```
/explain <file_path>::<symbol_name>
```

This shows existing intent, relations, and graph context.  Build on it —
don't duplicate.

### Step 3: Enrich via All-Might Command

Use the `/enrich` command — **never** edit sidecar YAML by hand:

```
/enrich --file <relative_path> --symbol <symbol_name> \
  --intent "Description of what this symbol does and why" \
  --relation "$DDI_ROOT_PATH/other/file.py::RelatedSymbol"
```

The `/enrich` command handles:
- Correct YAML schema and nesting
- Proper UID format with `$DDI_ROOT_PATH` prefix
- Creating the sidecar file if it doesn't exist
- Appending to existing sidecar if it does

### Step 4: SOS Check-In

After enriching, commit the sidecar to the canonical path:

```bash
sos check-in <sidecar_file>
```

After check-in:
- The sidecar is committed to Layer 1 (online) or Layer 2 (VC)
- It becomes available for `/ingest` and team-wide search
- Path mismatch warnings (if any) are resolved

### Step 5: Verify

1. **Re-ingest** the affected index:
   ```
   /ingest
   ```

2. **Search** to confirm the enrichment is indexed:
   ```
   /search "the enriched concept"
   ```

3. **Explain** to see the updated sidecar:
   ```
   /explain <file_path>::<symbol_name>
   ```

## Path Mismatch Warnings

When editing sidecars in an SOS workspace (Layer 3), All-Might may emit path mismatch
warnings.  **This is normal** — it means you're editing at a workspace path while
relations point to the canonical `$DDI_ROOT_PATH`.  After `sos check-in`,
everything aligns.

Do NOT:
- Suppress or work around path mismatch warnings
- Change relation paths to match your workspace path
- Create separate indices for workspace paths

## Strict Rules

1. **NEVER** edit `.sidecar.yaml` files by hand — not in online, not in VC, not
   in a workspace.  Always use `/enrich`.
2. **NEVER** hardcode absolute paths in relations.  Always use `$DDI_ROOT_PATH/...`.
3. **ALWAYS** set `$DDI_ROOT_PATH` before running All-Might commands.
4. **ALWAYS** `sos check-in` after enrichment to make sidecars available team-wide.
5. **ALWAYS** re-ingest after enrichment to update search indices.

## Interaction with Other Skills

| Skill | Relationship |
|-------|-------------|
| `detroit-smak` | Use it to search before enriching (Step 1) |
| `enrich` | `.claude/` enrichment teaches patterns; sidecar enrichment annotates symbols. Different layers, complementary |
| `self-improving` | After a batch of sidecar enrichment, self-improving can assess coverage improvements |
