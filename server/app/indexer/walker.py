"""File-tree walking with filtering of vendored / binary / lock files."""

from __future__ import annotations

import os

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", "out", "target",
    "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache",
    "vendor", ".idea", ".vscode", "coverage", ".cache",
}

SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Cargo.lock", "go.sum", "composer.lock", "Gemfile.lock",
}

LANGUAGE_BY_EXT = {
    ".ts": "typescript", ".tsx": "typescript", ".js": "javascript", ".jsx": "javascript",
    ".py": "python", ".java": "java", ".go": "go", ".rs": "rust",
    ".cpp": "cpp", ".cc": "cpp", ".c": "c", ".h": "c", ".hpp": "cpp",
    ".rb": "ruby", ".php": "php", ".cs": "csharp", ".kt": "kotlin",
    ".swift": "swift", ".scala": "scala", ".md": "markdown",
}

MAX_FILE_BYTES = 500_000  # skip files larger than ~500KB


def detect_language(path: str) -> str | None:
    _, ext = os.path.splitext(path)
    return LANGUAGE_BY_EXT.get(ext.lower())


def walk_source_files(root: str) -> list[str]:
    """Return relative paths of indexable source files under *root*."""
    results: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if name in SKIP_FILES:
                continue
            if detect_language(name) is None:
                continue
            full = os.path.join(dirpath, name)
            try:
                if os.path.getsize(full) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            results.append(os.path.relpath(full, root))
    return sorted(results)
