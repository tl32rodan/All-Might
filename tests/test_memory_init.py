"""Tests for MemoryInitializer — L1/L2/L3 architecture.

L1: MEMORY.md at project root (hook-loaded, agent-writable)
L2: memory/understanding/ per-corpus knowledge (agent reads/writes)
L3: memory/journal/ + store/ (text files + SMAK vector index)
"""

import pytest
import yaml

from allmight.memory.config import MemoryConfigManager
from allmight.memory.initializer import MemoryInitializer


@pytest.fixture
def project_root(tmp_path):
    """A minimal project root."""
    return tmp_path


class TestMemoryInitializer:

    # -- L1: MEMORY.md at project root ---------------------------------

    def test_creates_memory_md_at_root(self, project_root):
        """L1: MEMORY.md at project root (not inside memory/)."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / "MEMORY.md").exists()

    def test_memory_md_has_project_map(self, project_root):
        """L1: MEMORY.md contains a project map section."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / "MEMORY.md").read_text()
        assert "Project Map" in content

    def test_memory_md_has_user_preferences(self, project_root):
        """L1: MEMORY.md has user preferences section."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / "MEMORY.md").read_text()
        assert "User Preferences" in content or "Preferences" in content

    # -- L2: understanding/ per-corpus ---------------------------------

    def test_creates_understanding_dir(self, project_root):
        """L2: memory/understanding/ directory created."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / "memory" / "understanding").is_dir()

    # -- L3: journal/ + store/ -----------------------------------------

    def test_creates_journal_dir(self, project_root):
        """L3: memory/journal/ directory created."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / "memory" / "journal").is_dir()

    def test_creates_store_dir(self, project_root):
        """L3: memory/store/ for SMAK vector index."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / "memory" / "store").is_dir()

    def test_creates_smak_config(self, project_root):
        """SMAK config generated for journal index."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / "memory" / "smak_config.yaml").exists()

    def test_smak_config_indexes_journal(self, project_root):
        """SMAK config points to journal/ directory."""
        MemoryInitializer().initialize(project_root)
        with open(project_root / "memory" / "smak_config.yaml") as f:
            cfg = yaml.safe_load(f)
        index_names = [idx["name"] for idx in cfg.get("indices", [])]
        assert "journal" in index_names
        journal_idx = next(i for i in cfg["indices"] if i["name"] == "journal")
        assert "journal" in journal_idx["paths"][0]

    # -- Old architecture should NOT exist -----------------------------

    def test_no_episodes_dir(self, project_root):
        """Old episodes/ should not be created."""
        MemoryInitializer().initialize(project_root)
        assert not (project_root / "memory" / "episodes").exists()

    def test_no_semantic_dir(self, project_root):
        """Old semantic/ should not be created."""
        MemoryInitializer().initialize(project_root)
        assert not (project_root / "memory" / "semantic").exists()

    def test_no_working_dir(self, project_root):
        """Old working/ should not be created (MEMORY.md is at root)."""
        MemoryInitializer().initialize(project_root)
        assert not (project_root / "memory" / "working").exists()

    # -- Commands ------------------------------------------------------

    def test_generates_remember_command(self, project_root):
        MemoryInitializer().initialize(project_root)
        assert (project_root / ".opencode" / "commands" / "remember.md").exists()

    def test_generates_recall_command(self, project_root):
        MemoryInitializer().initialize(project_root)
        assert (project_root / ".opencode" / "commands" / "recall.md").exists()

    def test_no_consolidate_command(self, project_root):
        """consolidate removed — no more episode-to-semantic pipeline."""
        MemoryInitializer().initialize(project_root)
        assert not (project_root / ".opencode" / "commands" / "consolidate.md").exists()

    def test_remember_command_mentions_journal(self, project_root):
        """remember.md should reference journal/ (L3)."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "remember.md").read_text()
        assert "journal" in content

    def test_remember_command_mentions_understanding(self, project_root):
        """remember.md should reference understanding/ (L2)."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "remember.md").read_text()
        assert "understanding" in content

    def test_recall_command_mentions_smak(self, project_root):
        """recall.md should use smak search against journal."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "recall.md").read_text()
        assert "smak search" in content

    # -- Per-corpus scoping principle ----------------------------------

    def test_remember_teaches_scope_first(self, project_root):
        """/remember leads with scope-first decision (not a /kind/ list)."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "remember.md").read_text()
        assert "scope" in content.lower()
        # Principle is expressed generically
        assert "<kind>/<workspace>.md" in content

    def test_remember_shows_todos_as_example(self, project_root):
        """TODOs appear as an example of per-corpus personal state."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "remember.md").read_text()
        assert "todo" in content.lower()

    def test_remember_usage_log_has_scope_tag(self, project_root):
        """Usage log format includes scope= so /reflect can audit drift."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "remember.md").read_text()
        assert "scope=" in content

    def test_recall_scans_per_corpus_folders(self, project_root):
        """/recall instructs agent to scan memory/<kind>/<workspace>.md files."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "recall.md").read_text()
        assert "<kind>/<workspace>.md" in content
        # And calls out picking up unfinished state
        assert "unfinished" in content.lower() or "pick up where" in content.lower()

    def test_reflect_audits_scoping(self, project_root):
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "reflect.md").read_text()
        assert "scop" in content.lower()  # scope / scoping

    def test_agents_md_teaches_scoping(self, project_root):
        MemoryInitializer().initialize(project_root)
        content = (project_root / "AGENTS.md").read_text()
        assert "<kind>/<workspace>.md" in content
        assert "scope" in content.lower()

    def test_no_claude_hooks_directory(self, project_root):
        """No .claude/hooks/ should be generated — TS plugins handle memory loading."""
        MemoryInitializer().initialize(project_root)
        assert not (project_root / ".claude" / "hooks").exists()

    def test_no_claude_settings_json(self, project_root):
        """No .claude/settings.json should be generated."""
        MemoryInitializer().initialize(project_root)
        assert not (project_root / ".claude" / "settings.json").exists()

    def test_no_claude_dir_at_all(self, project_root):
        """After memory init, .claude/ directory must not exist."""
        MemoryInitializer().initialize(project_root)
        assert not (project_root / ".claude").exists()

    def test_no_hardcoded_todos_dir(self, project_root):
        """Initializer does NOT precreate memory/todos/ — agents make it on demand."""
        MemoryInitializer().initialize(project_root)
        assert not (project_root / "memory" / "todos").exists()

    # -- AGENTS.md update ----------------------------------------------

    def test_updates_agents_md(self, project_root):
        (project_root / "AGENTS.md").write_text("# Test Project\n\nExisting content.\n")
        MemoryInitializer().initialize(project_root)
        content = (project_root / "AGENTS.md").read_text()
        assert "Memory" in content
        assert "Existing content." in content

    def test_creates_agents_md_if_missing(self, project_root):
        MemoryInitializer().initialize(project_root)
        assert (project_root / "AGENTS.md").is_file()
        content = (project_root / "AGENTS.md").read_text()
        assert "Memory" in content

    def test_agents_md_replaces_stale_symlink(self, project_root):
        """If AGENTS.md is a stale symlink (old install), it is replaced with a real file."""
        (project_root / "CLAUDE.md").write_text("old\n")
        (project_root / "AGENTS.md").symlink_to("CLAUDE.md")
        MemoryInitializer().initialize(project_root)
        assert not (project_root / "AGENTS.md").is_symlink()
        assert "<!-- ALL-MIGHT-MEMORY -->" in (project_root / "AGENTS.md").read_text()

    # -- Idempotency ---------------------------------------------------

    def test_idempotent(self, project_root):
        """Running init twice doesn't break anything."""
        init = MemoryInitializer()
        init.initialize(project_root)
        init.initialize(project_root)
        assert (project_root / "MEMORY.md").exists()
        assert (project_root / "memory" / "understanding").is_dir()
        assert (project_root / "memory" / "journal").is_dir()

    def test_creates_agents_md_as_real_file(self, project_root):
        """AGENTS.md created as a real file (not a symlink) for OpenCode."""
        MemoryInitializer().initialize(project_root)
        agents_md = project_root / "AGENTS.md"
        assert agents_md.is_file()
        assert not agents_md.is_symlink()

    def test_opencode_dotdir_created(self, project_root):
        """.opencode/ directory created."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / ".opencode").is_dir()

    def test_opencode_compat_idempotent(self, project_root):
        init = MemoryInitializer()
        init.initialize(project_root)
        init.initialize(project_root)
        agents_md = project_root / "AGENTS.md"
        assert agents_md.is_file()
        assert not agents_md.is_symlink()
        assert (project_root / ".opencode").is_dir()


class TestOpenCodeHooks:
    """opencode.json and plugin for OpenCode hook compatibility."""

    def test_creates_opencode_json(self, project_root):
        """opencode.json created inside .opencode/."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / ".opencode" / "opencode.json").exists()

    def test_creates_memory_load_plugin(self, project_root):
        """OpenCode plugin for L1 loader created."""
        MemoryInitializer().initialize(project_root)
        plugin = project_root / ".opencode" / "plugins" / "memory-load.ts"
        assert plugin.exists()

    def test_memory_load_plugin_reads_memory_md(self, project_root):
        """Plugin reads MEMORY.md content."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "plugins" / "memory-load.ts").read_text()
        assert "MEMORY.md" in content
        assert "chat.message" in content

    def test_memory_load_plugin_injects_scope_first(self, project_root):
        """Plugin injects the scope-first principle alongside MEMORY.md."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "plugins" / "memory-load.ts").read_text()
        assert "Scope-First" in content or "scope-first" in content.lower()
        assert "<kind>/<workspace>.md" in content

    def test_memory_load_plugin_handles_session_lifecycle(self, project_root):
        """Plugin subscribes to session.created and session.compacted to re-prime."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "plugins" / "memory-load.ts").read_text()
        assert "session.created" in content
        assert "session.compacted" in content
        # Primes once per session, not every message
        assert "primed" in content.lower()

    def test_creates_remember_trigger_plugin(self, project_root):
        """Remember-trigger plugin is generated alongside memory-load."""
        MemoryInitializer().initialize(project_root)
        plugin = project_root / ".opencode" / "plugins" / "remember-trigger.ts"
        assert plugin.exists()

    def test_remember_trigger_delegates_to_slash_remember(self, project_root):
        """Plugin nudges the agent to run /remember, not duplicate its logic."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "plugins" / "remember-trigger.ts").read_text()
        assert "/remember" in content
        # It should not be writing memory files itself
        assert "writeFileSync" not in content
        assert "appendFileSync" not in content

    def test_remember_trigger_has_idle_and_compacting_events(self, project_root):
        """Plugin fires on session.idle (with throttle) and pre-compaction."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "plugins" / "remember-trigger.ts").read_text()
        assert "session.idle" in content
        # experimental.session.compacting is a top-level hook key, not a
        # bus event string inside event handler
        assert '"experimental.session.compacting":' in content
        # Throttle constant (every N turns) must exist
        assert "NUDGE_EVERY" in content

    def test_plugins_use_correct_chat_message_signature(self, project_root):
        """chat.message is (input, output) and injects via output.parts.unshift."""
        MemoryInitializer().initialize(project_root)
        plugins = ["memory-load.ts", "remember-trigger.ts", "todo-curator.ts"]
        for name in plugins:
            content = (project_root / ".opencode" / "plugins" / name).read_text()
            # Two-arg signature
            assert '"chat.message": async (input: any, output: any)' in content, (
                f"{name}: chat.message must accept (input, output)"
            )
            # Inject as a text part, not by mutating msg.content
            assert "output.parts.unshift" in content, (
                f"{name}: must inject via output.parts.unshift"
            )
            assert 'type: "text"' in content, (
                f"{name}: must use text-part shape"
            )
            # No stale msg.content mutations remain
            assert "msg.content =" not in content, (
                f"{name}: stale msg.content mutation remains"
            )

    def test_creates_todo_curator_plugin(self, project_root):
        """TODO curator plugin is generated."""
        MemoryInitializer().initialize(project_root)
        plugin = project_root / ".opencode" / "plugins" / "todo-curator.ts"
        assert plugin.exists()

    def test_todo_curator_has_three_phases(self, project_root):
        """Curator observes TodoWrite, curates on compacting, surfaces on session.created."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "plugins" / "todo-curator.ts").read_text()
        # Observe — TodoWrite via tool.execute.after
        assert "tool.execute.after" in content
        assert "TodoWrite" in content
        # Curate — writes to memory/todos/<workspace>.md
        assert "memory/todos" in content or 'memory", "todos"' in content
        assert "appendFileSync" in content
        # Surface — reads open backlog and prefixes chat.message
        assert "## Open" in content
        assert "chat.message" in content

    def test_todo_curator_infers_workspace_from_knowledge_graph_path(self, project_root):
        """Workspace inference uses the knowledge_graph/<name>/ convention."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "plugins" / "todo-curator.ts").read_text()
        assert "knowledge_graph" in content

    def test_creates_opencode_package_json(self, project_root):
        """`.opencode/package.json` is generated so Bun can bun-install the plugin dep."""
        MemoryInitializer().initialize(project_root)
        pkg = project_root / ".opencode" / "package.json"
        assert pkg.exists()

    def test_opencode_package_json_declares_plugin_runtime(self, project_root):
        """Declares @opencode-ai/plugin, no devDependencies by default."""
        import json
        MemoryInitializer().initialize(project_root)
        pkg = json.loads((project_root / ".opencode" / "package.json").read_text())
        assert "@opencode-ai/plugin" in pkg["dependencies"]
        # Bun runtime supplies fs/path natively — no type package needed
        assert "devDependencies" not in pkg

    def test_opencode_package_json_idempotent(self, project_root):
        """Running init twice leaves package.json untouched (still has the dep)."""
        import json
        init = MemoryInitializer()
        init.initialize(project_root)
        init.initialize(project_root)
        pkg = json.loads((project_root / ".opencode" / "package.json").read_text())
        assert "@opencode-ai/plugin" in pkg["dependencies"]

    def test_opencode_package_json_preserves_user_edits(self, project_root):
        """User-added fields (scripts, other deps) are preserved across re-init."""
        import json
        (project_root / ".opencode").mkdir(exist_ok=True)
        (project_root / ".opencode" / "package.json").write_text(json.dumps({
            "name": "user-chose-this",
            "scripts": {"build": "bun build"},
            "dependencies": {"some-other-pkg": "^1.0.0"}
        }))
        MemoryInitializer().initialize(project_root)
        pkg = json.loads((project_root / ".opencode" / "package.json").read_text())
        assert pkg["name"] == "user-chose-this"
        assert pkg["scripts"]["build"] == "bun build"
        assert pkg["dependencies"]["some-other-pkg"] == "^1.0.0"
        assert "@opencode-ai/plugin" in pkg["dependencies"]

    def test_opencode_json_idempotent(self, project_root):
        """Running init twice produces the same opencode.json."""
        init = MemoryInitializer()
        init.initialize(project_root)
        first = (project_root / ".opencode" / "opencode.json").read_text()
        init.initialize(project_root)
        second = (project_root / ".opencode" / "opencode.json").read_text()
        assert first == second

    def test_opencode_json_preserves_existing(self, project_root):
        """Existing opencode.json fields are preserved (non-hook keys)."""
        import json
        (project_root / ".opencode").mkdir(exist_ok=True)
        (project_root / ".opencode" / "opencode.json").write_text(json.dumps({
            "model": "claude-sonnet-4-6",
            "experimental": {"other": True}
        }))
        MemoryInitializer().initialize(project_root)
        config = json.loads((project_root / ".opencode" / "opencode.json").read_text())
        assert config["model"] == "claude-sonnet-4-6"
        assert config["experimental"]["other"] is True


class TestMemoryConfigManager:

    def test_initialize_creates_config(self, tmp_path):
        mgr = MemoryConfigManager(tmp_path)
        cfg = mgr.initialize()
        assert (tmp_path / "memory" / "config.yaml").exists()

    def test_config_has_journal_store(self, tmp_path):
        """Config should define a journal store, not episodes/semantic."""
        mgr = MemoryConfigManager(tmp_path)
        cfg = mgr.initialize()
        assert "journal" in cfg.stores
        assert "episodes" not in cfg.stores
        assert "semantic_facts" not in cfg.stores

    def test_round_trip(self, tmp_path):
        mgr = MemoryConfigManager(tmp_path)
        cfg = mgr.initialize()
        mgr.save(cfg)
        loaded = mgr.load()
        assert "journal" in loaded.stores


class TestReflectCommand:
    """/reflect — structured self-reflection to maintain memory quality."""

    def test_creates_reflect_command(self, project_root):
        MemoryInitializer().initialize(project_root)
        assert (project_root / ".opencode" / "commands" / "reflect.md").exists()

    def test_reflect_mentions_all_tiers(self, project_root):
        """reflect.md references L1, L2, and L3."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "reflect.md").read_text()
        assert "MEMORY.md" in content
        assert "understanding" in content
        assert "journal" in content

    def test_reflect_has_checklist(self, project_root):
        """reflect.md has a structured checklist for the agent."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "reflect.md").read_text()
        assert "## How" in content or "## Checklist" in content or "## Steps" in content



class TestFeedbackLoop:
    """Feedback loop — usage logging and enhanced /reflect."""

    def test_creates_usage_log(self, project_root):
        """memory/usage.log created during init."""
        MemoryInitializer().initialize(project_root)
        assert (project_root / "memory" / "usage.log").exists()

    def test_remember_command_logs_usage(self, project_root):
        """remember.md instructs agent to log usage."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "remember.md").read_text()
        assert "usage.log" in content

    def test_recall_command_logs_usage(self, project_root):
        """recall.md instructs agent to log usage."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "recall.md").read_text()
        assert "usage.log" in content

    def test_reflect_reads_usage_log(self, project_root):
        """reflect.md includes usage review step."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "reflect.md").read_text()
        assert "usage.log" in content
        assert "Usage Review" in content or "usage review" in content

    def test_reflect_generates_insights(self, project_root):
        """reflect.md has an insights generation step."""
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "reflect.md").read_text()
        assert "Insight" in content or "insight" in content


