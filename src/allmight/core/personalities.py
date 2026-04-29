"""Personality framework — pluggable capabilities for an All-Might project.

A *personality* is a reusable capability bundle (e.g. corpus_keeper for
knowledge-graph workspaces, memory_keeper for L1/L2/L3 agent memory).
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
  shallow scan of ``allmight.personalities.*`` for a ``TEMPLATE``
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
    """The KIND of a personality (e.g. corpus_keeper, memory_keeper).

    Plain dataclass holding metadata plus the two operation callables.
    Built-in templates live as module-level ``TEMPLATE`` constants
    inside ``allmight.personalities.<name>``.
    """

    name: str
    short_name: str
    version: str
    description: str
    owned_paths: list[str]
    cli_options: list[CliOption]
    install: Callable[["InstallContext", "Personality"], InstallResult]
    status: Callable[[Path, "Personality"], PersonalityStatus]


@dataclass
class Personality:
    """An INSTANCE of a template attached to one project."""

    template: PersonalityTemplate
    project_root: Path
    name: str
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def root(self) -> Path:
        """Directory the instance owns: ``personalities/<name>/``."""
        return self.project_root / "personalities" / self.name


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover(package: str = "allmight.personalities") -> list[PersonalityTemplate]:
    """Scan ``package`` for subpackages exposing a ``TEMPLATE`` attribute.

    Discovery order is the iteration order of ``pkgutil.iter_modules``,
    which is alphabetical on POSIX. Order matters because
    ``corpus_keeper`` writes ``AGENTS.md`` before ``memory_keeper``
    appends its memory section. The two built-in templates already
    sort that way (``corpus_keeper`` < ``memory_keeper``); if a third
    template is added that needs a specific slot, give it a name that
    sorts correctly or extend this function with explicit ordering.

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


def compose(project_root: Path, instance: Personality, *, force: bool = False) -> None:
    """Symlink an instance's skills/commands/plugins into ``.opencode/``.

    For each kind, every entry under ``personalities/<instance>/<kind>/``
    is mirrored at ``.opencode/<kind>/<basename>`` as a relative
    symlink pointing back to the instance.

    Naming collisions across instances (two instances both contributing
    e.g. ``commands/sync.md``) raise :class:`FileExistsError` unless
    ``force`` is set. ``force`` only overwrites existing **symlinks**;
    a non-symlink file at the destination always raises so we never
    silently clobber user work.
    """
    for kind in _COMPOSED_KINDS:
        src_dir = instance.root / kind
        if not src_dir.is_dir():
            continue
        dst_dir = project_root / ".opencode" / kind
        dst_dir.mkdir(parents=True, exist_ok=True)
        for entry in sorted(src_dir.iterdir()):
            dst = dst_dir / entry.name
            if dst.is_symlink():
                if not force and dst.resolve() != entry.resolve():
                    raise FileExistsError(
                        f"{dst} symlinked elsewhere; refuse to overwrite without force"
                    )
                dst.unlink()
            elif dst.exists():
                raise FileExistsError(
                    f"{dst} exists and is not a symlink; refuse to clobber"
                )
            dst.symlink_to(os.path.relpath(entry, dst_dir))


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
    cfg["$schema"] = "https://opencode.ai/config.json"
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


# ---------------------------------------------------------------------------
# Registry record (.allmight/personalities.yaml)
# ---------------------------------------------------------------------------


_REGISTRY_FILE = ".allmight/personalities.yaml"


@dataclass
class RegistryEntry:
    template: str
    instance: str
    version: str


def read_registry(project_root: Path) -> list[RegistryEntry]:
    """Read installed-personality records from ``.allmight/personalities.yaml``."""
    import yaml

    path = project_root / _REGISTRY_FILE
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    rows = data.get("personalities", []) or []
    out: list[RegistryEntry] = []
    for row in rows:
        out.append(
            RegistryEntry(
                template=row["template"],
                instance=row["instance"],
                version=row.get("version", ""),
            )
        )
    return out


def write_registry(project_root: Path, entries: list[RegistryEntry]) -> None:
    """Persist the registry, replacing any prior content."""
    import yaml

    path = project_root / _REGISTRY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "personalities": [
            {
                "template": e.template,
                "instance": e.instance,
                "version": e.version,
            }
            for e in entries
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


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
