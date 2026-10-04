"""Canonical workspace confinement shared by every filesystem operation."""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath


class WorkspaceViolation(ValueError):
    pass


def validate_relative_path(path: str) -> str:
    """Return a normalized repository-relative path or fail closed.

    This rejects absolute paths, traversal, NULs and paths whose existing
    symlink parents resolve outside the workspace. Sandbox implementations
    perform the final realpath check against their concrete root.
    """
    if not isinstance(path, str) or not path or "\x00" in path:
        raise WorkspaceViolation("Path must be a non-empty string")
    candidate = PurePosixPath(path.replace("\\", "/"))
    if candidate.is_absolute() or re.match(r"^[A-Za-z]:/", str(candidate)) or ".." in candidate.parts:
        raise WorkspaceViolation("Path must stay inside the repository workspace")
    normalized = str(candidate)
    if normalized in {"", "."}:
        return "."
    return normalized


def resolve_local_path(root: str, path: str, *, for_write: bool = False) -> str:
    relative = validate_relative_path(path)
    root_path = Path(root).resolve(strict=True)
    target = root_path / relative
    probe = target.parent if for_write and not target.exists() else target
    try:
        resolved_probe = probe.resolve(strict=probe.exists())
    except OSError as exc:
        raise WorkspaceViolation(f"Unable to resolve workspace path: {path}") from exc
    if os.path.commonpath((str(root_path), str(resolved_probe))) != str(root_path):
        raise WorkspaceViolation("Path escapes the repository workspace through a symlink")
    return str(target)
