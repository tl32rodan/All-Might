"""Bundled SOS skill content for CliosoftSOS environments.

All-Might ships its own copy of the SOS skill body so there is no
runtime dependency on SMAK skill files being present on disk.
"""

SOS_SKILL_BODY = """\
# CliosoftSOS + SMAK Workflow

## 0. STANDALONE HUB ARCHITECTURE

This All-Might folder is a **standalone workspace hub** — it is NOT inside the source code tree.

```
<this folder>/                        ← All-Might hub (Claude Code project root)
├── workspace_config.yaml             ← Index definitions → point to $DDI_ROOT_PATH/...
├── smak/                             ← FAISS databases (local, built by smak ingest)
├── .claude/skills/                   ← Skills loaded by agent
└── all-might/                        ← Enrichment tracker, panorama exports

$DDI_ROOT_PATH (e.g. /CAD/stdcell)    ← Source code (read-only, SOS online)
/users/you/ws_xxx/                    ← SOS workspace (read-write, personal checkout)
└── .*.sidecar.yaml                   ← Sidecars are created HERE, beside source files
```

**Key rules for agents:**
- Source code and sidecars are **outside this folder** — at SOS-managed paths
- FAISS databases and config are **inside this folder**
- When reading/modifying source or sidecars, navigate to the SOS path — not here
- `workspace_config.yaml` is the bridge between this local hub and remote source paths

## 1. WHAT CLIOSOFT SOS IS

CliosoftSOS is the **version control system** used internally for EDA (Electronic Design Automation) projects. It is NOT git. Key differences:

| Concept | Git | CliosoftSOS |
|---|---|---|
| Repository | `.git/` directory | Centralized SOS server |
| Branch | git branch | "flow release" |
| Main | `main` / `master` | "online" |
| Working copy | `git clone` | SOS workspace (link-based snapshot) |
| Commit | `git commit` + `git push` | `sos check-in` |
| Checkout | `git checkout` | `sos check-out` into workspace |

SOS workspaces are **link snapshots**: the SOS server creates a directory structure made of symlinks pointing to the actual files on a shared disk. When you check out a file, SOS replaces the link with a real writable copy. When you check in, it goes back to the shared location.

## 2. THE THREE-LAYER PATH MODEL

```
Layer 1: Online (latest / main)
  $DDI_ROOT_PATH = /CAD/stdcell
  Access:  READ-ONLY (shared disk, visible to everyone)
  Purpose: The latest codebase — always moving forward, contains all features
  FAISS:   Primary index is built from this layer

Layer 2: Version Control (frozen releases)
  $DDI_ROOT_PATH = /CAD/stdcell_production/{version_string}/  (e.g. 20260301_xxxxxx)
  Access:  READ-ONLY (shared disk, visible to everyone)
  Purpose: A complete snapshot of online at a specific point in time.
           Production uses a VC release to avoid unexpected side effects from online updates.
  FAISS:   Each version can have its own FAISS index

Layer 3: SOS Workspace (personal checkout)
  Path:    /arbitrary/path/created/by/sos/
  Access:  READ-WRITE (the only place you can edit files)
  Purpose: Personal working area for making changes
  Sidecar: Created/edited here, then checked in to Layer 1/2
```

### Key rules

- **Online and version control are read-only.** You cannot edit files there directly.
- **All edits happen in an SOS workspace.** After editing, `sos check-in` pushes changes back.
- **`$DDI_ROOT_PATH` is the abstraction** that points to either online or a specific version.
- **The workspace path is NOT `$DDI_ROOT_PATH`.** Workspace is a temporary working area at an unrelated path.

### Sidecar lifecycle across layers

Sidecars are enriched against **online** (Layer 1) — that's the primary focus.
When a new version control release is cut (e.g. `20260301_xxxxxx`), it is a **complete copy**
of online at that moment, including any sidecars that existed at that time. Over time,
version control releases accumulate their own copy of sidecars.

By setting `$DDI_ROOT_PATH` to online or a specific VC release, you control which layer's
source code and sidecars SMAK reads. Each layer can have its own FAISS index.

## 3. HOW $DDI_ROOT_PATH MAPS TO SMAK

SMAK's `path_env` feature bridges the gap between SOS's multi-path model and SMAK's UID system.

### Config setup

```yaml
# workspace_config.yaml
indices:
  - name: rtl_code
    uri: ./smak/rtl_code
    description: "Verilog/SystemVerilog RTL modules for DDR5 PHY datapath"
    paths:
      - $DDI_ROOT_PATH/rtl/phy
    path_env: DDI_ROOT_PATH

  - name: verification
    uri: ./smak/verification
    description: "UVM testbenches and coverage models for PHY verification"
    paths:
      - $DDI_ROOT_PATH/verif
    path_env: DDI_ROOT_PATH

  - name: constraints
    uri: ./smak/constraints
    description: "SDC timing constraints, floorplan DEF, and power intent UPF"
    paths:
      - $DDI_ROOT_PATH/constraints
    path_env: DDI_ROOT_PATH
```

### UID format in SOS environment

```
$DDI_ROOT_PATH/rtl/phy/dq_serdes.v::dq_serializer

When DDI_ROOT_PATH=/CAD/stdcell, expands to:
/CAD/stdcell/rtl/phy/dq_serdes.v::dq_serializer
```

## 4. WORKFLOW: ENRICH SIDECAR IN A WORKSPACE

You are in an SOS workspace at `/users/john/ws_fix_timing/`. The FAISS index was built from online (`DDI_ROOT_PATH=/CAD/stdcell`).

1. Search: `/search "DQ serializer timing-critical path" --index rtl_code`
2. Find related issue: `/search "timing closure ECO for DQ path" --index release_notes`
3. Annotate: `/enrich --file rtl/phy/dq_serdes.v --symbol dq_serializer --intent "8:1 serializer for DQ lane. Timing-critical." --relation "$DDI_ROOT_PATH/doc/releases/eco_042.md::*"`
4. After `sos check-in`: sidecar is committed to the canonical path (Layer 1 or 2),
   making it available for future `smak ingest` and team-wide search

## 5. PATH MISMATCH WARNING

When editing sidecars in a workspace, SMAK may emit path mismatch warnings. **This is normal** — it means you're editing in a workspace (Layer 3) while relations correctly point to the canonical path (Layer 1/2). After `sos check-in`, everything aligns.

## 6. WHICH LAYER TO TARGET

| Task | Target Layer | $DDI_ROOT_PATH |
|---|---|---|
| Build FAISS for latest code | Online (Layer 1) | `/CAD/stdcell` |
| Build FAISS for a frozen release | Version Control (Layer 2) | `/CAD/stdcell_production/{version}/` |
| Edit sidecars | Workspace (Layer 3) | Set to the target layer (1 or 2) |
| Search/query | Any (reads FAISS) | Set to match the FAISS you want to query |

## 7. STRICT RULES FOR SOS ENVIRONMENTS

1. **Never hardcode absolute paths in relations.** Always use `$DDI_ROOT_PATH/...` format.
2. **Never edit sidecar files by hand** — not in online, not in version control, not even in a workspace. Always use `/enrich` from All-Might.
3. **Always set `path_env: DDI_ROOT_PATH`** in config for indices on the shared disk.
4. **Set `$DDI_ROOT_PATH` before running SMAK** — it determines which layer you're operating on.
5. **Path mismatch warnings in workspaces are normal.** Don't suppress or work around them.
6. **Re-ingest after cutting a version control release** to build FAISS for the new version.
7. **One FAISS index per `$DDI_ROOT_PATH` value.** Don't share indices across online and version control.

## 8. SOS + ENRICHMENT WORKFLOW

All sidecar modifications in SOS workspaces go through **All-Might commands**:

1. Use `/enrich --file <relative_path> --symbol <name> --intent "..."` to annotate symbols
2. Use `/enrich ... --relation <uid>` to add cross-references
3. **Never** edit `.sidecar.yaml` files by hand — the `/enrich` command handles:
   - Correct YAML schema and nesting
   - Proper UID format with `$DDI_ROOT_PATH` prefix where needed
   - Bidirectional relation management
4. After `sos check-in`, sidecars are committed to the canonical path (Layer 1/2)
   and become available for `smak ingest` and team-wide search

For the full enrichment protocol, see the `enrichment-protocol` skill.

## 9. WORKSPACE_CONFIG.YAML MANAGEMENT

`workspace_config.yaml` defines which source paths to index. It lives in the All-Might hub folder.

### Adding or modifying indices

**Always use All-Might commands** to modify `workspace_config.yaml`:

```bash
# Add a new index
allmight config add-index --name rtl_code \
    --description "Verilog RTL modules" \
    --paths '$DDI_ROOT_PATH/rtl/phy' \
    --path-env DDI_ROOT_PATH

# Update an existing index
allmight config update-index --name rtl_code \
    --description "Updated description" \
    --paths '$DDI_ROOT_PATH/rtl'

# Remove an index
allmight config remove-index --name rtl_code

# List current indices
allmight config list-indices
```

**NEVER** edit `workspace_config.yaml` by hand. The commands ensure:
- Correct YAML structure and field names
- Consistent `uri` generation (`./smak/<index_name>`)
- Sync between `workspace_config.yaml` and `all-might/config.yaml`

### Required fields per index

| Field | Required | Example | Purpose |
|-------|----------|---------|---------|
| `name` | Yes | `rtl_code` | Unique identifier |
| `description` | Yes | `"Verilog RTL modules for DDR5 PHY"` | Human-readable purpose |
| `paths` | Yes | `["$DDI_ROOT_PATH/rtl/phy"]` | Source directories to index |
| `uri` | Auto | `./smak/rtl_code` | FAISS database location (auto-generated) |
| `path_env` | SOS only | `DDI_ROOT_PATH` | Environment variable for path prefix |

After adding/modifying indices, run `/ingest` to rebuild the FAISS database.
"""
