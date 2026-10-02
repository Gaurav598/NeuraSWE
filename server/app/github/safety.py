"""Fail-closed checks applied before a generated patch can be published."""

from __future__ import annotations

import re

from app.security.workspace import WorkspaceViolation, validate_relative_path

SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)
BLOCKED_PATHS = {".npmrc", ".pypirc", "id_rsa", "id_ed25519"}


class UnsafePatch(ValueError):
    pass


def validate_patch_for_publication(diff: str) -> list[str]:
    if not diff.strip() or "diff --git " not in diff:
        raise UnsafePatch("Generated patch is empty or malformed")
    if re.search(r"^(?:new file mode|old mode) 120000$", diff, re.MULTILINE):
        raise UnsafePatch("Patch may not create or modify symbolic links")
    changed: list[str] = []
    for match in re.finditer(r"^diff --git a/(.+?) b/(.+)$", diff, re.MULTILINE):
        path = match.group(2)
        try:
            validate_relative_path(path)
        except WorkspaceViolation as exc:
            raise UnsafePatch("Patch contains a path outside the repository") from exc
        changed.append(path)
        basename = path.rsplit("/", 1)[-1]
        if basename in BLOCKED_PATHS or basename == ".env" or basename.startswith(".env."):
            raise UnsafePatch(f"Patch contains blocked credential file: {path}")
    if not changed:
        raise UnsafePatch("Patch does not identify modified files")
    additions = "\n".join(
        line[1:] for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    for pattern in SECRET_PATTERNS:
        if pattern.search(additions):
            raise UnsafePatch("Patch appears to introduce a credential or private key")
    return changed