class TestJournalFrontmatterTemplates:
    """F5 — /remember and /reflect templates carry the v1 sentinel so
    agents write structured entries by default."""

    def test_remember_template_has_v1_sentinel(self, project_root):
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "remember.md").read_text()
        assert "allmight_journal: v1" in content

    def test_reflect_template_has_v1_sentinel(self, project_root):
        MemoryInitializer().initialize(project_root)
        content = (project_root / ".opencode" / "commands" / "reflect.md").read_text()
        assert "allmight_journal: v1" in content


class TestTrajectoryWriterPlugin:
    """F5 — trajectory-writer.ts captures structured session data
    transparently to the daily user."""

    def test_trajectory_writer_plugin_exists(self, project_root):
        MemoryInitializer().initialize(project_root)
        assert (project_root / ".opencode" / "plugins" / "trajectory-writer.ts").exists()

    def test_trajectory_writer_subscribes_to_tool_lifecycle(self, project_root):
        MemoryInitializer().initialize(project_root)
        content = (
            project_root / ".opencode" / "plugins" / "trajectory-writer.ts"
        ).read_text()
        assert "tool.execute.before" in content
        assert "tool.execute.after" in content
        assert '"chat.message":' in content

    def test_trajectory_writer_writes_under_journal(self, project_root):
        MemoryInitializer().initialize(project_root)
        content = (
            project_root / ".opencode" / "plugins" / "trajectory-writer.ts"
        ).read_text()
        # The plugin must target memory/journal/<workspace>/ paths.
        assert 'memory", "journal"' in content or "memory/journal" in content
        # Negative: must NOT use the deprecated msg.content mutation.
        assert "msg.content =" not in content

    def test_trajectory_writer_emits_v1_frontmatter(self, project_root):
        MemoryInitializer().initialize(project_root)
        content = (
            project_root / ".opencode" / "plugins" / "trajectory-writer.ts"
        ).read_text()
        # Emits the sentinel so downstream export can distinguish it.
        assert "allmight_journal: v1" in content

