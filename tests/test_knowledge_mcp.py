"""All-Might Knowledge MCP server (Framework B, slice 1).

The wrapper exposes two intent-named tools — ``project_knowledge_search``
(code + docs + mesh, the offline web_search/context7 analog) and
``memory_recall`` (per-personality L3 journal) — delegating to
``smak.core_ops``.

These tests pin the parts that don't need the heavy ``smak`` / ``mcp``
deps installed:

* discovery + default-personality resolution from the project tree,
* the deterministic guards (no workspace / no personality) that return
  a no-hallucination payload **before** any ``smak`` import,
* delegation shape, with ``smak`` mocked into ``sys.modules``,
* tool registration (names + descriptions), with ``mcp`` mocked.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from allmight.mcp import knowledge_server as ks


# ---------------------------------------------------------------------------
# Fixtures: a fake project tree
# ---------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "personalities" / "stdcell_owner" / "database" / "stdcell").mkdir(
        parents=True,
    )
    (root / "personalities" / "stdcell_owner" / "database" / "stdcell" / "config.yaml").write_text(
        "indices: []\n",
    )
    (root / "personalities" / "pll_owner" / "database" / "pll").mkdir(parents=True)
    (root / "personalities" / "pll_owner" / "database" / "pll" / "config.yaml").write_text(
        "indices: []\n",
    )
    (root / "personalities" / "stdcell_owner" / "memory").mkdir(parents=True)
    (root / "personalities" / "stdcell_owner" / "memory" / "smak_config.yaml").write_text(
        "indices: []\n",
    )
    return root


# ---------------------------------------------------------------------------
# Discovery / resolution helpers
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_finds_all_database_configs_sorted(self, project: Path) -> None:
        configs = ks.discover_database_configs(project)
        names = [c.parent.name for c in configs]
        assert names == ["pll", "stdcell"]  # sorted, across personalities

    def test_no_personalities_dir_returns_empty(self, tmp_path: Path) -> None:
        assert ks.discover_database_configs(tmp_path) == []

    def test_lists_personalities(self, project: Path) -> None:
        assert ks.list_personalities(project) == ["pll_owner", "stdcell_owner"]

    def test_resolve_default_personality_from_callout(self, project: Path) -> None:
        (project / "MEMORY.md").write_text(
            "# Project\n\n> **Default personality**: stdcell_owner\n\nbody\n",
        )
        assert ks.resolve_default_personality(project) == "stdcell_owner"

    def test_resolve_default_personality_absent(self, project: Path) -> None:
        assert ks.resolve_default_personality(project) is None  # no MEMORY.md
        (project / "MEMORY.md").write_text("# Project\n\nno callout here\n")
        assert ks.resolve_default_personality(project) is None

    def test_discover_memory_config(self, project: Path) -> None:
        assert ks.discover_memory_config(project, "stdcell_owner") is not None
        assert ks.discover_memory_config(project, "pll_owner") is None


# ---------------------------------------------------------------------------
# Deterministic guards — must return a no-hallucination payload WITHOUT smak
# ---------------------------------------------------------------------------


class TestGuardsNeedNoSmak:
    def test_knowledge_search_empty_when_no_workspaces(self, tmp_path: Path) -> None:
        out = ks.run_project_knowledge_search(tmp_path, "anything")
        assert out["empty"] is True
        assert "not indexed" in out["reason"].lower()

    def test_memory_recall_no_personality(self, tmp_path: Path) -> None:
        # No MEMORY.md, none passed → clear error, never a guess.
        out = ks.run_memory_recall(tmp_path, "anything")
        assert "error" in out
        assert out["available"] == []

    def test_memory_recall_no_index_for_personality(self, project: Path) -> None:
        out = ks.run_memory_recall(project, "q", personality="pll_owner")
        assert out["empty"] is True
        assert out["personality"] == "pll_owner"


# ---------------------------------------------------------------------------
# Delegation shape — smak mocked into sys.modules
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_smak(monkeypatch: pytest.MonkeyPatch):
    """Inject fake ``smak.core_ops`` / ``smak.config`` / ``smak.factory``."""
    calls: dict[str, list] = {"search_all": [], "search": []}

    core_ops = types.ModuleType("smak.core_ops")

    def do_search_all(config, query, top_k=3, embedding_config=None):
        calls["search_all"].append((config, query, top_k))
        return {"source_code": {"results": []}, "docs": {"results": []}}

    def do_search(config, query, index="source_code", top_k=5, embedding_config=None):
        calls["search"].append((config, query, index, top_k))
        return {"results": []}

    core_ops.do_search_all = do_search_all
    core_ops.do_search = do_search

    config_mod = types.ModuleType("smak.config")
    config_mod.load_config = lambda p: {"_config_from": str(p)}
    config_mod.load_embedding_config = lambda *a, **k: object()
    factory_mod = types.ModuleType("smak.factory")
    factory_mod.init_config = lambda cfg, embedding_config=None: cfg

    smak_pkg = types.ModuleType("smak")
    monkeypatch.setitem(sys.modules, "smak", smak_pkg)
    monkeypatch.setitem(sys.modules, "smak.core_ops", core_ops)
    monkeypatch.setitem(sys.modules, "smak.config", config_mod)
    monkeypatch.setitem(sys.modules, "smak.factory", factory_mod)
    return calls


class TestDelegation:
    def test_knowledge_search_calls_search_all_per_workspace(
        self, project: Path, fake_smak,
    ) -> None:
        out = ks.run_project_knowledge_search(project, "update cell", top_k=7)
        # One do_search_all per discovered database workspace (2).
        assert len(fake_smak["search_all"]) == 2
        assert all(c[1] == "update cell" and c[2] == 7 for c in fake_smak["search_all"])
        assert {w["workspace"] for w in out["workspaces"]} == {"pll", "stdcell"}

    def test_memory_recall_searches_journal_index(
        self, project: Path, fake_smak,
    ) -> None:
        out = ks.run_memory_recall(project, "did we decide", personality="stdcell_owner")
        assert len(fake_smak["search"]) == 1
        _cfg, q, index, top_k = fake_smak["search"][0]
        assert (q, index, top_k) == ("did we decide", "journal", 5)
        assert out["personality"] == "stdcell_owner"

    def test_knowledge_search_reports_per_workspace_error(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, fake_smak,
    ) -> None:
        # A workspace that raises must be reported, not crash the tool.
        def boom(config, query, top_k=3, embedding_config=None):
            raise RuntimeError("index missing")

        sys.modules["smak.core_ops"].do_search_all = boom
        out = ks.run_project_knowledge_search(project, "q")
        assert all("error" in w for w in out["workspaces"])


# ---------------------------------------------------------------------------
# Tool registration — mcp mocked
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_build_server_registers_two_intent_named_tools(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        registered: list = []

        class FakeMCP:
            def __init__(self, name): self.name = name
            def tool(self):
                def deco(fn):
                    registered.append(fn)
                    return fn
                return deco

        fastmcp_mod = types.ModuleType("mcp.server.fastmcp")
        fastmcp_mod.FastMCP = FakeMCP
        server_mod = types.ModuleType("mcp.server")
        mcp_pkg = types.ModuleType("mcp")
        monkeypatch.setitem(sys.modules, "mcp", mcp_pkg)
        monkeypatch.setitem(sys.modules, "mcp.server", server_mod)
        monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fastmcp_mod)

        ks.build_server()

        names = {fn.__name__ for fn in registered}
        assert names == {"project_knowledge_search", "memory_recall"}
        by_name = {fn.__name__: fn for fn in registered}
        # Descriptions come from the single-source constants and name the
        # offline substitution explicitly.
        assert by_name["project_knowledge_search"].__doc__ == ks.PROJECT_KNOWLEDGE_DESCRIPTION
        assert "web search" in ks.PROJECT_KNOWLEDGE_DESCRIPTION.lower()
        assert "context7" in ks.PROJECT_KNOWLEDGE_DESCRIPTION.lower()
        assert by_name["memory_recall"].__doc__ == ks.MEMORY_RECALL_DESCRIPTION
