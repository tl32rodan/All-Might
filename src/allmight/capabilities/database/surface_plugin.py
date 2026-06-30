"""``search-surface`` OpenCode plugin generator (All-Might / database).

Closes the read-side asymmetry diagnosed in
``docs/retrieval-surfacing-proposal.md``. One ``tool.execute.after`` hook
on grep/glob:

* **Read surfacing (§1–5):** runs a parallel ``smak search-all`` for the
  active personality's database workspaces and *appends* the top hits to
  the tool output — "augment silently", never gate (P-2). The agent keeps
  its grep reflex but gets the structured answer for free.
* **Create/maintain (§6, bundled):** throttled, fire-and-forget
  ``allmight database ingest --incremental`` so the index self-bootstraps
  and stays fresh off the hot path.

OpenCode-only this round (rides the already-declared-but-unused
``tool_execute_after_inject`` capability — ``claude_code: False``). The
Claude Code mirror (``PreToolUse`` + ``additionalContext``) is a
heartbeat-gated follow-up.

Shared-string discipline (CLAUDE.md dual-platform rule 3): the framing
header and all thresholds live here as Python constants and are
substituted into the TS template, so a future CC mirror cannot drift.

NOTE (verification, proposal §7.1): the bundled OpenCode reference
documents ``tool.execute.after`` as "observe the result". Appending to
``output.output`` is the intended same-turn surface but is **unverified
on a live host** — the plugin skips silently (no ``.injected``
heartbeat) when ``output.output`` is not a mutable string, so the
``fired`` vs ``injected`` ratio reveals the truth instead of guessing.
"""

from __future__ import annotations

# --- Single source: framing text + thresholds (substituted into the TS) ---
# Short, literal, directive — readable by a weak (Kimi-class) model. No
# meta-cognition prose (CLAUDE.md anti-pattern).
SURFACE_HEADER = (
    "Related domain knowledge (SMAK vector hits — read these files if "
    "they look relevant):"
)
SURFACE_MIN_SCORE = 0.3     # relevance floor; tune from P-6 heartbeat data
SURFACE_TOP_K = 3           # cap injected hits
SMAK_TIMEOUT_MS = 3000      # time-box the search so it never stalls a grep
DB_INGEST_THROTTLE_SECONDS = 14400  # 4h — skip re-kicking ingest within window


def build_search_surface_ts() -> str:
    """Return the ``search-surface.ts`` OpenCode plugin body."""
    from ...core.plugin_telemetry import TS_HEARTBEAT_SNIPPET

    escaped_header = (
        SURFACE_HEADER
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
    )
    return (
        _SEARCH_SURFACE_TEMPLATE
        .replace("__TS_HEARTBEAT_SNIPPET__", TS_HEARTBEAT_SNIPPET)
        .replace("__SURFACE_HEADER__", escaped_header)
        .replace("__SURFACE_MIN_SCORE__", repr(SURFACE_MIN_SCORE))
        .replace("__SURFACE_TOP_K__", str(SURFACE_TOP_K))
        .replace("__SMAK_TIMEOUT_MS__", str(SMAK_TIMEOUT_MS))
        .replace("__DB_INGEST_THROTTLE_MS__", str(DB_INGEST_THROTTLE_SECONDS * 1000))
    )


