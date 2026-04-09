"""Bundled SOS skill content for CliosoftSOS environments.

All-Might ships its own copy of the SOS skill body so there is no
runtime dependency on SMAK skill files being present on disk.
"""

SOS_SKILL_BODY = """\
# CliosoftSOS + SMAK Workflow

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
Layer 1: Online (production / main)
  $DDI_ROOT_PATH = /CAD/stdcell
  Access:  READ-ONLY (shared disk, visible to everyone)
  Purpose: The "truth" — production codebase
  FAISS:   Primary index is built from this layer

Layer 2: Version Control (flow releases)
  $DDI_ROOT_PATH = /CAD/stdcell_production/{version_string}/
  Access:  READ-ONLY (shared disk, visible to everyone)
  Purpose: Frozen snapshots of specific releases
  FAISS:   Each version can have its own FAISS index

Layer 3: SOS Workspace (personal checkout)
  Path:    /arbitrary/path/created/by/sos/
  Access:  READ-WRITE (the only place you can edit files)
  Purpose: Personal working area for making changes
  Sidecar: All sidecar edits happen here
```

### Key rules

- **Online and version control are read-only.** You cannot edit files there directly.
- **All edits happen in an SOS workspace.** After editing, `sos check-in` pushes changes back.
- **`$DDI_ROOT_PATH` is the abstraction** that points to either online or a specific version.
- **The workspace path is NOT `$DDI_ROOT_PATH`.** Workspace is a temporary working area at an unrelated path.

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
4. After `sos check-in`: sidecar lands at the canonical path

## 5. PATH MISMATCH WARNING

When editing sidecars in a workspace, SMAK may emit path mismatch warnings. **This is normal** — it means you're editing in a workspace (Layer 3) while relations correctly point to the canonical path (Layer 1/2). After `sos check-in`, everything aligns.

## 6. WHICH LAYER TO TARGET

| Task | Target Layer | $DDI_ROOT_PATH |
|---|---|---|
| Build FAISS for production | Online | `/CAD/stdcell` |
| Build FAISS for a release | Version Control | `/CAD/stdcell_production/{version}/` |
| Edit sidecars | Workspace (Layer 3) | Set to the target layer (1 or 2) |
| Search/query | Any (reads FAISS) | Set to match the FAISS you want to query |

## 7. STRICT RULES FOR SOS ENVIRONMENTS

1. **Never hardcode absolute paths in relations.** Always use `$DDI_ROOT_PATH/...` format.
2. **Never edit sidecars directly in online or version control.** Always use an SOS workspace.
3. **Always set `path_env: DDI_ROOT_PATH`** in config for indices on the shared disk.
4. **Set `$DDI_ROOT_PATH` before running SMAK** — it determines which layer you're operating on.
5. **Path mismatch warnings in workspaces are normal.** Don't suppress or work around them.
6. **Re-ingest after cutting a version control release** to build FAISS for the new version.
7. **One FAISS index per `$DDI_ROOT_PATH` value.** Don't share indices across online and version control.
"""
