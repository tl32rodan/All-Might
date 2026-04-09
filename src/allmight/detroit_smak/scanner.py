"""Detroit SMAK Scanner — detects project characteristics.

Scans a project directory to identify languages, frameworks,
directory conventions, and proposes SMAK index configurations.
"""

from __future__ import annotations

from pathlib import Path

from ..core.domain import IndexSpec, ProjectManifest
from ..utils.git import get_repo_name
from ..utils.languages import detect_directories, detect_frameworks, detect_languages


class ProjectScanner:
    """Scans a project and produces a ProjectManifest."""

    def scan(self, root: Path) -> ProjectManifest:
        """Scan a project directory and return a manifest describing it.

        Args:
            root: The project root directory to scan.

        Returns:
            A ProjectManifest with detected languages, frameworks,
            directory structure, and proposed SMAK indices.
        """
        root = root.resolve()
        name = get_repo_name(root) or root.name
        languages = detect_languages(root)
        frameworks = detect_frameworks(root)
        directory_map = detect_directories(root)
        indices = self._propose_indices(root, directory_map, languages)
        has_path_env = self._detect_path_env(root)

        return ProjectManifest(
            name=name,
            root_path=root,
            languages=languages,
            frameworks=frameworks,
            directory_map=directory_map,
            indices=indices,
            has_path_env=has_path_env,
        )

    def _propose_indices(
        self,
        root: Path,
        directory_map: dict[str, str],
        languages: list[str],
    ) -> list[IndexSpec]:
        """Propose SMAK indices based on detected directories.

        Follows the pattern from SMAK's demo workspace: source_code,
        issues, tests, documentation as the 4 standard indices.
        """
        indices: list[IndexSpec] = []

        # Source code index — look for src/, lib/, or language-specific dirs
        source_dirs = [d for d in ("src", "lib") if d in directory_map]
        # EDA-specific: rtl, verif
        eda_dirs = [d for d in ("rtl", "verif", "tb") if d in directory_map]

        if eda_dirs:
            # EDA project — create separate indices per directory
            for d in eda_dirs:
                role = directory_map[d]
                indices.append(IndexSpec(
                    name=d,
                    description=f"{role} — {self._describe_eda_dir(d, languages)}",
                    paths=[f"./{d}"],
                ))
        elif source_dirs:
            lang_str = ", ".join(languages[:3]) if languages else "source"
            indices.append(IndexSpec(
                name="source_code",
                description=f"Project source code ({lang_str})",
                paths=[f"./{d}" for d in source_dirs],
            ))
        else:
            # Fallback: index the entire root
            lang_str = ", ".join(languages[:3]) if languages else "source"
            indices.append(IndexSpec(
                name="source_code",
                description=f"Project source code ({lang_str})",
                paths=["."],
            ))

        # Test index
        test_dirs = [d for d in ("tests", "test", "spec") if d in directory_map]
        if test_dirs:
            indices.append(IndexSpec(
                name="tests",
                description="Unit tests, integration tests, and test cases",
                paths=[f"./{d}" for d in test_dirs],
            ))
        # Check for tests nested inside src
        for src_dir in source_dirs:
            nested = root / src_dir / "tests"
            if nested.is_dir() and "tests" not in test_dirs:
                indices.append(IndexSpec(
                    name="tests",
                    description="Unit tests, integration tests, and test cases",
                    paths=[f"./{src_dir}/tests"],
                ))
                break

        # Documentation index
        doc_dirs = [d for d in ("docs", "doc", "documentation") if d in directory_map]
        if doc_dirs:
            indices.append(IndexSpec(
                name="documentation",
                description="Architecture docs, API docs, and general knowledge base",
                paths=[f"./{d}" for d in doc_dirs],
            ))

        # Issues index
        if "issues" in directory_map:
            indices.append(IndexSpec(
                name="issues",
                description="Bug reports, tickets, and known problems",
                paths=["./issues"],
            ))

        # Constraints index (EDA-specific)
        if "constraints" in directory_map:
            indices.append(IndexSpec(
                name="constraints",
                description="SDC timing constraints, floorplan DEF, and power intent UPF",
                paths=["./constraints"],
            ))

        return indices

    def _describe_eda_dir(self, dirname: str, languages: list[str]) -> str:
        """Generate a description for an EDA-specific directory."""
        descriptions = {
            "rtl": "RTL design files",
            "verif": "Verification testbenches and coverage models",
            "tb": "Testbench files",
            "constraints": "Timing constraints and floorplan",
        }
        lang_hint = ""
        if dirname == "rtl" and any(l in languages for l in ("Verilog", "SystemVerilog", "VHDL")):
            hdl = [l for l in languages if l in ("Verilog", "SystemVerilog", "VHDL")]
            lang_hint = f" ({', '.join(hdl)})"
        return descriptions.get(dirname, dirname) + lang_hint

    def _detect_path_env(self, root: Path) -> bool:
        """Check if the project uses environment-variable-based paths.

        Looks for existing workspace_config.yaml with path_env entries,
        or the presence of $DDI_ROOT_PATH in the environment.
        """
        import os

        if os.environ.get("DDI_ROOT_PATH"):
            return True

        config_path = root / "workspace_config.yaml"
        if config_path.exists():
            try:
                import yaml
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                if config and "indices" in config:
                    return any(
                        idx.get("path_env")
                        for idx in config["indices"]
                    )
            except Exception:
                pass

        return False