_SEARCH_SURFACE_TEMPLATE = """\
// all-might generated
/**
 * Search Surface — OpenCode plugin (All-Might / database capability)
 *
 * On every grep/glob (tool.execute.after), runs a parallel SMAK vector
 * search for the active personality's database workspaces and APPENDS
 * the top hits to the tool output so the agent sees structured domain
 * knowledge alongside its grep result — without choosing /search.
 * Augment-only: never blocks, denies, or rewrites the tool.
 *
 * The same hook lazily kicks `allmight database ingest --incremental`
 * (throttled, fire-and-forget) so the index self-bootstraps and stays
 * fresh — the create/maintain closure (proposal §6).
 *
 * OpenCode-only (rides tool_execute_after_inject). No Claude Code
 * mirror yet; see docs/retrieval-surfacing-proposal.md.
 *
 * Hook:
 *   tool.execute.after(grep|glob) -> append SMAK hits + kick db ingest
 */
import type { Plugin } from "@opencode-ai/plugin";
import { spawn, execFile } from "child_process";
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from "fs";
import { join } from "path";

__TS_HEARTBEAT_SNIPPET__
const SURFACE_HEADER = `__SURFACE_HEADER__`;
const SURFACE_MIN_SCORE = __SURFACE_MIN_SCORE__;
const SURFACE_TOP_K = __SURFACE_TOP_K__;
const SMAK_TIMEOUT_MS = __SMAK_TIMEOUT_MS__;
const DB_INGEST_THROTTLE_MS = __DB_INGEST_THROTTLE_MS__;

// Active personality: MEMORY.md "> **Default personality**: <name>"
// callout, else the sole personality that opted into database/. Mirrors
// core/routing.ROUTING_PREAMBLE + mcp.knowledge_server.resolve_default_personality.
function resolveActivePersonality(cwd: string): string | null {
  try {
    const mem = join(cwd, "MEMORY.md");
    if (existsSync(mem)) {
      const text = readFileSync(mem, "utf-8");
      const m = text.match(/^>\\s*\\*\\*Default personality\\*\\*:\\s*(.+?)\\s*$/m);
      if (m) return m[1].trim();
    }
  } catch {
    // fall through
  }
  try {
    const base = join(cwd, "personalities");
    if (!existsSync(base)) return null;
    const withDb = readdirSync(base).filter((p) =>
      existsSync(join(base, p, "database")),
    );
    if (withDb.length === 1) return withDb[0];
  } catch {
    // fall through
  }
  return null;
}

// personalities/<active>/database/*/config.yaml whose store/ is non-empty
// (an empty store means "not yet ingested" — nothing to surface).
function activeDbConfigs(cwd: string, active: string): string[] {
  const out: string[] = [];
  try {
    const dbDir = join(cwd, "personalities", active, "database");
    if (!existsSync(dbDir)) return out;
    for (const ws of readdirSync(dbDir)) {
      const cfg = join(dbDir, ws, "config.yaml");
      if (!existsSync(cfg)) continue;
      const store = join(dbDir, ws, "store");
      let populated = false;
      try {
        populated = existsSync(store) && readdirSync(store).length > 0;
      } catch {
        populated = false;
      }
      if (populated) out.push(cfg);
    }
  } catch {
    // best-effort
  }
  return out.slice(0, 4);
}

// `smak search-all "<query>" --config <cfg> --top-k N --json`, time-boxed.
// Resolves [] on any error/timeout — a plugin must never throw or stall.
function smakSearch(cwd: string, cfg: string, query: string): Promise<any[]> {
  return new Promise((resolve) => {
    let done = false;
    const finish = (hits: any[]) => {
      if (!done) {
        done = true;
        resolve(hits);
      }
    };
    try {
      const child = execFile(
        "smak",
        ["search-all", query, "--config", cfg, "--top-k", String(SURFACE_TOP_K), "--json"],
        { cwd, timeout: SMAK_TIMEOUT_MS, maxBuffer: 1 << 20 },
        (err: any, stdout: any) => {
          if (err) {
            finish([]);
            return;
          }
          try {
            const parsed = JSON.parse(String(stdout || "{}"));
            finish(Array.isArray(parsed?.results) ? parsed.results : []);
          } catch {
            finish([]);
          }
        },
      );
      child.on("error", () => finish([]));
    } catch {
      finish([]);
    }
  });
}

function surfaceBlock(hits: any[]): string {
  const lines = hits.map((h: any) => {
    const id = String(h?.id ?? h?.metadata?.path ?? "?");
    const score = typeof h?.score === "number" ? h.score.toFixed(2) : "?";
    const snippet = String(h?.text ?? "").replace(/\\s+/g, " ").slice(0, 120);
    return `- ${id}  (score ${score}) — ${snippet}`;
  });
  return SURFACE_HEADER + "\\n" + lines.join("\\n");
}

// Throttled, fire-and-forget create/maintain closure (proposal §6).
// Returns true if it kicked an ingest. Touches the marker optimistically
// so an in-flight ingest doesn't get re-kicked every grep.
function maybeKickIngest(cwd: string): boolean {
  try {
    const dir = join(cwd, ".allmight");
    const marker = join(dir, "db_last_ingest");
    if (
      existsSync(marker) &&
      Date.now() - statSync(marker).mtimeMs < DB_INGEST_THROTTLE_MS
    ) {
      return false;
    }
    const child = spawn("allmight", ["database", "ingest", "--incremental"], {
      cwd,
      stdio: "ignore",
      detached: true,
    });
    child.unref();
    child.on("error", () => {
      // allmight not on PATH — silent; recovery via the CLI by hand.
    });
    try {
      mkdirSync(dir, { recursive: true });
      writeFileSync(marker, "");
    } catch {
      // marker touch is best-effort
    }
    return true;
  } catch {
    return false;
  }
}

export const SearchSurfacePlugin: Plugin = async ({ directory }: any) => {
  const cwd = (directory as string | undefined) ?? process.cwd();

  return {
    "tool.execute.after": async (input: any, output: any) => {
      emitHeartbeat("search-surface", cwd);
      try {
        const tool = String(input?.tool ?? "");
        if (tool !== "grep" && tool !== "glob") return;
        const query = String(input?.args?.pattern ?? "").trim();
        if (!query) return;
        const target = String(input?.args?.path ?? "");
        if (/(^|\\/)\\.(allmight|opencode)(\\/|$)/.test(target)) return;

        // Part B — create/maintain closure (independent of surfacing).
        if (maybeKickIngest(cwd)) emitHeartbeat("search-surface.ingest", cwd);

        // Part A — read surfacing.
        const active = resolveActivePersonality(cwd);
        if (!active) return;
        const configs = activeDbConfigs(cwd, active);
        if (configs.length === 0) return;

        const all = (
          await Promise.all(configs.map((c) => smakSearch(cwd, c, query)))
        ).flat();
        const hits = all
          .filter(
            (h: any) =>
              typeof h?.score === "number" && h.score >= SURFACE_MIN_SCORE,
          )
          .sort((a: any, b: any) => (b.score as number) - (a.score as number))
          .slice(0, SURFACE_TOP_K);
        if (hits.length === 0) return;

        // Same-turn augment: append to the tool output (P-2). If the host
        // does not expose a mutable string output, skip — no .injected
        // heartbeat fires, so the fired/injected ratio measures it.
        if (output && typeof output.output === "string") {
          output.output = output.output + "\\n\\n" + surfaceBlock(hits);
          emitHeartbeat("search-surface.injected", cwd);
        }
      } catch {
        // A plugin must never throw.
      }
    },
  };
};

export default SearchSurfacePlugin;
"""
