"""SmakBridge — calls SMAK CLI via subprocess.

All-Might does NOT import SMAK Python modules. Instead, it shells out
to ``smak <command> --json`` and parses the JSON output. This keeps
All-Might free of SMAK's heavy dependencies (faiss-cpu, llama-index,
etc.) and allows SMAK to evolve independently.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class SmakBridgeError(Exception):
    """Raised when the SMAK CLI returns a non-zero exit code."""

    def __init__(self, message: str, returncode: int, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class SmakBridge:
    """Calls SMAK CLI via subprocess. No SMAK Python dependencies needed.

    All methods shell out to ``smak <command> --json`` and parse the
    JSON output. Requires SMAK CLI to be installed and on PATH (or
    provide a custom path via *smak_cmd*).
    """

    def __init__(
        self,
        workspace_config: Path | str,
        smak_cmd: str = "smak",
        timeout: int = 300,
    ) -> None:
        self.workspace_config = str(Path(workspace_config).resolve())
        self.smak_cmd = smak_cmd
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self, query: str, index: str = "source_code", top_k: int = 5,
    ) -> dict[str, Any]:
        """Semantic search within a single index."""
        return self._run([
            "search", query,
            "--config", self.workspace_config,
            "--index", index,
            "--top-k", str(top_k),
        ])

    def search_all(
        self, query: str, top_k: int = 3,
    ) -> dict[str, Any]:
        """Search across all indices."""
        return self._run([
            "search-all", query,
            "--config", self.workspace_config,
            "--top-k", str(top_k),
        ])

    def lookup(
        self, uid: str, index: str = "source_code",
    ) -> dict[str, Any]:
        """Look up a UID in the vector store."""
        return self._run([
            "lookup", uid,
            "--config", self.workspace_config,
            "--index", index,
        ])

    # ------------------------------------------------------------------
    # Enrichment
    # ------------------------------------------------------------------

    def enrich_symbol(
        self, file_path: str, symbol: str,
        intent: str | None = None,
        relations: list[str] | None = None,
        index: str = "source_code",
        bidirectional: bool = False,
    ) -> dict[str, Any]:
        """Annotate a symbol with intent and/or relations."""
        args = [
            "enrich",
            "--config", self.workspace_config,
            "--index", index,
            "--file", file_path,
            "--symbol", symbol,
        ]
        if intent:
            args.extend(["--intent", intent])
        if relations:
            for rel in relations:
                args.extend(["--relation", rel])
        if bidirectional:
            args.append("--bidirectional")
        return self._run(args)

    def enrich_file(
        self, file_path: str, index: str = "source_code",
    ) -> dict[str, Any]:
        """Sync a file's sidecar."""
        return self._run([
            "enrich-file",
            "--config", self.workspace_config,
            "--index", index,
            "--file", file_path,
        ])

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def ingest(self, index: str | None = None) -> dict[str, Any]:
        """Re-ingest files into a vector store index."""
        args = [
            "ingest",
            "--config", self.workspace_config,
        ]
        if index:
            args.extend(["--index", index])
        return self._run(args)

    def describe(self) -> dict[str, Any]:
        """Describe workspace indices."""
        return self._run([
            "describe",
            "--config", self.workspace_config,
        ])

    def health(self) -> dict[str, Any]:
        """Run health checks."""
        return self._run([
            "health",
            "--config", self.workspace_config,
        ])

    def graph_stats(self) -> dict[str, Any]:
        """Knowledge graph coverage statistics."""
        return self._run([
            "stats",
            "--config", self.workspace_config,
        ])

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self, args: list[str]) -> dict[str, Any]:
        """Execute ``smak <args> --json`` and parse the JSON output.

        Raises :class:`SmakBridgeError` on non-zero exit codes.
        """
        cmd = [self.smak_cmd] + args + ["--json"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except FileNotFoundError:
            raise SmakBridgeError(
                f"SMAK CLI not found: '{self.smak_cmd}'. "
                "Ensure SMAK is installed and on PATH.",
                returncode=-1,
            )
        except subprocess.TimeoutExpired:
            raise SmakBridgeError(
                f"SMAK CLI timed out after {self.timeout}s",
                returncode=-1,
            )

        if result.returncode != 0:
            raise SmakBridgeError(
                f"SMAK CLI failed (exit {result.returncode}): {result.stderr.strip()}",
                returncode=result.returncode,
                stderr=result.stderr,
            )

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            raise SmakBridgeError(
                f"SMAK CLI returned invalid JSON: {result.stdout[:200]}",
                returncode=0,
                stderr=result.stderr,
            )
