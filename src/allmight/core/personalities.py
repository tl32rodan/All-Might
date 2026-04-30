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
  (``knowledge_graph/`` or ``memory/``).

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
    """Cross-cutting state passed to every ``install`` call."""

    project_root: Path
    manifest: ProjectManifest
    staging: bool = False
    force: bool = False


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
# Composition (.opencode/<kind>/* symlinks)
# ---------------------------------------------------------------------------


_COMPOSED_KINDS = ("skills", "commands", "plugins")


@dataclass
class ComposeConflict:
    """A composition target we refused to overwrite.

    Raised by ``compose()`` when ``.opencode/<kind>/<name>`` is occupied
    by content that doesn't carry an All-Might marker — i.e. the user
    (or some other tool) authored the file. The agent resolves the
    conflict during ``/sync``.

    Attributes:
        instance_name: Name of the personality instance that wanted to
            contribute this entry.
        kind: One of ``skills``, ``commands``, ``plugins``.
        basename: Final path component (e.g. ``search.md``).
        dst: Absolute path of the conflicted destination
            (``.opencode/<kind>/<basename>``).
        source: Absolute path of the entry we would have linked to
            (``personalities/<instance>/<kind>/<basename>``).
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
    """Symlink an instance's skills/commands/plugins into ``.opencode/``.

    For each kind, every entry under ``personalities/<instance>/<kind>/``
    is mirrored at ``.opencode/<kind>/<basename>`` as a relative
    symlink pointing back to the instance.

    Conflict handling — never raises, returns conflicts instead:

    * **Already correct** (symlink to our entry): idempotent, do nothing.
    * **Symlink to elsewhere**: returned as a conflict; ``dst`` is left
      untouched. ``force=True`` overrides and replaces it.
    * **Regular file with an All-Might marker**: it's our own old
      generated file — auto-resolve by deleting and re-symlinking.
    * **Regular file without a marker**: user authored, returned as a
      conflict; ``dst`` is preserved. ``force=True`` overrides.
    * **Directory**: returned as a conflict (we never recursively
      delete user content). ``force=True`` overrides only when the dir
      is itself a stale All-Might-owned dir (any file with a marker).

    The CLI passes the returned list to
    :func:`stage_compose_conflicts` so ``/sync`` can resolve them.
    """
    from .markers import ALLMIGHT_MARKER_MD, ALLMIGHT_MARKER_TS, ALLMIGHT_MARKER_YAML

    markers = (ALLMIGHT_MARKER_MD, ALLMIGHT_MARKER_TS, ALLMIGHT_MARKER_YAML)

    def _looks_owned(path: Path) -> bool:
        """True when ``path`` contains any All-Might marker token.

        Used to distinguish *our* old generated content (safe to
        overwrite) from *user* content (must be staged for ``/sync``).
        Reads at most a few KB so we don't slurp huge files.
        """
        try:
            head = path.read_bytes()[:4096].decode("utf-8", errors="replace")
        except OSError:
            return False
        return any(m in head for m in markers)

    def _dir_looks_owned(path: Path) -> bool:
        """True when any file inside ``path`` carries our marker."""
        for child in path.rglob("*"):
            if child.is_file() and _looks_owned(child):
                return True
        return False

    conflicts: list[ComposeConflict] = []

    for kind in _COMPOSED_KINDS:
        src_dir = instance.root / kind
        if not src_dir.is_dir():
            continue
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
                    if force or _looks_owned(dst):
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
    payload = {
        "compose_conflicts": [
            {
                "instance": c.instance_name,
                "kind": c.kind,
                "basename": c.basename,
                "dst": str(c.dst.relative_to(project_root)),
                "source": str(c.source.relative_to(project_root)),
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


# ---------------------------------------------------------------------------
# ROLE.md composition + role-load.ts plugin
# ---------------------------------------------------------------------------


_AGENTS_MD_HEADER = (
    "<!-- all-might generated -->\n"
    "<!--\n"
    "  This file is composed from each personality's ROLE.md.\n"
    "  Edit personalities/<name>/ROLE.md, not this file.\n"
    "-->\n\n"
    "# {project_name}\n\n"
)


def compose_agents_md(
    project_root: Path,
    instances: list["Personality"],
    *,
    project_name: str | None = None,
) -> Path:
    """Stitch each instance's ROLE.md into the single root AGENTS.md.

    Order is the order ``instances`` is passed (registry order: corpus
    before memory). Instances missing a ROLE.md are skipped.

    The composed file carries the All-Might marker so re-init can tell
    its own composed output from a user-edited AGENTS.md and stage a
    conflict for ``/sync`` if the user has hand-edited the root.
    """
    name = project_name or project_root.name
    parts = [_AGENTS_MD_HEADER.format(project_name=name)]
    for instance in instances:
        role_md = instance.root / "ROLE.md"
        if not role_md.is_file():
            continue
        body = role_md.read_text().rstrip()
        # Strip the leading marker line — it's already on the composed
        # file, no need to repeat it inside each section.
        from .markers import ALLMIGHT_MARKER_MD

        if body.startswith(ALLMIGHT_MARKER_MD):
            body = body[len(ALLMIGHT_MARKER_MD):].lstrip("\n")
        parts.append(body)
        parts.append("")  # blank line between sections
    agents_md = project_root / "AGENTS.md"
    agents_md.write_text("\n".join(parts).rstrip() + "\n")
    return agents_md


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
        _ROLE_LOAD_PLUGIN_CONTENT,
        ALLMIGHT_MARKER_TS,
    )


_ROLE_LOAD_PLUGIN_CONTENT = """\
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
    },
  };
};

export default RoleLoadPlugin;
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
            out.append(RegistryEntry(
                instance=row["name"],
                capabilities=list(row.get("capabilities") or []),
                versions=dict(row.get("versions") or {}),
                role_summary=row.get("role_summary", ""),
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
    return row


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
