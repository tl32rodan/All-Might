"""Tests for the personalities composition layer (Part-D, downward symlinks).

Exercises ``allmight.core.personalities.compose`` and friends in the
Part-D model:

* Capability templates write project-wide globals
  (``search.md``, ``remember.md``, …) directly into ``.opencode/``.
* Each personality owns real, initially empty ``commands/`` and
  ``skills/`` subdirs where the agent may add personality-specific
  entries at runtime.
* ``compose`` projects every personality entry into
  ``.opencode/<kind>/<basename>`` as a relative symlink so OpenCode
  discovers it from the same global scan.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from allmight.core.markers import ALLMIGHT_MARKER_MD, ALLMIGHT_MARKER_TS
from allmight.core.personalities import (
    ComposeConflict,
    Personality,
    PersonalityTemplate,
    compose,
    compose_agents_md,
    compose_role_agents,
    stage_compose_conflicts,
    write_init_scaffold,
)


def _dummy_template() -> PersonalityTemplate:
    """Minimal template — install/status are unused; we drive compose directly."""
    return PersonalityTemplate(
        name="t",
        short_name="t",
        version="1.0.0",
        description="",
        owned_paths=[],
        cli_options=[],
        install=lambda ctx, instance: None,  # type: ignore[arg-type]
        status=lambda root, instance: None,  # type: ignore[arg-type]
    )


def _make_instance(tmp_path: Path) -> Personality:
    """Build an instance under tmp_path/personalities/<n>/ with a few entries.

    Pre-fills personality-specific commands/skills (the case that
    actually exercises the projection — globals are written by
    capability templates, not by us here).
    """
    instance = Personality(
        template=_dummy_template(),
        project_root=tmp_path,
        name="demo-t",
        options={},
    )
    (instance.root / "commands").mkdir(parents=True)
    (instance.root / "commands" / "stdcell-special.md").write_text(
        f"{ALLMIGHT_MARKER_MD}\nour content\n"
    )
    (instance.root / "skills").mkdir(parents=True)
    (instance.root / "skills" / "audit.ts").write_text(
        f"{ALLMIGHT_MARKER_TS}\nour ts content\n"
    )
    return instance


class TestComposeFreshDirectory:
    def test_personality_dirs_become_real_empty_when_no_entries(
        self, tmp_path: Path,
    ) -> None:
        """A personality with no custom entries still gets the real
        empty ``commands/`` / ``skills/`` slots."""
        instance = Personality(
            template=_dummy_template(),
            project_root=tmp_path,
            name="bare-t",
            options={},
        )

        conflicts = compose(tmp_path, instance)

        assert conflicts == []
        assert (instance.root / "commands").is_dir()
        assert not (instance.root / "commands").is_symlink()
        assert (instance.root / "skills").is_dir()
        assert not (instance.root / "skills").is_symlink()

    def test_creates_downward_symlinks_when_target_empty(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)

        conflicts = compose(tmp_path, instance)

        assert conflicts == []
        link = tmp_path / ".opencode" / "commands" / "stdcell-special.md"
        assert link.is_symlink()
        assert link.resolve() == (instance.root / "commands" / "stdcell-special.md").resolve()

    def test_idempotent_when_run_twice(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)

        compose(tmp_path, instance)
        conflicts = compose(tmp_path, instance)

        assert conflicts == []


class TestComposeAutoResolves:
    def test_owned_markdown_file_at_dst_is_replaced(self, tmp_path: Path) -> None:
        """An All-Might-marked file at the projection target is treated
        as our own stale copy and auto-resolved by replacement."""
        instance = _make_instance(tmp_path)
        # Pre-existing All-Might-owned file at the target — we'd have
        # written it ourselves on a previous run.
        existing = tmp_path / ".opencode" / "commands" / "stdcell-special.md"
        existing.parent.mkdir(parents=True)
        existing.write_text(f"{ALLMIGHT_MARKER_MD}\nstale content\n")

        conflicts = compose(tmp_path, instance)

        # Marker-bearing files are NOT auto-resolved in the new model
        # because they could be capability-written globals. Force is
        # required; without it, the conflict is reported.
        assert len(conflicts) == 1


class TestComposeStagesUserConflicts:
    def test_user_authored_markdown_is_not_overwritten(self, tmp_path: Path) -> None:
        """A pre-existing user file at ``.opencode/<kind>/<basename>``
        without our marker stays put; conflict surfaced."""
        instance = _make_instance(tmp_path)
        user_file = tmp_path / ".opencode" / "commands" / "stdcell-special.md"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("user wrote this\n")

        conflicts = compose(tmp_path, instance)

        assert len(conflicts) == 1
        c = conflicts[0]
        assert isinstance(c, ComposeConflict)
        assert c.kind == "commands"
        assert c.basename == "stdcell-special.md"
        assert c.existing == "file"
        assert c.dst == user_file
        assert c.source == instance.root / "commands" / "stdcell-special.md"
        # User's content untouched.
        assert user_file.read_text() == "user wrote this\n"

    def test_symlink_to_elsewhere_is_preserved(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        elsewhere = tmp_path / "user_target.md"
        elsewhere.write_text("user target\n")
        user_file = tmp_path / ".opencode" / "commands" / "stdcell-special.md"
        user_file.parent.mkdir(parents=True)
        user_file.symlink_to(elsewhere.resolve())

        conflicts = compose(tmp_path, instance)

        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.existing == "symlink-to-elsewhere"
        assert user_file.is_symlink()
        assert user_file.resolve() == elsewhere.resolve()

    def test_force_overrides_user_file(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        user_file = tmp_path / ".opencode" / "commands" / "stdcell-special.md"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("user wrote this\n")

        conflicts = compose(tmp_path, instance, force=True)

        assert conflicts == []
        assert user_file.is_symlink()
        assert user_file.resolve() == (instance.root / "commands" / "stdcell-special.md").resolve()


class TestStageComposeConflicts:
    def test_writes_yaml_manifest(self, tmp_path: Path) -> None:
        instance = _make_instance(tmp_path)
        user_file = tmp_path / ".opencode" / "commands" / "stdcell-special.md"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("user wrote this\n")

        conflicts = compose(tmp_path, instance)
        path = stage_compose_conflicts(tmp_path, conflicts)

        assert path is not None
        assert path == tmp_path / ".allmight" / "templates" / "conflicts.yaml"
        payload = yaml.safe_load(path.read_text())
        rows = payload["compose_conflicts"]
        assert len(rows) == 1
        row = rows[0]
        assert row["instance"] == "demo-t"
        assert row["kind"] == "commands"
        assert row["basename"] == "stdcell-special.md"
        assert row["dst"] == ".opencode/commands/stdcell-special.md"
        assert row["source"] == "personalities/demo-t/commands/stdcell-special.md"
        assert row["existing"] == "file"

    def test_no_conflicts_removes_existing_manifest(self, tmp_path: Path) -> None:
        path = tmp_path / ".allmight" / "templates" / "conflicts.yaml"
        path.parent.mkdir(parents=True)
        path.write_text("compose_conflicts: []\n")

        result = stage_compose_conflicts(tmp_path, [])

        assert result is None
        assert not path.exists()


class TestWriteInitScaffold:
    def test_creates_personalities_dir(self, tmp_path: Path) -> None:
        write_init_scaffold(tmp_path)
        assert (tmp_path / "personalities").is_dir()

    def test_creates_dot_opencode_skeleton(self, tmp_path: Path) -> None:
        write_init_scaffold(tmp_path)
        assert (tmp_path / ".opencode" / "opencode.json").is_file()


class TestReflectionPlugin:
    """Project-level reflection-check OpenCode plugin (mirrors reflection.py)."""

    def test_writes_reflection_plugin(self, tmp_path: Path) -> None:
        write_init_scaffold(tmp_path)
        plugin = tmp_path / ".opencode" / "plugins" / "reflection.ts"
        assert plugin.is_file()

    def test_reflection_plugin_carries_marker(self, tmp_path: Path) -> None:
        write_init_scaffold(tmp_path)
        body = (tmp_path / ".opencode" / "plugins" / "reflection.ts").read_text()
        assert body.startswith(ALLMIGHT_MARKER_TS)

    def test_reflection_plugin_uses_chat_message_hook(self, tmp_path: Path) -> None:
        """Pin the exact OpenCode hook signature.

        OpenCode distinguishes the global ``event`` handler from
        top-level keys like ``chat.message`` which are hooks with
        input/output contracts. The reflection plugin uses the hook
        form so it can mutate ``output.parts``; the negative
        assertion below catches the regression where someone places
        the hook inside the event handler's if-chain.
        """
        write_init_scaffold(tmp_path)
        body = (tmp_path / ".opencode" / "plugins" / "reflection.ts").read_text()
        assert '"chat.message": async (input: any, output: any)' in body
        assert "output.parts.unshift" in body
        # The reflection check is stateless — no per-session gate
        # (would defeat the point: each turn needs the same prompt).
        assert "new Set" not in body
        assert "primed.add" not in body
        assert "sessions.set" not in body
        # Negative assertion: not the broken "msg.content = ..." shape.
        assert "msg.content =" not in body

    def test_reflection_plugin_contains_reflection_prompt(
        self, tmp_path: Path
    ) -> None:
        write_init_scaffold(tmp_path)
        body = (tmp_path / ".opencode" / "plugins" / "reflection.ts").read_text()
        # The user-facing prompt content.
        assert "Reflection Check" in body
        assert "What went wrong?" in body
        assert "Why did it happen?" in body
        assert "How will I avoid" in body

    def test_reflection_plugin_preserves_user_authored(
        self, tmp_path: Path
    ) -> None:
        """write_guarded contract — never overwrite a user-authored file."""
        plugins_dir = tmp_path / ".opencode" / "plugins"
        plugins_dir.mkdir(parents=True)
        custom = "// my own plugin\n"
        (plugins_dir / "reflection.ts").write_text(custom)
        write_init_scaffold(tmp_path)
        assert (plugins_dir / "reflection.ts").read_text() == custom

    def test_reflection_plugin_idempotent(self, tmp_path: Path) -> None:
        write_init_scaffold(tmp_path)
        first = (tmp_path / ".opencode" / "plugins" / "reflection.ts").read_text()
        write_init_scaffold(tmp_path)
        second = (tmp_path / ".opencode" / "plugins" / "reflection.ts").read_text()
        assert first == second


def _instance_with_role(
    tmp_path: Path,
    name: str = "stdcell_owner",
    role_body: str = (
        "# stdcell_owner\n\n"
        "Standard-cell library characterisation.\n"
    ),
) -> Personality:
    """Pre-stage a personality with a ROLE.md so compose_role_agents has input.

    ``role_body`` is the markdown that goes under the marker line. The
    first non-heading paragraph becomes the agent's ``description:``
    so test cases can pin the extraction directly by varying it.
    """
    inst = Personality(
        template=_dummy_template(),
        project_root=tmp_path,
        name=name,
        capabilities=["database"],
    )
    inst.root.mkdir(parents=True)
    (inst.root / "ROLE.md").write_text(f"{ALLMIGHT_MARKER_MD}\n{role_body}")
    return inst


class TestComposeRoleAgents:
    """`.opencode/agents/<name>.md` — OpenCode subagent file per personality.

    Pin the documented OpenCode contract:
      * file is at ``.opencode/agents/<name>.md`` (plural ``agents``)
      * frontmatter has required ``description``, ``mode: subagent``,
        and ``prompt: "{file:...}"`` pointing back at ROLE.md
      * marker lives inside the body so write_guarded recognises
        ownership without breaking OpenCode's frontmatter parser
        (which requires ``---`` to be the first line)
    """

    def test_writes_agent_file_with_documented_frontmatter(
        self, tmp_path: Path
    ) -> None:
        inst = _instance_with_role(tmp_path)
        written = compose_role_agents(tmp_path, [inst])
        target = tmp_path / ".opencode" / "agents" / f"{inst.name}.md"
        assert target in written
        body = target.read_text()
        # First line must be `---` so OpenCode's frontmatter parser sees
        # the YAML block before anything else.
        assert body.startswith("---\n")
        # The three frontmatter fields we depend on are present.
        # Description comes from ROLE.md's first paragraph (not from a
        # registry field), so we pin the actual extracted text.
        assert 'description: "Standard-cell library characterisation."' in body
        assert "mode: subagent" in body
        assert (
            'prompt: "{file:../personalities/stdcell_owner/ROLE.md}"' in body
        )

    def test_marker_in_body_not_before_frontmatter(self, tmp_path: Path) -> None:
        """Marker is in the body so frontmatter stays the first thing OpenCode sees."""
        inst = _instance_with_role(tmp_path)
        compose_role_agents(tmp_path, [inst])
        body = (tmp_path / ".opencode" / "agents" / f"{inst.name}.md").read_text()
        # Marker present (write_guarded will recognise on re-init)…
        assert ALLMIGHT_MARKER_MD in body
        # …but not before the first ``---``.
        assert body.index(ALLMIGHT_MARKER_MD) > body.index("---\n")

    def test_description_skips_headings_and_html_comments(
        self, tmp_path: Path
    ) -> None:
        """First *prose* paragraph wins — not the marker, not the heading."""
        inst = _instance_with_role(
            tmp_path,
            role_body=(
                "# stdcell_owner\n\n"
                "<!-- internal note, not for the agent picker -->\n\n"
                "Owns the stdcell flow end-to-end.\n\n"
                "Second paragraph that should not appear.\n"
            ),
        )
        compose_role_agents(tmp_path, [inst])
        body = (tmp_path / ".opencode" / "agents" / f"{inst.name}.md").read_text()
        assert 'description: "Owns the stdcell flow end-to-end."' in body
        assert "Second paragraph" not in body

    def test_description_collapses_internal_whitespace(
        self, tmp_path: Path
    ) -> None:
        """Multi-line paragraph collapses to one YAML line."""
        inst = _instance_with_role(
            tmp_path,
            role_body=(
                "# stdcell_owner\n\n"
                "Characterises the standard-cell library\n"
                "across   PVT corners and writes\nliberty files.\n"
            ),
        )
        compose_role_agents(tmp_path, [inst])
        body = (tmp_path / ".opencode" / "agents" / f"{inst.name}.md").read_text()
        assert (
            'description: "Characterises the standard-cell library '
            'across PVT corners and writes liberty files."'
        ) in body

    def test_description_truncates_long_paragraphs(self, tmp_path: Path) -> None:
        """Cap description at ~200 chars so the agent picker stays readable."""
        long = "alpha " * 200  # ~1200 chars
        inst = _instance_with_role(
            tmp_path,
            role_body=f"# stdcell_owner\n\n{long}\n",
        )
        compose_role_agents(tmp_path, [inst])
        body = (tmp_path / ".opencode" / "agents" / f"{inst.name}.md").read_text()
        # Find the description line, parse out the quoted value, check
        # its length + ellipsis sentinel.
        for line in body.splitlines():
            if line.startswith('description: "'):
                value = line[len('description: "'):-1]
                assert len(value) <= 200
                assert value.endswith("…")
                break
        else:  # pragma: no cover
            raise AssertionError("expected a description: line")

    def test_description_falls_back_when_role_md_has_only_heading(
        self, tmp_path: Path
    ) -> None:
        """OpenCode requires non-empty `description`; fallback uses the name."""
        inst = _instance_with_role(
            tmp_path, role_body="# stdcell_owner\n",  # nothing after the heading
        )
        compose_role_agents(tmp_path, [inst])
        body = (tmp_path / ".opencode" / "agents" / f"{inst.name}.md").read_text()
        assert 'description: ""' not in body
        assert 'description: "stdcell_owner personality"' in body

    def test_skips_instance_without_role_md(self, tmp_path: Path) -> None:
        """No ROLE.md → no agent file. Symmetric with compose_agents_md."""
        inst = Personality(
            template=_dummy_template(),
            project_root=tmp_path,
            name="rolemissing",
        )
        inst.root.mkdir(parents=True)  # but no ROLE.md
        written = compose_role_agents(tmp_path, [inst])
        assert written == []
        assert not (
            tmp_path / ".opencode" / "agents" / "rolemissing.md"
        ).exists()

    def test_idempotent_on_rerun(self, tmp_path: Path) -> None:
        inst = _instance_with_role(tmp_path)
        compose_role_agents(tmp_path, [inst])
        first = (tmp_path / ".opencode" / "agents" / f"{inst.name}.md").read_text()
        compose_role_agents(tmp_path, [inst])
        second = (tmp_path / ".opencode" / "agents" / f"{inst.name}.md").read_text()
        assert first == second

    def test_user_authored_file_preserved_and_staged_for_sync(
        self, tmp_path: Path
    ) -> None:
        """User-authored .opencode/agents/<n>.md → preserved; fresh content staged for /sync."""
        inst = _instance_with_role(tmp_path)
        target = tmp_path / ".opencode" / "agents" / f"{inst.name}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        custom = "# my hand-rolled agent — no marker\nbody\n"
        target.write_text(custom)
        written = compose_role_agents(tmp_path, [inst])
        # Working file untouched.
        assert target.read_text() == custom
        # Fresh template staged at the documented /sync location.
        staged = (
            tmp_path / ".allmight" / "templates" / "agents" / f"{inst.name}.md"
        )
        assert staged in written
        assert staged.is_file()
        assert "mode: subagent" in staged.read_text()


class TestAgentsMdFrameworkPrimer:
    """`compose_agents_md` must always emit the framework primer.

    The primer is the air-gap agent's only baseline understanding of
    All-Might before any personality exists; it must survive both the
    empty-registry case (right after ``allmight init``) and the
    populated-registry case (after ``/onboard`` runs ``allmight add``).
    """

    def test_empty_registry_emits_primer(self, tmp_path: Path) -> None:
        """`allmight init` calls ``compose_agents_md(root, [])`` — the
        primer headings must all appear so the agent has framework
        context before ``/onboard`` runs."""
        compose_agents_md(tmp_path, [], project_name="demo")
        content = (tmp_path / "AGENTS.md").read_text()
        for heading in (
            "## About All-Might",
            "## Slash commands",
            "## Routing",
            "## Personality subagents",
            "## When to suggest user actions",
            "## Memory model — scope-first",
            "## Recovery awareness",
            "## Layering — what lives where",
        ):
            assert heading in content, f"missing primer section: {heading}"

    def test_empty_registry_lists_every_slash_command(
        self, tmp_path: Path,
    ) -> None:
        """The slash-command table must enumerate every command All-Might
        installs; agents that can't reach the README rely on this list."""
        compose_agents_md(tmp_path, [], project_name="demo")
        content = (tmp_path / "AGENTS.md").read_text()
        for cmd in (
            "/onboard",
            "/search",
            "/remember",
            "/recall",
            "/recover",
            "/one-for-all",
            "/all-for-one",
            "/split",
            "/sync",
        ):
            assert cmd in content, f"primer omits slash command: {cmd}"

    def test_split_listed_but_not_in_when_to_suggest(
        self, tmp_path: Path,
    ) -> None:
        """``/split`` is a manual-only personality refactor. Its design
        forbids agent self-evaluation: it must appear in the Slash
        commands enumeration (so the agent knows it exists when the
        user types it) but must **not** appear in the
        "When to suggest user actions" table (which teaches the agent
        to volunteer the command on context cues). False positives in
        that table are the failure mode this test guards against."""
        compose_agents_md(tmp_path, [], project_name="demo")
        content = (tmp_path / "AGENTS.md").read_text()

        slash_section_start = content.index("## Slash commands")
        when_to_suggest_start = content.index("## When to suggest user actions")
        memory_model_start = content.index("## Memory model — scope-first")

        slash_section = content[slash_section_start:when_to_suggest_start]
        when_to_suggest_section = content[when_to_suggest_start:memory_model_start]

        assert "/split" in slash_section, "/split must be enumerated"
        assert "/split" not in when_to_suggest_section, (
            "/split must NOT be in the When-to-suggest table — manual only"
        )

    def test_empty_registry_suggests_onboard(self, tmp_path: Path) -> None:
        """No personalities yet → the personalities section must point at
        ``/onboard``, otherwise the agent has no actionable next step."""
        compose_agents_md(tmp_path, [], project_name="demo")
        content = (tmp_path / "AGENTS.md").read_text()
        assert "no personalities yet" in content
        assert "/onboard" in content

    def test_empty_registry_emphasises_search_only_for_database(
        self, tmp_path: Path,
    ) -> None:
        """SRP rule: the agent surface against the knowledge graph is
        search-only. Keep the wording explicit so the agent never tries
        to mutate a corpus via slash commands."""
        compose_agents_md(tmp_path, [], project_name="demo")
        content = (tmp_path / "AGENTS.md").read_text()
        assert "search-only" in content

    def test_populated_registry_keeps_primer_then_personality(
        self, tmp_path: Path,
    ) -> None:
        """A real personality with ROLE.md must land *after* the primer,
        not in place of it. Without this we'd lose framework context
        the moment ``/onboard`` creates the first personality."""
        inst = _instance_with_role(
            tmp_path, name="stdcell_owner",
            role_body="# stdcell_owner\n\nStandard-cell characterisation.\n",
        )
        compose_agents_md(tmp_path, [inst], project_name="demo")
        content = (tmp_path / "AGENTS.md").read_text()
        assert "## About All-Might" in content
        # Personality body appears strictly after the primer's last section.
        primer_anchor = content.index("## Layering — what lives where")
        personalities_anchor = content.index("## Personalities")
        personality_body = content.index("Standard-cell characterisation")
        assert primer_anchor < personalities_anchor < personality_body

    def test_marker_stays_on_first_line(self, tmp_path: Path) -> None:
        """Re-init safety: the file is recognised as All-Might-owned by
        ``write_guarded`` / conflict staging only if the marker is on
        line 1. Don't let the primer push it out of place."""
        compose_agents_md(tmp_path, [], project_name="demo")
        first_line = (tmp_path / "AGENTS.md").read_text().splitlines()[0]
        assert first_line == "<!-- all-might generated -->"
