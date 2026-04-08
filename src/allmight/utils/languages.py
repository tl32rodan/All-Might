"""Language and framework detection heuristics.

Used by Detroit SMAK's scanner to identify project characteristics.
"""

from __future__ import annotations

from pathlib import Path

# File extension → language mapping
EXTENSION_MAP: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript",
    ".tsx": "TypeScript",
    ".v": "Verilog",
    ".sv": "SystemVerilog",
    ".vhd": "VHDL",
    ".vhdl": "VHDL",
    ".pl": "Perl",
    ".pm": "Perl",
    ".rb": "Ruby",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C",
    ".hpp": "C++",
    ".cs": "C#",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".sh": "Shell",
    ".bash": "Shell",
}

# Marker file → framework mapping
FRAMEWORK_MARKERS: dict[str, str] = {
    "pyproject.toml": "Python",
    "setup.py": "Python",
    "setup.cfg": "Python",
    "requirements.txt": "Python",
    "Pipfile": "Python",
    "package.json": "Node.js",
    "tsconfig.json": "TypeScript",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "Gemfile": "Ruby",
    "pom.xml": "Java/Maven",
    "build.gradle": "Java/Gradle",
    "CMakeLists.txt": "CMake",
    "Makefile": "Make",
    "docker-compose.yml": "Docker",
    "Dockerfile": "Docker",
    ".synopsys_dc.setup": "EDA/Synopsys",
    "filelist.f": "EDA/Verilog",
}

# Common directory names and their roles
DIRECTORY_ROLES: dict[str, str] = {
    "src": "Source code",
    "lib": "Library code",
    "tests": "Test files",
    "test": "Test files",
    "spec": "Test specifications",
    "docs": "Documentation",
    "doc": "Documentation",
    "documentation": "Documentation",
    "issues": "Issue tracking",
    "scripts": "Utility scripts",
    "bin": "Executables",
    "config": "Configuration",
    "rtl": "RTL design files",
    "verif": "Verification/testbench",
    "constraints": "Design constraints",
    "tb": "Testbench files",
}


def detect_languages(root: Path, max_depth: int = 3) -> list[str]:
    """Detect programming languages used in a project by file extensions.

    Scans up to max_depth levels deep and returns languages sorted by file count.
    """
    lang_counts: dict[str, int] = {}

    for path in _walk_limited(root, max_depth):
        if path.is_file():
            lang = EXTENSION_MAP.get(path.suffix.lower())
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

    return sorted(lang_counts, key=lambda l: lang_counts[l], reverse=True)


def detect_frameworks(root: Path) -> list[str]:
    """Detect frameworks/build systems by marker files in the project root."""
    found = []
    for marker, framework in FRAMEWORK_MARKERS.items():
        if (root / marker).exists():
            found.append(framework)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique = []
    for f in found:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique


def detect_directories(root: Path) -> dict[str, str]:
    """Detect well-known directories and their roles.

    Returns a mapping of directory name → role description.
    """
    found = {}
    for item in sorted(root.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            role = DIRECTORY_ROLES.get(item.name.lower())
            if role:
                found[item.name] = role
    return found


def _walk_limited(root: Path, max_depth: int, _current_depth: int = 0):
    """Walk directory tree up to a maximum depth."""
    if _current_depth > max_depth:
        return
    try:
        for item in root.iterdir():
            if item.name.startswith("."):
                continue
            yield item
            if item.is_dir():
                yield from _walk_limited(item, max_depth, _current_depth + 1)
    except PermissionError:
        pass
