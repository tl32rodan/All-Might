"""Personality framework — pluggable capabilities for an All-Might project.

A *personality* is a user-defined role that bundles one or more
capabilities (e.g. ``database`` for knowledge-graph workspaces,
``memory`` for L1/L2/L3 agent memory).
Each capability is split in two:

* ``PersonalityTemplate`` — the *kind*. A static description plus the
  ``install`` and ``status`` callables. Discovered at runtime.
* ``Personality``         — an *instance* of a template attached to one
  project. Lives under ``personalities/<name>/`` and owns its own
  agent surface (skills/commands/plugins) plus its data dir
  (``database/`` or ``memory/``).

The top-level ``.opencode/`` is **composed** from each instance's
``skills/``, ``commands/``, ``plugins/`` via symlinks; agent-facing
entrypoints (``AGENTS.md``, ``MEMORY.md``) stay at the project root.

Design notes
------------
* Templates are plain Python objects, not subclasses. Discovery is a
  shallow scan of ``allmight.capabilities.*`` for a ``TEMPLATE``
  attribute. No entry points, no plugin registry — third-party
  authoring is **explicitly out of scope** for this PR (TODO marker
  below).
* ``cli.py`` knows nothing template-specific. Per-template flags like
  ``--sos`` are contributed via :class:`CliOption`; the CLI registers
  them dynamically and forwards the raw option dict to every
  ``Personality.options``. Each template extracts what it needs.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .domain import ProjectManifest


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CliOption:
    """A CLI flag a template contributes to ``allmight init``.

    The CLI does not interpret these flags itself — it forwards their
    parsed values into every :class:`Personality`'s ``options`` dict
    keyed by ``name``. The owning template extracts what it cares
    about inside its ``install`` callable.
    """

    name: str
    flag: str
    is_flag: bool = True
    default: Any = None
    help: str = ""


@dataclass
class InstallContext:
    """Cross-cutting state passed to every ``install`` /
    ``install_globals`` call.

    ``options`` carries CLI-level flags that templates need at the
    project-wide install step (e.g. ``sos=True`` for the database
    capability) — there's no ``Personality`` instance at that point
    so options can't ride on ``Personality.options``.
    """

    project_root: Path
    manifest: ProjectManifest
    staging: bool = False
    force: bool = False
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class InstallResult:
    """What an ``install`` call returns to the registry."""

    notes: list[str] = field(default_factory=list)


@dataclass
class PersonalityStatus:
    """What ``status`` returns for one instance, used by ``allmight status``."""

    installed: bool
    version_on_disk: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PersonalityTemplate:
    """The KIND of a capability (e.g. ``database``, ``memory``).

    Plain dataclass holding metadata plus the two operation callables.
    Built-in templates live as module-level ``TEMPLATE`` constants
    inside ``allmight.capabilities.<name>``.

    ``default_instance_name`` is the slug used when ``allmight init``
    runs non-interactively (or the user accepts the default). Should be
    a filesystem-safe slug (slugify_instance_name-friendly) — e.g.
    ``"knowledge"`` for ``database``, ``"memory"`` for ``memory``.
    """

    name: str
    short_name: str
    version: str
    description: str
    owned_paths: list[str]
    cli_options: list[CliOption]
    install: Callable[["InstallContext", "Personality"], InstallResult]
    status: Callable[[Path, "Personality"], PersonalityStatus]
    default_instance_name: str = ""
    install_globals: Callable[["InstallContext"], None] | None = None
    """Project-wide install step. Called once per template at init time
    (before any ``Personality`` instance exists). Writes the
    ``.opencode/`` skills/commands/plugins, root MEMORY.md / AGENTS.md
    placeholders, and any ``.allmight/`` mode files. ``None`` means the
    template has no project-wide assets — the install loop just skips
    it. Per-personality writes still go through ``install`` (called by
    ``allmight add``)."""


@dataclass
class Personality:
    """An INSTANCE of a template attached to one project.

    Part-D extension: a personality bundles one role (``ROLE.md``)
    plus zero-or-more *capability subdirs* (``database/``, ``memory/``).
    The legacy ``template`` field still names the **primary** template
    for Part-C-shaped callers; ``capabilities`` is the Part-D source
    of truth for "what data dirs does this personality own?".

    For pure single-capability Part-C personalities, ``capabilities``
    is left empty and ``template.short_name`` is treated as the only
    one. Part-D personalities populate ``capabilities`` explicitly.
    """

    template: PersonalityTemplate
    project_root: Path
    name: str
    options: dict[str, Any] = field(default_factory=dict)

    # Part-D additions (default-empty so all existing call sites work):
    capabilities: list[str] = field(default_factory=list)
    role_summary: str = ""

    @property
    def root(self) -> Path:
        """Directory the personality owns: ``personalities/<name>/``."""
        return self.project_root / "personalities" / self.name

    def capability_root(self, capability: str) -> Path:
        """Where a given capability's data dir lives, e.g. ``…/<name>/database/``.

        Used by capability templates in Part D to address their data
        without hard-coding paths.
        """
        return self.root / capability


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover(package: str = "allmight.capabilities") -> list[PersonalityTemplate]:
    """Scan ``package`` for subpackages exposing a ``TEMPLATE`` attribute.

    Discovery order is the iteration order of ``pkgutil.iter_modules``,
    which is alphabetical on POSIX. Order matters because ``database``
    writes ``AGENTS.md`` before ``memory`` appends its memory section.
    The two built-in templates already sort that way (``database`` <
    ``memory``); if a third template is added that needs a specific
    slot, give it a name that sorts correctly or extend this function
    with explicit ordering.

    Duplicate template ``name`` values raise ``ValueError``.
    """
    try:
        pkg = importlib.import_module(package)
    except ModuleNotFoundError:
        return []

    templates: list[PersonalityTemplate] = []
    seen: set[str] = set()
    for info in pkgutil.iter_modules(pkg.__path__, prefix=f"{package}."):
        if not info.ispkg:
            continue
        mod = importlib.import_module(info.name)
        tmpl = getattr(mod, "TEMPLATE", None)
        if tmpl is None:
            continue
        if not isinstance(tmpl, PersonalityTemplate):
            raise TypeError(
                f"{info.name}.TEMPLATE must be a PersonalityTemplate, got "
                f"{type(tmpl).__name__}"
            )
        if tmpl.name in seen:
            raise ValueError(f"duplicate personality template name: {tmpl.name}")
        seen.add(tmpl.name)
        templates.append(tmpl)
    return templates


# TODO(future): user-defined templates via entry-points. Out of scope for
# this PR — built-in discovery is sufficient.


# ---------------------------------------------------------------------------
# Composition (downward symlinks .opencode/<kind>/<X> -> personalities/<p>/<kind>/<X>)
# ---------------------------------------------------------------------------


# Each personality has its own real subdir for these kinds. Capability
# templates write the project-wide *globals* directly into
# ``.opencode/<kind>/``; ``compose`` projects every per-personality
# entry into ``.opencode/<kind>/<basename>`` as a relative symlink so
# OpenCode discovers it from the same global scan.
#
# ``plugins/`` is intentionally not exposed per-personality — plugins
# are project-wide hooks, not personality-scoped.
_COMPOSED_KINDS = ("skills", "commands")


@dataclass
class ComposeConflict:
    """A downward-symlink target we refused to overwrite.

    Raised by ``compose()`` when ``.opencode/<kind>/<basename>`` is
    already occupied (by a capability-written global, by another
    personality's symlink, or by user content) and we refuse to
    silently replace it. The agent resolves the conflict during
    ``/sync``.

    Attributes:
        instance_name: Name of the personality instance whose entry
            we tried to project.
        kind: One of ``skills`` or ``commands``.
        basename: Final path component (e.g. ``stdcell-special.md``).
        dst: Absolute path of the conflicted location
            (``.opencode/<kind>/<basename>``).
        source: Absolute path of the personality entry we wanted to
            symlink to (``personalities/<p>/<kind>/<basename>``).
        existing: ``"file"``, ``"directory"``, or
            ``"symlink-to-elsewhere"`` — what currently occupies dst.
    """

    instance_name: str
    kind: str
    basename: str
    dst: Path
    source: Path
    existing: str


def compose(
    project_root: Path,
    instance: Personality,
    *,
    force: bool = False,
) -> list[ComposeConflict]:
    """Project ``personalities/<p>/{skills,commands}/*`` into ``.opencode/``.

    Part-D model: capability templates write project-wide globals
    (``search.md``, ``remember.md``, …) directly into ``.opencode/``.
    Personalities own their own real ``commands/`` and ``skills/``
    subdirs, where the agent may write personality-specific entries
    at runtime. ``compose`` then projects every per-personality entry
    into ``.opencode/<kind>/<basename>`` as a relative symlink so
    OpenCode discovers it via its single ``.opencode/`` scan.

    The personality dirs are created (empty) on every call so the
    agent always has somewhere to write into.

    Conflict handling — never raises, returns conflicts instead:

    * **Already correct** (symlink to our entry): idempotent.
    * **Symlink to elsewhere**: conflict; ``force=True`` replaces.
    * **Regular file with an All-Might marker**: stale, auto-resolved.
    * **Regular file without a marker**: user/global authored —
      conflict; ``force=True`` replaces.
    * **Directory**: conflict (we never recursively delete user
      content); ``force=True`` replaces only when the dir is itself
      stale All-Might-owned.
    """
    from .markers import ALLMIGHT_MARKER_MD, ALLMIGHT_MARKER_TS, ALLMIGHT_MARKER_YAML

    markers = (ALLMIGHT_MARKER_MD, ALLMIGHT_MARKER_TS, ALLMIGHT_MARKER_YAML)

    def _looks_owned(path: Path) -> bool:
        try:
            head = path.read_bytes()[:4096].decode("utf-8", errors="replace")
        except OSError:
            return False
        return any(m in head for m in markers)

    def _dir_looks_owned(path: Path) -> bool:
        for child in path.rglob("*"):
            if child.is_file() and _looks_owned(child):
                return True
        return False

    instance_root = instance.root
    instance_root.mkdir(parents=True, exist_ok=True)

    conflicts: list[ComposeConflict] = []

    for kind in _COMPOSED_KINDS:
        # Personality's own real dir — initially empty; agent writes here.
        src_dir = instance_root / kind
        src_dir.mkdir(parents=True, exist_ok=True)

        # Global .opencode/<kind>/ where capability writes globals
        # and where we project personality entries via symlink.
        dst_dir = project_root / ".opencode" / kind
        dst_dir.mkdir(parents=True, exist_ok=True)

        for entry in sorted(src_dir.iterdir()):
            dst = dst_dir / entry.name

            if dst.is_symlink():
                if force or dst.resolve() == entry.resolve():
                    dst.unlink()
                else:
                    conflicts.append(ComposeConflict(
                        instance_name=instance.name,
                        kind=kind,
                        basename=entry.name,
                        dst=dst,
                        source=entry,
                        existing="symlink-to-elsewhere",
                    ))
                    continue
            elif dst.exists():
                if dst.is_dir():
                    if force or _dir_looks_owned(dst):
                        import shutil

                        shutil.rmtree(dst)
                    else:
                        conflicts.append(ComposeConflict(
                            instance_name=instance.name,
                            kind=kind,
                            basename=entry.name,
                            dst=dst,
                            source=entry,
                            existing="directory",
                        ))
                        continue
                else:
                    # Capability-written globals carry our marker. We
                    # don't auto-delete those — different personalities
                    # might want to define a same-named entry, but only
                    # one wins at .opencode/<kind>/<basename>.
                    if force:
                        dst.unlink()
                    else:
                        conflicts.append(ComposeConflict(
                            instance_name=instance.name,
                            kind=kind,
                            basename=entry.name,
                            dst=dst,
                            source=entry,
                            existing="file",
                        ))
                        continue

            dst.symlink_to(os.path.relpath(entry, dst_dir))

    return conflicts


def stage_compose_conflicts(
    project_root: Path,
    conflicts: list[ComposeConflict],
) -> Path | None:
    """Persist a conflict manifest at ``.allmight/templates/conflicts.yaml``.

    ``/sync`` reads this file to learn which composition targets need
    user-driven resolution. Returns the manifest path, or ``None`` if
    there were no conflicts (and nothing was written / any prior
    manifest is removed).
    """
    import yaml

    path = project_root / ".allmight" / "templates" / "conflicts.yaml"
    if not conflicts:
        if path.exists():
            path.unlink()
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    def _rel(p: Path) -> str:
        # ``source`` is the symlink target, which is intentionally relative
        # in the upward-symlink model (e.g. ``../../.opencode/commands``).
        # ``dst`` is the absolute personality dir we wanted to write into.
        if p.is_absolute():
            try:
                return str(p.relative_to(project_root))
            except ValueError:
                return str(p)
        return str(p)

    payload = {
        "compose_conflicts": [
            {
                "instance": c.instance_name,
                "kind": c.kind,
                "basename": c.basename,
                "dst": _rel(c.dst),
                "source": _rel(c.source),
                "existing": c.existing,
            }
            for c in conflicts
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path


# ---------------------------------------------------------------------------
# Init scaffold (single .opencode/opencode.json + package.json per project)
# ---------------------------------------------------------------------------


_OPENCODE_PACKAGE_JSON = (
    '{\n'
    '  "name": "all-might-opencode",\n'
    '  "private": true,\n'
    '  "dependencies": {\n'
    '    "@opencode-ai/plugin": "latest"\n'
    '  }\n'
    '}\n'
)


def write_init_scaffold(project_root: Path) -> None:
    """Write project-level files that don't belong to any template.

    Currently: ``.opencode/opencode.json`` (with the schema header) and
    ``.opencode/package.json`` (so OpenCode's bundled Bun can resolve
    ``@opencode-ai/plugin``). Both are idempotent — existing files are
    preserved, only the schema field is ensured for ``opencode.json``
    and the plugin dependency for ``package.json``.

    Also creates ``personalities/`` so symlink composition has a stable
    parent.
    """
    import json

    (project_root / "personalities").mkdir(exist_ok=True)

    opencode_dir = project_root / ".opencode"
    opencode_dir.mkdir(exist_ok=True)

    opencode_json = opencode_dir / "opencode.json"
    if opencode_json.exists():
        try:
            cfg = json.loads(opencode_json.read_text())
        except (json.JSONDecodeError, OSError):
            cfg = {}
    else:
        cfg = {}
    # Only set $schema if absent — never overwrite a user-chosen value,
    # otherwise a project that uses an internal mirror gets clobbered
    # on every re-init.
    cfg.setdefault("$schema", "https://opencode.ai/config.json")
    # Knowledge MCP server — the offline web_search/context7 substitute.
    # setdefault so a user-customised entry survives re-init (same policy
    # as $schema). Single-source entry lives in claude_bridge.
    from .claude_bridge import MCP_SERVER_NAME, opencode_mcp_entry

    cfg.setdefault("mcp", {}).setdefault(MCP_SERVER_NAME, opencode_mcp_entry())
    opencode_json.write_text(json.dumps(cfg, indent=2) + "\n")

    pkg_json = opencode_dir / "package.json"
    if pkg_json.exists():
        try:
            existing = json.loads(pkg_json.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}
        deps = existing.setdefault("dependencies", {})
        deps.setdefault("@opencode-ai/plugin", "latest")
        pkg_json.write_text(json.dumps(existing, indent=2) + "\n")
    else:
        pkg_json.write_text(_OPENCODE_PACKAGE_JSON)

    _write_role_load_plugin(project_root)
    _write_feedback_check_plugin(project_root)
    _write_offline_reference_plugin(project_root)

    # Bundled OpenCode reference + /opencode-ref skill. Framework-level
    # (no personality owns it) so it lives next to the other scaffold
    # writes here, not under capabilities/.
    from .opencode_reference import write_opencode_reference

    write_opencode_reference(project_root)

    # Working-discipline contract + /whip-it skill. Framework-level for
    # the same reason — no personality owns discipline.
    from .whip_it import write_whip_it

    write_whip_it(project_root)

    # Claude Code compatibility bridge — markdown surface via dir
    # symlinks, agent context via @-import shim, runtime hooks for
    # role-load (memory-load lives in the memory capability).
    from .claude_bridge import write_claude_bridge

    write_claude_bridge(project_root)


# ---------------------------------------------------------------------------
# ROLE.md composition + role-load.ts plugin
# ---------------------------------------------------------------------------


_AGENTS_MD_HEADER = (
    "<!-- all-might generated -->\n"
    "<!--\n"
    "  This file is composed from the All-Might framework primer plus\n"
    "  each personality's ROLE.md. Edit personalities/<name>/ROLE.md to\n"
    "  change a personality's behaviour; do not edit this file by hand.\n"
    "-->\n\n"
    "# {project_name}\n"
)


_AGENTS_MD_FRAMEWORK_PRIMER = """## About All-Might

You are running inside an All-Might project. All-Might organises this
workspace around **personalities** — user-defined roles such as
`stdcell_owner` or `code_reviewer` — each of which opts into one or
more **capabilities**:

- **`database`** — knowledge graph over the project's source code.
  Gives the personality `/search` and a per-personality SMAK workspace
  at `personalities/<name>/database/<workspace>/`.
- **`memory`** — cross-session memory. Gives the personality
  `/remember`, `/reflect`, `/recall`, and a per-personality
  `understanding/` + `journal/` tree at
  `personalities/<name>/memory/`.

There is exactly **one** flat slash-command surface for the whole
project (`.opencode/commands/` and `.opencode/skills/`). The
personality a command acts for is resolved at call time — see
"Routing" below.

## Slash commands

| Command | What it does |
|---------|--------------|
| `/onboard` | Create personalities. Proposes from `.allmight/suggestions/personalities/`, then shells out to `allmight add <name>` for each pick. **Run this first when no personalities exist.** |
| `/search <query>` | Semantic search inside the active personality's database workspace. |
| `/remember <fact>` | Record a single observation in the right scope (L1 / L2 / L3 / per-kind). |
| `/reflect` | End-of-session audit: cap triage, scope drift, insights. |
| `/recall <query>` | Search past journal entries for the active personality. |
| `/recover` | Restore a deleted or overwritten memory file from `.allmight/memory-history/` snapshots. |
| `/one-for-all` | Bundle one personality outward for sharing (1 → 1). |
| `/all-for-one` | Absorb N sources into one personality (N → 1). |
| `/split` | Refactor within a project: extract memory + scope from one personality into another (1 → 1, same project). |
| `/sync` | Merge `.allmight/templates/` after a re-init, or resolve compose conflicts. |
| `/whip-it` | Re-assert the working-discipline contract (TDD-first, Unix search, recorded agreements, post-compaction re-anchor, no shortcuts). |

Database is **search-only** to the agent; index builds happen
out-of-band via `smak`. The memory journal is **auto-indexed between
sessions** — entries written via `/remember` become searchable via
`/recall` starting from the next session.

## Routing — which personality acts?

Every routed command body is prefixed with ``ROUTING_PREAMBLE`` (see
`core/routing.py`), which teaches the agent to resolve the active
personality from: explicit mention → conversation context →
`MEMORY.md`'s ``> **Default personality**: <name>`` callout. If none
resolves, ask the user — never guess.

## Personality subagents (`@<name>`)

Every installed personality is also exposed as an OpenCode subagent
at `.opencode/agents/<name>.md` — `@<name>`-mention to invoke for one
task without switching sessions. The agent file is a pointer; the
behaviour spec is `personalities/<name>/ROLE.md`.

## When to suggest user actions

| Situation | Suggest |
|---|---|
| `.allmight/personalities.yaml` is empty | Run `/onboard` |
| User reports a lost or overwritten memory file | Run `/recover` |
| Files staged at `.allmight/templates/` after re-init | Run `/sync` |
| User wants to ship a personality to another project | Run `/one-for-all` |
| User wants to fold sources into a personality | Run `/all-for-one` |
| Re-init complains about path conflicts | Open `.allmight/templates/conflicts.yaml` |

## Memory model — scope-first

Memory is **scope-first**: before writing, decide whether the
observation is project-wide (`MEMORY.md`), personality-specific
(`personalities/<active>/memory/understanding/<topic>.md`), or
episodic (`personalities/<active>/memory/journal/...`). Default to
the narrower scope. Full rules: see the `/remember` body.

## Recovery awareness

Every memory write is auto-snapshotted into
`.allmight/memory-history/.git` by a per-turn hook. Accidental
deletes / overwrites are recoverable via `/recover` or
`allmight memory restore <file> --rev <sha>`. SMAK vector indices
(`store/`) are excluded — rebuild them out-of-band via `smak ingest`.

## SMAK reference — find before invoking

The `smak` CLI is a separate Python package. When you need exact
flags, JSON shapes, or workflow conventions, **read SMAK's own
canonical docs** instead of inferring. Discovery:

```bash
python -c "import smak, pathlib; print(pathlib.Path(smak.__path__[0]))"
```

From that directory: `skills/smak-skill/SKILL.md` is the canonical
agent-facing guide (pull it into context before any non-trivial use);
`skills/sos-smak-skill/SKILL.md` covers CliosoftSOS / EDA paths;
`cli.py` is the executable spec. If `import smak` raises
``ModuleNotFoundError``, surface that to the user — do not guess.

## OpenCode reference — read before touching `.opencode/`

When authoring or modifying `.opencode/plugins/*.ts`,
`.opencode/agents/<name>.md`, slash-command bodies or
`opencode.json`, read the bundled cheat-sheet at
`.opencode/reference/opencode/README.md` first — it covers the
wrong-shape traps the test suite cannot catch (the `chat.message`
hook signature, the `output.parts.unshift(...)` injection path, the
`subagent` vs `primary` mode default). The matching `/opencode-ref`
skill auto-loads this pointer when relevant.

## Working discipline — binding, survives compaction

The rule sheet at `.opencode/skills/whip-it/SKILL.md` is a binding
contract for every session: TDD-first (RED before any production
code), native Unix search instead of built-in Grep/Glob, recorded
agreements over general convention, full scope with real output.
**After every compaction**, re-read that file plus `MEMORY.md`, the
active `ROLE.md`, and this file before continuing work. The user
invokes `/whip-it` to re-assert the contract on demand.

## Layering — what lives where

| File | Audience |
|------|----------|
| `AGENTS.md` (this file) | Agent — framework primer + composed `ROLE.md` (high-level WHAT) |
| `MEMORY.md` | Project map + default-personality callout + user prefs |
| `personalities/<name>/ROLE.md` | Per-role behaviour spec |
| `.opencode/{commands,skills}/<name>` | The HOW (step-by-step bodies) |
| `README.md` | Human-facing narrative |

When you need the HOW behind a slash command, read its
`.opencode/skills/<name>/SKILL.md` or `commands/<name>.md`.
"""


def compose_role_agents(
    project_root: Path,
    instances: list["Personality"],
) -> list[Path]:
    """Project each personality as an OpenCode subagent file.

    For every instance with a ``ROLE.md`` on disk, write
    ``.opencode/agents/<name>.md`` — a thin OpenCode agent file whose
    ``prompt:`` frontmatter points back at the personality's
    ``ROLE.md`` (so ROLE.md stays the single source of truth and
    editing it updates the agent's behaviour without re-running
    ``allmight init``).

    Agents are emitted as **subagents**: the user does not switch
    sessions to use a personality. Instead they ``@<name>`` mention
    it from any conversation and OpenCode invokes the personality
    for that one task. This matches All-Might's "no default
    personality switch" UX — personalities are specialised helpers,
    not interaction modes.

    Re-init safety:

    * First write: creates ``.opencode/agents/<name>.md`` directly.
    * User-authored ``.opencode/agents/<name>.md`` (no All-Might
      marker): preserved untouched; the fresh content stages to
      ``.allmight/templates/agents/<name>.md`` so ``/sync`` can
      reconcile (same pattern as command / plugin re-init staging).
    * Already-All-Might-owned file: refreshed in place.

    Returns the list of paths actually written (working file or
    staging file), in instance order. Missing ROLE.md is skipped.
    """
    from .markers import ALLMIGHT_MARKER_MD
    from .safe_write import write_guarded

    written: list[Path] = []
    agents_dir = project_root / ".opencode" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = project_root / ".allmight" / "templates" / "agents"

    for instance in instances:
        role_md = instance.root / "ROLE.md"
        if not role_md.is_file():
            continue
        content = _role_agent_content(instance)
        target = agents_dir / f"{instance.name}.md"
        wrote = write_guarded(target, content, ALLMIGHT_MARKER_MD)
        if wrote:
            written.append(target)
            continue
        # User-authored conflict — stage the fresh content so ``/sync``
        # can merge it. The user's working file is left untouched.
        staging_dir.mkdir(parents=True, exist_ok=True)
        staged = staging_dir / f"{instance.name}.md"
        staged.write_text(content)
        written.append(staged)
    return written


def _role_agent_content(instance: "Personality") -> str:
    """Render the ``.opencode/agents/<name>.md`` body for one instance.

    Frontmatter fields:

    * ``description`` — required by OpenCode. Extracted from the
      first paragraph of ``ROLE.md`` (the natural "what this
      personality does" prose). ROLE.md is the single source of
      truth; we deliberately do **not** read this from a separate
      registry field that would have to be kept in sync.
    * ``mode: subagent`` — invoked via ``@<name>`` mention, never
      via Tab-switch.
    * ``prompt: "{file:../personalities/<name>/ROLE.md}"`` — the
      documented OpenCode way to point an agent at an external
      system-prompt file. Path is relative to the agent file's
      location, which is always ``.opencode/agents/``.

    The All-Might marker lives in the body (after the frontmatter)
    so write_guarded recognises the file as ours on re-init without
    breaking OpenCode's frontmatter parser (which requires
    ``---`` to be the first line).
    """
    desc = _extract_role_description(instance.root / "ROLE.md", instance.name)
    # YAML double-quoted scalar — escape backslashes and double-quotes.
    desc = desc.replace("\\", "\\\\").replace('"', '\\"')
    return (
        "---\n"
        f'description: "{desc}"\n'
        "mode: subagent\n"
        f'prompt: "{{file:../personalities/{instance.name}/ROLE.md}}"\n'
        "---\n"
        "<!-- all-might generated -->\n"
        f"<!-- Edit personalities/{instance.name}/ROLE.md to change "
        "this agent's behaviour; this file is just a pointer. -->\n"
    )


_DESCRIPTION_MAX_LEN = 200


def _extract_role_description(role_md: Path, fallback_name: str) -> str:
    """Return a one-line description suitable for OpenCode's frontmatter.

    Strategy: parse ROLE.md and take the first non-empty *paragraph*
    that isn't a heading or HTML comment. Collapse internal whitespace
    so the result fits on one YAML line, and truncate to
    ``_DESCRIPTION_MAX_LEN`` characters (with an ellipsis) so the agent
    picker UI doesn't get a wall of text.

    Falls back to ``"<fallback_name> personality"`` if no usable
    paragraph is found — OpenCode requires ``description`` to be
    non-empty, so we always return something.
    """
    fallback = f"{fallback_name} personality"
    try:
        text = role_md.read_text(encoding="utf-8")
    except OSError:
        return fallback

    # Walk paragraph by paragraph. A paragraph is a blank-line-delimited
    # run; the first one that is neither a heading nor an HTML comment
    # wins.
    paragraphs = text.split("\n\n")
    for raw in paragraphs:
        stripped = raw.strip()
        if not stripped:
            continue
        # Skip headings ('#', '##', ...) and HTML comments
        # (``<!-- all-might generated -->`` etc.).
        if stripped.startswith("#") or stripped.startswith("<!--"):
            continue
        # Collapse internal newlines + repeated whitespace into single
        # spaces so the YAML scalar is one line.
        flat = " ".join(stripped.split())
        if not flat:
            continue
        if len(flat) > _DESCRIPTION_MAX_LEN:
            flat = flat[: _DESCRIPTION_MAX_LEN - 1].rstrip() + "…"
        return flat
    return fallback


def compose_agents_md(
    project_root: Path,
    instances: list["Personality"],
    *,
    project_name: str | None = None,
    force: bool = False,
) -> Path:
    """Stitch the framework primer and each instance's ROLE.md into AGENTS.md.

    Assembly order:

    1. Project-name header.
    2. ``_AGENTS_MD_FRAMEWORK_PRIMER`` — fixed agent-facing primer that
       explains personalities, capabilities, the slash-command surface,
       routing, and recovery. Survives every recompose so an air-gap
       agent has framework context from day 1, before any personality
       is created.
    3. ``## Personalities`` section header.
    4. Each ROLE.md body in registry order, separated by blank lines.
       When ``instances`` is empty, a callout points the agent at
       ``/onboard``.

    The composed file carries the All-Might marker so re-init can tell
    its own composed output from a user-edited AGENTS.md. A root
    AGENTS.md *without* the marker is user-authored (super-learner
    style hand-written entry points exist in the wild): it is left
    untouched and the fresh composition is staged at
    ``.allmight/templates/AGENTS.md`` for ``/sync`` to reconcile. The
    returned path is whichever file was actually written.

    ``force=True`` bypasses the guard — used by the one-shot migrator,
    which rewrites a *legacy-format* AGENTS.md (fence markers, no
    file-level marker) that is known to be All-Might-authored.
    """
    from .markers import ALLMIGHT_MARKER_MD
    from .safe_write import write_guarded

    name = project_name or project_root.name
    sections: list[str] = [
        _AGENTS_MD_HEADER.format(project_name=name).rstrip(),
        _AGENTS_MD_FRAMEWORK_PRIMER.rstrip(),
        "## Personalities",
    ]
    bodies: list[str] = []
    for instance in instances:
        role_md = instance.root / "ROLE.md"
        if not role_md.is_file():
            continue
        body = role_md.read_text().rstrip()
        if body.startswith(ALLMIGHT_MARKER_MD):
            body = body[len(ALLMIGHT_MARKER_MD):].lstrip("\n")
        bodies.append(body)
    if bodies:
        sections.append("\n\n".join(bodies))
    else:
        sections.append(
            "*(no personalities yet — run `/onboard` to set up the first one.)*"
        )
    content = "\n\n".join(sections) + "\n"
    agents_md = project_root / "AGENTS.md"
    if write_guarded(agents_md, content, ALLMIGHT_MARKER_MD, force=force):
        return agents_md
    # User-authored AGENTS.md (no marker): never clobber. Stage the
    # fresh composition for /sync instead.
    staged = project_root / ".allmight" / "templates" / "AGENTS.md"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(content)
    return staged


def _write_role_load_plugin(project_root: Path) -> None:
    """Write ``.opencode/plugins/role-load.ts`` if absent or owned.

    Mirrors the memory-load.ts pattern: at every ``chat.message`` for
    an un-primed session, scan ``personalities/*/ROLE.md`` and inject
    them as a synthetic prefix part. ``session.created``,
    ``session.compacted``, ``session.deleted`` events clear the primed
    flag so the next message re-injects.

    The plugin is project-level (not owned by any personality) — same
    status as ``opencode.json``.
    """
    from .markers import ALLMIGHT_MARKER_TS
    from .safe_write import write_guarded

    plugins_dir = project_root / ".opencode" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    write_guarded(
        plugins_dir / "role-load.ts",
        _role_load_plugin_content(),
        ALLMIGHT_MARKER_TS,
    )


def _role_load_plugin_content() -> str:
    from .plugin_telemetry import TS_HEARTBEAT_SNIPPET
    return _ROLE_LOAD_PLUGIN_TEMPLATE.replace(
        "__TS_HEARTBEAT_SNIPPET__", TS_HEARTBEAT_SNIPPET,
    )


_ROLE_LOAD_PLUGIN_TEMPLATE = """\
// all-might generated
/**
 * Role Loader — OpenCode plugin (All-Might)
 *
 * Primes the agent's context with each personality's ROLE.md at the
 * start of every (un-primed) session, and re-primes after compaction
 * — compaction summarises history and dilutes the role description,
 * so a fresh injection keeps each personality's identity stable.
 *
 * Events:
 *   session.created    -> mark session un-primed
 *   session.compacted  -> mark session un-primed (re-inject next message)
 *   session.deleted    -> drop state
 *
 * Hook:
 *   chat.message -> inject ROLE.md prefix once per (un-primed) session
 */
import type { Plugin } from "@opencode-ai/plugin";
import { readFileSync, existsSync, readdirSync, statSync } from "fs";
import { join } from "path";

__TS_HEARTBEAT_SNIPPET__
const primed = new Set<string>();

function readAllRoles(cwd: string): string {
  const personalitiesDir = join(cwd, "personalities");
  if (!existsSync(personalitiesDir)) return "";
  const parts: string[] = [];
  let entries: string[] = [];
  try {
    entries = readdirSync(personalitiesDir).sort();
  } catch {
    return "";
  }
  for (const name of entries) {
    const rolePath = join(personalitiesDir, name, "ROLE.md");
    if (!existsSync(rolePath)) continue;
    let stat;
    try {
      stat = statSync(rolePath);
    } catch {
      continue;
    }
    if (!stat.isFile()) continue;
    try {
      parts.push(`--- Role: ${name} (ROLE.md) ---`);
      parts.push(readFileSync(rolePath, "utf-8"));
      parts.push(`--- End Role: ${name} ---`);
      parts.push("");
    } catch {
      // ignore unreadable role files
    }
  }
  return parts.join("\\n");
}

export const RoleLoadPlugin: Plugin = async ({ directory }: any) => {
  const cwd = (directory as string | undefined) ?? process.cwd();

  return {
    event: async ({ event }: { event: any }) => {
      emitHeartbeat("role-load", cwd);
      const type = event?.type;
      const sid = event?.properties?.sessionID ?? "";
      if (!sid) return;
      if (
        type === "session.created" ||
        type === "session.compacted" ||
        type === "session.deleted"
      ) {
        primed.delete(sid);
      }
    },

    "chat.message": async (input: any, output: any) => {
      emitHeartbeat("role-load", cwd);
      const sid = input?.sessionID;
      if (!sid) return;
      if (primed.has(sid)) return;

      const text = readAllRoles(cwd);
      if (!text.trim()) return;

      const mid = output?.message?.id;
      if (!mid) return;
      if (!Array.isArray(output?.parts)) return;
      output.parts.unshift({
        id: "prt_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10),
        sessionID: sid,
        messageID: mid,
        type: "text",
        text,
        synthetic: true,
      });
      primed.add(sid);
      emitHeartbeat("role-load.injected", cwd);
    },
  };
};

export default RoleLoadPlugin;
"""


# ---------------------------------------------------------------------------
# Feedback-check plugin (project-level, every chat.message)
#
# Renamed from ``reflection`` (2026-06): the old name collided with the
# /reflect command (periodic memory audit) and misled users into
# thinking this plugin performed self-reflection. It only cues a short
# in-turn retrospective on user feedback / friction.
# ---------------------------------------------------------------------------


FEEDBACK_CHECK_PROMPT = (
    "--- Feedback Check ---\n"
    "Before this turn's work, glance back at the last few turns:\n"
    "- Reflect in 2-3 sentences if ANY of these happened (not only explicit\n"
    "  corrections): the user pointed out a mistake or redirected you; you\n"
    "  retried something, hit a dead-end, or were surprised by a result; or\n"
    "  an assumption you acted on turned out wrong. Cover:\n"
    "    * What happened / went wrong?\n"
    "    * Why did it happen?\n"
    "    * How will I avoid the same class of issue next time?\n"
    "  Then proceed with the turn.\n"
    "- Only skip if the last turns were genuinely clean and uneventful\n"
    "  (e.g. the first user turn, or a simple request with no friction).\n"
    "--- End Feedback Check ---"
)


# Single source for the offline-reference notice — consumed by both the
# OpenCode plugin below and the Claude hook in claude_bridge.py. Tells
# the air-gapped agent which offline tools replace web_search / context7.
OFFLINE_REFERENCE_NOTICE = (
    "--- Offline Environment ---\n"
    "This workstation is air-gapped: `web_search` and `context7` are "
    "unavailable. When you would look something up online, use the MCP "
    "tools instead:\n"
    "- `project_knowledge_search` — library/API signatures, tool flags, "
    "manuals, or how internal code works (the offline code+docs "
    "knowledge base, with the code<->doc mesh).\n"
    "- `memory_recall` — your own past decisions, gotchas, and notes.\n"
    "If a search returns nothing, say so and ask the user — do NOT "
    "fabricate an answer or imply you reached the web.\n"
    "--- End Offline Environment ---"
)


def _write_offline_reference_plugin(project_root: Path) -> None:
    """Write ``.opencode/plugins/offline-reference.ts`` if absent or owned.

    Project-level plugin modelled on ``feedback-check`` — stateless, fires
    every ``chat.message`` (so it survives compaction) and prepends the
    offline-environment notice telling the agent to reach for the
    ``project_knowledge_search`` / ``memory_recall`` MCP tools instead of
    the unavailable ``web_search`` / ``context7``.

    Sibling Claude Code hook is ``.claude/hooks/offline_reference.py``
    (see ``core.claude_bridge``); both inject the same notice.
    """
    from .markers import ALLMIGHT_MARKER_TS
    from .safe_write import write_guarded

    plugins_dir = project_root / ".opencode" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    write_guarded(
        plugins_dir / "offline-reference.ts",
        _offline_reference_plugin_content(),
        ALLMIGHT_MARKER_TS,
    )


def _offline_reference_plugin_content() -> str:
    from .plugin_telemetry import TS_HEARTBEAT_SNIPPET

    escaped = (
        OFFLINE_REFERENCE_NOTICE
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
    )
    return (
        _OFFLINE_REFERENCE_PLUGIN_TEMPLATE
        .replace("__OFFLINE_REFERENCE_NOTICE__", escaped)
        .replace("__TS_HEARTBEAT_SNIPPET__", TS_HEARTBEAT_SNIPPET)
    )


_OFFLINE_REFERENCE_PLUGIN_TEMPLATE = """\
// all-might generated
/**
 * Offline Reference — OpenCode plugin (All-Might)
 *
 * On every chat.message, prepends a short notice telling the agent the
 * environment is air-gapped (no web_search / context7) and to use the
 * project_knowledge_search / memory_recall MCP tools instead.
 *
 * Stateless and fires every turn (same rationale as feedback-check.ts):
 * the cue must stay present after compaction. The notice is short.
 *
 * Sibling Claude Code hook is .claude/hooks/offline_reference.py — both
 * surfaces inject the same notice; changes to one MUST land in the
 * other (see All-Might CLAUDE.md -> Editor Compatibility).
 *
 * Hook:
 *   chat.message -> inject the offline-environment notice every turn
 */
import type { Plugin } from "@opencode-ai/plugin";

__TS_HEARTBEAT_SNIPPET__
const OFFLINE_REFERENCE_NOTICE = `__OFFLINE_REFERENCE_NOTICE__`;

export const OfflineReferencePlugin: Plugin = async ({ directory }: any) => {
  const cwd = (directory as string | undefined) ?? process.cwd();

  return {
    "chat.message": async (input: any, output: any) => {
      emitHeartbeat("offline-reference", cwd);
      const sid = input?.sessionID;
      if (!sid) return;
      const mid = output?.message?.id;
      if (!mid) return;
      if (!Array.isArray(output?.parts)) return;
      output.parts.unshift({
        id: "prt_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10),
        sessionID: sid,
        messageID: mid,
        type: "text",
        text: OFFLINE_REFERENCE_NOTICE,
        synthetic: true,
      });
      emitHeartbeat("offline-reference.injected", cwd);
    },
  };
};

export default OfflineReferencePlugin;
"""


def _write_feedback_check_plugin(project_root: Path) -> None:
    """Write ``.opencode/plugins/feedback-check.ts`` if absent or owned.

    Project-level plugin (same status as role-load). At every
    ``chat.message`` it prepends a short instruction asking the agent
    to glance at the user's latest message and, if it points out a
    mistake, do a 2-3 sentence retrospective (what / why / how to
    avoid) before proceeding. Positive or neutral feedback skips the
    retrospective — the gating happens inside the agent's head, so
    the plugin itself is stateless and fires every turn.

    This is NOT the periodic self-reflection surface — that is the
    ``/reflect`` command (memory capability). The plugin was renamed
    from ``reflection`` to dissolve exactly that confusion; the stale
    ``reflection.ts`` is removed on re-init by ``prune_stale_plugins``.

    Sibling Claude Code hook is ``.claude/hooks/feedback_check.py``
    (see ``core.claude_bridge``); both surfaces inject the same prompt.
    """
    from .markers import ALLMIGHT_MARKER_TS
    from .safe_write import write_guarded

    plugins_dir = project_root / ".opencode" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    write_guarded(
        plugins_dir / "feedback-check.ts",
        _feedback_check_plugin_content(),
        ALLMIGHT_MARKER_TS,
    )


def _feedback_check_plugin_content() -> str:
    from .plugin_telemetry import TS_HEARTBEAT_SNIPPET
    # The prompt is interpolated into a TS backtick-string, so escape
    # backslashes, backticks, and ${ to keep the literal intact.
    escaped = (
        FEEDBACK_CHECK_PROMPT
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
    )
    return (
        _FEEDBACK_CHECK_PLUGIN_TEMPLATE
        .replace("__FEEDBACK_CHECK_PROMPT__", escaped)
        .replace("__TS_HEARTBEAT_SNIPPET__", TS_HEARTBEAT_SNIPPET)
    )


_FEEDBACK_CHECK_PLUGIN_TEMPLATE = """\
// all-might generated
/**
 * Feedback Check — OpenCode plugin (All-Might)
 *
 * On every chat.message, prepends a brief instruction asking the
 * agent to glance at the user's latest message and, if it points
 * out a mistake, do a 2-3 sentence retrospective (what went wrong /
 * why / how to avoid) before proceeding with the turn. Positive or
 * neutral feedback skips it.
 *
 * NOT the periodic self-reflection surface — that is the /reflect
 * command. This plugin only cues an in-turn check on user feedback.
 *
 * The plugin is stateless — the agent itself decides whether the
 * latest user message constitutes negative feedback. Firing every
 * turn (no per-session "primed" gate) keeps the cue present even
 * after compaction, and the prompt is small enough that the
 * repeated injection cost is negligible.
 *
 * Sibling Claude Code hook is .claude/hooks/feedback_check.py — both
 * surfaces inject the same prompt; changes to one MUST land in the
 * other (see All-Might CLAUDE.md -> Editor Compatibility).
 *
 * Hook:
 *   chat.message -> inject the feedback-check prefix every turn
 */
import type { Plugin } from "@opencode-ai/plugin";

__TS_HEARTBEAT_SNIPPET__
const FEEDBACK_CHECK_PROMPT = `__FEEDBACK_CHECK_PROMPT__`;

export const FeedbackCheckPlugin: Plugin = async ({ directory }: any) => {
  const cwd = (directory as string | undefined) ?? process.cwd();

  return {
    "chat.message": async (input: any, output: any) => {
      emitHeartbeat("feedback-check", cwd);
      const sid = input?.sessionID;
      if (!sid) return;
      // Each Part requires id / sessionID / messageID (see OpenCode's
      // TextPart schema in session/message-v2.ts); omitting them makes
      // SyncEvent.run reject the mutated part with "sessionID required".
      const mid = output?.message?.id;
      if (!mid) return;
      if (!Array.isArray(output?.parts)) return;
      output.parts.unshift({
        id: "prt_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10),
        sessionID: sid,
        messageID: mid,
        type: "text",
        text: FEEDBACK_CHECK_PROMPT,
        synthetic: true,
      });
      emitHeartbeat("feedback-check.injected", cwd);
    },
  };
};

export default FeedbackCheckPlugin;
"""


# ---------------------------------------------------------------------------
# Slug helper
# ---------------------------------------------------------------------------


def slugify_instance_name(name: str) -> str:
    """Normalise a user-supplied instance name into a filesystem slug.

    Spaces collapse to ``_``; characters outside ``[a-z0-9_-]`` drop;
    leading/trailing ``_-`` strip; result is lowercased. Empty input
    returns the empty string so callers can detect and re-prompt.
    """
    import re

    s = name.strip().lower().replace(" ", "_")
    s = re.sub(r"[^a-z0-9_-]+", "", s)
    s = s.strip("_-")
    return s


# ---------------------------------------------------------------------------
# Registry record (.allmight/personalities.yaml)
# ---------------------------------------------------------------------------


_REGISTRY_FILE = ".allmight/personalities.yaml"


@dataclass
class DerivedFrom:
    """One source descriptor in a personality's ``derived_from`` lineage.

    Personalities can be derived from prior bundles (output of
    ``/one-for-all``, installed via ``allmight share pull``) or from
    in-project
    personalities consumed during ``/all-for-one`` merges. A single
    personality may be derived from multiple sources of either kind,
    so the registry stores ``derived_from`` as a list of these
    descriptors.

    Field semantics by ``kind``:

    * ``kind == "bundle"``: ``bundle_id`` and ``bundle_version`` are
      populated; ``name`` is empty. ``bundle_id`` is the ``uuid4``
      generated by ``/one-for-all`` for that specific export.
    * ``kind == "personality"``: ``name`` is the in-project source's
      personality name; ``bundle_id`` and ``bundle_version`` are
      empty.
    """

    kind: str
    bundle_id: str = ""
    bundle_version: str = ""
    name: str = ""


@dataclass
class RegistryEntry:
    """A row in ``.allmight/personalities.yaml``.

    Two on-disk shapes are accepted by the reader:

    * **Part-C** (legacy, single capability per row)::

        - template: corpus_keeper
          instance: knowledge
          version: 1.0.0

    * **Part-D** (new, role bundle with capability list)::

        - name: stdcell_owner
          capabilities: [database, memory]
          versions: {database: 1.0.0, memory: 1.0.0}
          role_summary: Standard-cell library characterisation.
          derived_from:
            - kind: bundle
              bundle_id: <uuid>
              bundle_version: 0.1.0
            - kind: personality
              name: stdcell_owner
          derived_at: '2026-05-04T00:00:00Z'

    The dataclass exposes both vintages' fields. Part-C callers
    continue using ``template`` / ``instance`` / ``version``; Part-D
    callers use ``name`` / ``capabilities`` / ``versions``. The
    ``__post_init__`` synthesises whichever side wasn't supplied so
    every consumer sees a complete record regardless of vintage.
    """

    # Part-C primary fields (kept first for positional-construction
    # backward compatibility with existing call sites).
    template: str = ""
    instance: str = ""
    version: str = ""

    # Part-D additions.
    capabilities: list[str] = field(default_factory=list)
    versions: dict[str, str] = field(default_factory=dict)
    role_summary: str = ""

    # Lineage: list of source descriptors (bundles or in-project
    # personalities) this entry was derived from. Empty list means
    # "locally created, never derived". A single-bundle import
    # produces a one-entry list; a ``/all-for-one`` merge produces
    # one entry per source. Order matches the order sources were
    # listed during the merge.
    derived_from: list[DerivedFrom] = field(default_factory=list)
    derived_at: str = ""

    def __post_init__(self) -> None:
        # Synthesise Part-D fields from Part-C inputs. Lets old call
        # sites construct rows without knowing about the new shape.
        if not self.capabilities and self.template:
            self.capabilities = [self.template]
        if not self.versions and self.template and self.version:
            self.versions = {self.template: self.version}
        # And the reverse: keep Part-C accessors meaningful when only
        # Part-D fields were provided.
        if not self.template and self.capabilities:
            self.template = self.capabilities[0]
        if not self.instance and self.name:
            self.instance = self.name
        if not self.version and self.versions and self.template in self.versions:
            self.version = self.versions[self.template]

    @property
    def name(self) -> str:
        """Personality name (== ``instance`` for Part-C rows)."""
        return self.instance


def read_registry(project_root: Path) -> list[RegistryEntry]:
    """Read installed-personality records from ``.allmight/personalities.yaml``.

    Accepts both Part-C and Part-D row shapes — see :class:`RegistryEntry`.
    """
    import yaml

    path = project_root / _REGISTRY_FILE
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    rows = data.get("personalities", []) or []
    out: list[RegistryEntry] = []
    for row in rows:
        if "name" in row and "capabilities" in row:
            # Part-D row.
            derived_from: list[DerivedFrom] = []
            for src in row.get("derived_from") or []:
                if not isinstance(src, dict):
                    continue
                derived_from.append(DerivedFrom(
                    kind=str(src.get("kind", "")),
                    bundle_id=str(src.get("bundle_id", "") or ""),
                    bundle_version=str(src.get("bundle_version", "") or ""),
                    name=str(src.get("name", "") or ""),
                ))
            out.append(RegistryEntry(
                instance=row["name"],
                capabilities=list(row.get("capabilities") or []),
                versions=dict(row.get("versions") or {}),
                role_summary=row.get("role_summary", ""),
                derived_from=derived_from,
                derived_at=row.get("derived_at", ""),
            ))
        else:
            # Part-C row (or hand-edited mix). Required keys: template,
            # instance. Optional: version.
            out.append(RegistryEntry(
                template=row["template"],
                instance=row["instance"],
                version=row.get("version", ""),
            ))
    return out


def write_registry(project_root: Path, entries: list[RegistryEntry]) -> None:
    """Persist the registry in the Part-D shape, replacing prior content.

    Each entry is written as a Part-D row (``name`` + ``capabilities``
    + ``versions``); Part-C-shaped entries get up-converted via the
    synthesis in :class:`RegistryEntry.__post_init__`. The on-disk
    file is therefore always Part-D after a write.
    """
    import yaml

    path = project_root / _REGISTRY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "personalities": [
            _entry_to_row(e) for e in entries
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


def _entry_to_row(entry: RegistryEntry) -> dict[str, Any]:
    """Render a registry entry as a Part-D YAML row."""
    row: dict[str, Any] = {
        "name": entry.instance,
        "capabilities": list(entry.capabilities),
        "versions": dict(entry.versions),
    }
    if entry.role_summary:
        row["role_summary"] = entry.role_summary
    # Lineage is only emitted when sources exist, so locally-created
    # personalities don't accumulate empty bookkeeping keys.
    if entry.derived_from:
        row["derived_from"] = [
            _derived_from_to_dict(src) for src in entry.derived_from
        ]
    if entry.derived_at:
        row["derived_at"] = entry.derived_at
    return row


def _derived_from_to_dict(src: DerivedFrom) -> dict[str, Any]:
    """Render a ``DerivedFrom`` as a YAML-friendly dict.

    Only fields relevant to ``kind`` are emitted, keeping the on-disk
    shape minimal and unambiguous.
    """
    out: dict[str, Any] = {"kind": src.kind}
    if src.kind == "bundle":
        if src.bundle_id:
            out["bundle_id"] = src.bundle_id
        if src.bundle_version:
            out["bundle_version"] = src.bundle_version
    elif src.kind == "personality":
        if src.name:
            out["name"] = src.name
    return out


# ---------------------------------------------------------------------------
# Owned-path collision detection
# ---------------------------------------------------------------------------


def check_owned_path_collisions(templates: list[PersonalityTemplate]) -> None:
    """Raise if two templates declare the same ``owned_paths`` glob.

    Owned paths are formatted with ``{instance}`` left as a placeholder;
    we compare the raw glob so two templates that both claim e.g.
    ``personalities/{instance}/skills/**`` are fine (each instance gets
    its own directory), but two that both claim ``MEMORY.md`` clash.
    """
    seen: dict[str, str] = {}
    for tmpl in templates:
        for glob in tmpl.owned_paths:
            if "{instance}" in glob:
                # Per-instance paths are namespaced by instance name —
                # collision is only possible if two templates pick the
                # same instance name, which the registry already
                # prevents.
                continue
            if glob in seen and seen[glob] != tmpl.name:
                raise ValueError(
                    f"owned_paths collision: '{glob}' claimed by both "
                    f"{seen[glob]!r} and {tmpl.name!r}"
                )
            seen[glob] = tmpl.name
