"""Rewrite a pre-Part-C project to the new layout.

Detection is conservative — only legacy markers trigger migration:

* Instance dirs ending in ``-corpus`` / ``-memory`` (the old
  project-prefixed name pattern).
* ``.opencode/commands/reflect.md`` present (the dropped command).
* Root ``AGENTS.md`` containing both ``<!-- ALL-MIGHT -->`` and
  ``<!-- ALL-MIGHT-MEMORY -->`` marker fences (the old single-file
  shape).

If none of those match, the project is already on the new layout and
``migrate`` returns a no-op report. The migrator is idempotent on
already-migrated projects.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..core.markers import ALLMIGHT_MARKER_MD
from ..core.personalities import (
    Personality,
    RegistryEntry,
    compose,
    compose_agents_md,
    discover,
    read_registry,
    write_init_scaffold,
    write_registry,
)


_LEGACY_CORPUS_SUFFIX = "-corpus"
_LEGACY_MEMORY_SUFFIX = "-memory"
_OLD_CORPUS_FENCE = "<!-- ALL-MIGHT -->"
_OLD_MEMORY_FENCE = "<!-- ALL-MIGHT-MEMORY -->"


@dataclass
class MigrationPlan:
    """What the migrator will do (or did) to a project."""

    needs_migration: bool = False
    rename: dict[str, str] = field(default_factory=dict)
    dropped_files: list[str] = field(default_factory=list)
    written_role_files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def detect(project_root: Path) -> MigrationPlan:
    """Inspect ``project_root`` and report what migration would do.

    Pure read-only — never touches disk.
    """
    plan = MigrationPlan()
    personalities_dir = project_root / "personalities"

    if personalities_dir.is_dir():
        for child in sorted(personalities_dir.iterdir()):
            if not child.is_dir():
                continue
            new_name = _new_instance_name(child.name)
            if new_name is not None and new_name != child.name:
                plan.rename[child.name] = new_name

    reflect_md = project_root / ".opencode" / "commands" / "reflect.md"
    if reflect_md.exists() or reflect_md.is_symlink():
        plan.dropped_files.append(".opencode/commands/reflect.md")

    agents_md = project_root / "AGENTS.md"
    if agents_md.is_file():
        text = agents_md.read_text()
        if _OLD_CORPUS_FENCE in text or _OLD_MEMORY_FENCE in text:
            plan.notes.append(
                "Root AGENTS.md uses legacy marker fences; will be "
                "split into per-personality ROLE.md files."
            )

    plan.needs_migration = bool(
        plan.rename or plan.dropped_files or plan.notes
    )
    return plan


def migrate(project_root: Path, *, dry_run: bool = False) -> MigrationPlan:
    """Apply the migration. ``dry_run=True`` returns the plan only."""
    plan = detect(project_root)
    if not plan.needs_migration or dry_run:
        return plan

    # 1. Rename legacy instance dirs.
    personalities_dir = project_root / "personalities"
    for old, new in plan.rename.items():
        src = personalities_dir / old
        dst = personalities_dir / new
        if dst.exists():
            plan.notes.append(
                f"Refused to rename {old} -> {new}: destination exists. "
                "Resolve manually."
            )
            continue
        shutil.move(str(src), str(dst))

    # 2. Drop legacy /reflect command (file or symlink).
    reflect_md = project_root / ".opencode" / "commands" / "reflect.md"
    if reflect_md.is_symlink() or reflect_md.exists():
        try:
            reflect_md.unlink()
        except OSError:
            pass

    # 3. Split legacy AGENTS.md into per-personality ROLE.md files.
    agents_md = project_root / "AGENTS.md"
    if agents_md.is_file():
        text = agents_md.read_text()
        sections = _split_legacy_agents_md(text)
        for kind, body in sections.items():
            instance = _instance_for_kind(plan, kind)
            if instance is None:
                continue
            role_path = personalities_dir / instance / "ROLE.md"
            role_path.parent.mkdir(parents=True, exist_ok=True)
            # Convert section heading "## All-Might: ..." into the
            # ROLE.md "# Corpus/Memory Keeper" header that the new
            # template writers use.
            normalised = _normalise_role_body(kind, body)
            role_path.write_text(f"{ALLMIGHT_MARKER_MD}\n{normalised}")
            plan.written_role_files.append(
                str(role_path.relative_to(project_root))
            )

    # 4. Refresh .allmight/personalities.yaml with the new names.
    entries = read_registry(project_root)
    if entries:
        new_entries = []
        for entry in entries:
            new_instance = plan.rename.get(entry.instance, entry.instance)
            new_template = _LEGACY_TEMPLATE_NAMES.get(entry.template, entry.template)
            new_entries.append(RegistryEntry(
                template=new_template,
                instance=new_instance,
                version=entry.version,
            ))
        write_registry(project_root, new_entries)
    else:
        # First run on a project that pre-dates the registry — synthesize
        # entries from the new dir names.
        templates = {t.name: t for t in discover()}
        synthesized: list[RegistryEntry] = []
        for child in sorted(personalities_dir.iterdir()):
            if not child.is_dir():
                continue
            template = _guess_template(child.name, templates)
            if template is None:
                continue
            synthesized.append(RegistryEntry(
                template=template.name,
                instance=child.name,
                version=template.version,
            ))
        if synthesized:
            write_registry(project_root, synthesized)

    # 5. Re-run scaffold + composition so .opencode/ points at the
    #    renamed dirs and the role-load.ts plugin lands.
    write_init_scaffold(project_root)
    templates_by_name = {t.name: t for t in discover()}
    instances = []
    for entry in read_registry(project_root):
        template = templates_by_name.get(entry.template)
        if template is None:
            continue
        instances.append(Personality(
            template=template, project_root=project_root, name=entry.instance,
        ))
    for instance in instances:
        compose(project_root, instance, force=False)
    if instances:
        compose_agents_md(project_root, instances, project_name=project_root.name)

    return plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_instance_name(legacy: str) -> str | None:
    """Map a legacy ``<project>-corpus`` / ``-memory`` name to the new default.

    Returns ``None`` for names that don't fit the legacy pattern, so
    user-customised names survive migration unchanged.
    """
    if legacy.endswith(_LEGACY_CORPUS_SUFFIX):
        return "knowledge"
    if legacy.endswith(_LEGACY_MEMORY_SUFFIX):
        return "memory"
    return None


def _instance_for_kind(plan: MigrationPlan, kind: str) -> str | None:
    """Pick the post-migration instance dir name for a given kind.

    ``kind`` is ``"corpus"`` or ``"memory"`` — we choose the renamed
    default if a rename happened, otherwise fall back to the static
    new defaults.
    """
    for old, new in plan.rename.items():
        if old.endswith(f"-{kind}"):
            return new
    return {"corpus": "knowledge", "memory": "memory"}[kind]


def _guess_template(instance_name: str, templates: dict):
    """Heuristic: instance name == "knowledge" -> database, "memory" -> memory."""
    if instance_name == "knowledge":
        return templates.get("database")
    if instance_name == "memory":
        return templates.get("memory")
    return None


# Map legacy Part-A/B/C template names to the Part-D names so a registry
# carrying ``template: corpus_keeper`` still resolves to the renamed
# ``database`` template after Part-D is in place.
_LEGACY_TEMPLATE_NAMES: dict[str, str] = {
    "corpus_keeper": "database",
    "memory_keeper": "memory",
}


def _split_legacy_agents_md(text: str) -> dict[str, str]:
    """Split a legacy single-file AGENTS.md by marker fences.

    Returns ``{"corpus": <body>, "memory": <body>}`` for whichever
    fences were present. Each body is the content after the fence
    line up to (but not including) the next fence.
    """
    sections: dict[str, str] = {}
    if _OLD_CORPUS_FENCE in text:
        sections["corpus"] = _slice_after(text, _OLD_CORPUS_FENCE, _OLD_MEMORY_FENCE)
    if _OLD_MEMORY_FENCE in text:
        sections["memory"] = _slice_after(text, _OLD_MEMORY_FENCE, _OLD_CORPUS_FENCE)
    return sections


def _slice_after(text: str, start: str, *stops: str) -> str:
    """Return text after ``start`` line up to the first ``stop`` line.

    The stop-fence is not included; trailing whitespace is stripped.
    """
    idx = text.find(start)
    if idx < 0:
        return ""
    after = text[idx + len(start):]
    cut = len(after)
    for stop in stops:
        s = after.find(stop)
        if s >= 0 and s < cut:
            cut = s
    return after[:cut].strip()


def _normalise_role_body(kind: str, legacy_body: str) -> str:
    """Re-shape a legacy section body to the new ROLE.md header style.

    The legacy section started with ``## All-Might: ...``; the new
    file is ``# <Personality> Keeper``. We replace the H2 heading
    with an appropriate H1 and keep the rest intact.
    """
    header = "# Corpus Keeper" if kind == "corpus" else "# Memory Keeper"
    lines = legacy_body.splitlines()
    # Drop a leading "## All-Might: ..." or "## Agent Memory" if present.
    if lines and lines[0].startswith("## "):
        lines = lines[1:]
        # Drop the trailing blank line that often follows the heading.
        while lines and not lines[0].strip():
            lines = lines[1:]
    return f"{header}\n\n" + "\n".join(lines).rstrip() + "\n"
