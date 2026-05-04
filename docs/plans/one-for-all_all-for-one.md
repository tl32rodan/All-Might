# Plan: `/one-for-all` and `/all-for-one`

Renames `/export` to `/one-for-all` and replaces `allmight import`'s
agent-facing surface with a richer `/all-for-one` skill that can
**merge N source personalities (bundles or in-project) into 1 target
(new or existing)**. Backward compatibility is intentionally not a
goal — Part-D / Part-E rows and existing bundles will be migrated, not
preserved under their old names.

## Naming rationale

Themed after the All-Might (Boku no Hero Academia) quirks. The
asymmetry is deliberate:

| Skill | Cardinality | What the quirk does |
|---|---|---|
| `/one-for-all` | **1 → 1** | Pass one personality outward as a single bundle (the heroic transfer) |
| `/all-for-one` | **N → 1** | Absorb multiple sources into one personality (the villain's accumulation) |

## Confirmed design decisions (from the discussion)

1. **Sources for `/all-for-one`** can be either an external bundle (a
   `/one-for-all` output dir) or an **in-project personality** by
   name. This lets `/all-for-one` double as a refactoring tool:
   "merge `stdcell_owner` and `pll_owner` into `eda_owner`" needs no
   bundle.
2. **`database` capability stays coupled to SMAK.** No abstraction
   layer. The merge primitive operates at the
   `database/<workspace>/config.yaml` level only; `store/` is
   throwaway derived data and is rebuilt by `/ingest` after the
   merge. Agent does not need SMAK-internal fluency to merge.
3. **In-project sources are kept by default**, with a yes/no prompt
   asking whether to remove them after merge succeeds. (`git merge
   --squash` style: keep both unless user opts in.)
4. **`/one-for-all` stays 1→1.** No batched "export N personalities
   into one bundle" mode. Asymmetry with `/all-for-one` is the point.

## Architecture changes

### CLI ↔ skill split (corrected from previous plan)

| Operation | Surface | Why |
|---|---|---|
| Single-bundle install, no merge, target name available | `allmight import <bundle>` (CLI) | CI / scripting / fresh-project bootstrap |
| Anything involving merge (multi-source, target-collision, in-project consolidation) | `/all-for-one` (skill) | Needs agent dialog: name conflicts, file-level merge decisions, ROLE.md prose reconciliation |

`allmight import` no longer has a `--force` overwrite path. If the
target name already exists, it fails with:

> `error: personality '<name>' already exists. To merge into it, run /all-for-one in the agent.`

This redirects merge-shaped problems to the surface that can dialog.

### Per-capability merge rules (spec for `/all-for-one` skill body)

| Capability | Asset | Merge action |
|---|---|---|
| `database` | `<ws>/config.yaml` (per workspace) | Same workspace name in two sources → dialog (rename / pick / merge corpora list). Different name → union directory layout. |
| `database` | `<ws>/store/` | **Never bundled, never merged.** Skill ends with: "Run `/ingest` in the merged workspaces to rebuild SMAK indices." |
| `memory` | `understanding/<topic>.md` | File-level conflict → per-file dialog: concat / pick-one / agent-rewrite. Understanding is prose; no mechanical merge. |
| `memory` | `journal/<scope>/*` | Append-only by nature. Concat all sources, sort by timestamp, dedupe identical entries. |
| `memory` | `store/` | Never bundled. Rebuilt by next `/remember` cycle. |
| any | `ROLE.md` | Pure prose. Agent reads all source ROLE.md files, drafts a merged version reconciling responsibilities/scope, asks user to confirm before writing. Most expensive merge step. |

### Registry schema change (`.allmight/personalities.yaml`)

Replace single-source lineage:

```yaml
- name: stdcell_v2
  capabilities: [database, memory]
  versions: {database: 1.0.0, memory: 1.0.0}
  imported_from_bundle_id: <uuid>      # OLD — single source only
  bundle_version: 0.1.0
  imported_at: 2026-01-...
```

with multi-source lineage:

```yaml
- name: eda_owner
  capabilities: [database, memory]
  versions: {database: 1.0.0, memory: 1.0.0}
  derived_from:                        # NEW — list of source descriptors
    - kind: bundle
      bundle_id: <uuid>
      bundle_version: 0.1.0
    - kind: personality                 # in-project source
      name: stdcell_owner
  derived_at: 2026-05-...
```

`derived_from` is a list of dicts. Each entry has `kind: bundle` or
`kind: personality`. Bundle entries carry `bundle_id` +
`bundle_version`; personality entries carry the source `name`.

For single-bundle imports via `allmight import`, the list has exactly
one `kind: bundle` entry — the same lineage information the old
flat fields carried, just under the new schema.

`RegistryEntry` dataclass loses the three flat fields
(`imported_from_bundle_id`, `bundle_version`, `imported_at`) and
gains:

```python
@dataclass
class DerivedFrom:
    kind: str                    # "bundle" | "personality"
    bundle_id: str = ""          # only when kind == "bundle"
    bundle_version: str = ""
    name: str = ""               # only when kind == "personality"

derived_from: list[DerivedFrom] = field(default_factory=list)
derived_at: str = ""
```

## Files touched

### Renames (file-level)

- `src/allmight/capabilities/database/export_skill_content.py`
  → `one_for_all_skill_content.py`
  - `EXPORT_SKILL_BODY` → `ONE_FOR_ALL_SKILL_BODY`
  - `EXPORT_COMMAND_BODY` → `ONE_FOR_ALL_COMMAND_BODY`
  - Body text replaces "Export" / "/export" / "export skill" with
    "One For All" / "/one-for-all" / "one-for-all skill"
  - Lineage section updates: write `derived_from: [{kind: bundle, ...}]`
    instead of flat fields; rename "Export" headings to "One For All"

### New files

- `src/allmight/capabilities/database/all_for_one_skill_content.py`
  - `ALL_FOR_ONE_SKILL_BODY` — full skill prose covering source
    discovery, per-capability merge rules, ROLE.md drafting, registry
    update
  - `ALL_FOR_ONE_COMMAND_BODY` — short command stub

### Edits

- `src/allmight/capabilities/database/initializer.py`
  - `_install_export_skill` → `_install_one_for_all_skill` (writes
    `.opencode/skills/one-for-all/SKILL.md` and
    `.opencode/commands/one-for-all.md`)
  - Add `_install_all_for_one_skill` (writes corresponding files for
    AFO)
  - Both are called from the first-init branch; `_install_export_skill`
    call site is replaced

- `src/allmight/cli.py`
  - `import_personality` (the `import` command body):
    - Remove `--force` flag
    - Fail with redirect message when target exists
    - Switch lineage write from
      `imported_from_bundle_id=...` to
      `derived_from=[DerivedFrom(kind="bundle", ...)]`
  - Help text reflects the narrowed scope

- `src/allmight/core/personalities.py`
  - `RegistryEntry`: add `DerivedFrom`, `derived_from`, `derived_at`;
    remove `imported_from_bundle_id`, `bundle_version`, `imported_at`
  - `read_registry`: parse new `derived_from` list shape; drop the
    flat-field branch
  - `_entry_to_row`: emit `derived_from` list

- `CLAUDE.md` (project root)
  - "Cross-project moves go through `/export` and `allmight import`"
    paragraph → updated to reflect `/one-for-all`, `/all-for-one`,
    and the narrowed `allmight import`
  - "Key Files to Know" table: `export_skill_content.py` →
    `one_for_all_skill_content.py`; add `all_for_one_skill_content.py`
  - Remove the dead `one_for_all/` row that points at a directory
    that doesn't exist (separate cleanup, but in scope)

- `src/allmight/share/git_share.py`
  - References to `/export` in docstrings/comments → `/one-for-all`
  - No behavioural change (publish/pull operates on bundle dirs;
    bundle layout doesn't change)

### Tests

- Rename `tests/test_export_import.py` → `tests/test_one_for_all_all_for_one.py`
  - Update all `EXPORT_SKILL_BODY` / `EXPORT_COMMAND_BODY` imports
  - Update `["import", ...]` invocations: keep the happy-path single-bundle
    test; add tests for the new "target exists → redirect to /all-for-one"
    error path; remove tests of the removed `--force` flag
  - Add tests for `ONE_FOR_ALL_SKILL_BODY` content (PII review,
    manifest format, `derived_from: [...]` shape)
  - Add tests for `ALL_FOR_ONE_SKILL_BODY` content (source discovery,
    per-capability merge rules, ROLE.md drafting, registry shape)

- `tests/test_skill_content.py`: any `/export` references → `/one-for-all`

- `tests/test_command_body_generic.py`: ensure the new
  `one-for-all.md` and `all-for-one.md` command bodies pass the
  generic-body invariant (no literal personality names).

- `tests/test_share.py`: any docstring/error references; no behavioural
  change expected.

- `tests/test_registry_dual_shape.py`: needs an audit — the dual-shape
  Part-C / Part-D logic stays, but the lineage-field shape changes.

## Out of scope for this commit

- The merge **engine** (the actual Python that performs in-project
  multi-source merge) — `/all-for-one` is a **skill**, so the agent
  walks the procedure using existing `Path` / file-copy primitives
  plus `smak` CLI calls. No new merge helper module is added in this
  commit. If a future commit wants a `merge_personalities()` helper,
  it can be added behind the skill, but is not required for the skill
  to function.
- The in-project personality removal flow (the "yes/no, remove
  sources?" prompt) is documented in the skill body; no CLI command
  is added to remove personalities programmatically.

## Test plan

After all edits:

1. `PYTHONPATH=src python -m pytest tests/` — full suite must pass.
2. The renamed test file (`test_one_for_all_all_for_one.py`) covers:
   happy-path import, target-exists rejection, lineage shape on
   import, skill body content for both OFA and AFO.
3. No generated TypeScript was touched (no plugin changes), so
   `tsc --noEmit --skipLibCheck` is not required.
4. Sanity: `cd /tmp/demo && allmight init . && ls .opencode/commands/`
   shows `one-for-all.md` and `all-for-one.md` present, `export.md`
   and `import.md` (slash-command) absent.
