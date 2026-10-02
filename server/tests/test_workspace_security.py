from pathlib import Path

import pytest

from app.security.workspace import WorkspaceViolation, resolve_local_path, validate_relative_path


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "a/../../secret", "C:\\secrets"])
def test_rejects_paths_outside_workspace(path: str) -> None:
    with pytest.raises(WorkspaceViolation):
        validate_relative_path(path)


def test_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-secret"
    outside.write_text("secret")
    (tmp_path / "link").symlink_to(outside)
    with pytest.raises(WorkspaceViolation):
        resolve_local_path(str(tmp_path), "link")


def test_accepts_normal_workspace_path(tmp_path: Path) -> None:
    assert resolve_local_path(str(tmp_path), "src/new.py", for_write=True).startswith(str(tmp_path))
