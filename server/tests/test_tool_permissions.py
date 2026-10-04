import pytest

from app.sandbox.types import ExecResult
from app.tools.base import ToolContext, ToolPermission
from app.tools.registry import build_default_registry


class Sandbox:
    workdir = "/workspace"
    def validate_path(self, path: str, *, for_write: bool = False) -> str:
        return path
    async def exec(self, command: str, *, timeout: int = 30) -> ExecResult:
        return ExecResult("", "", 0)
    async def read_file(self, path: str) -> str:
        return ""
    async def write_file(self, path: str, content: str) -> None:
        return None
    async def file_exists(self, path: str) -> bool:
        return False
    async def destroy(self) -> None:
        return None


@pytest.mark.asyncio
async def test_shell_tool_requires_permission() -> None:
    ctx = ToolContext(sandbox=Sandbox(), allowed_permissions={ToolPermission.READ})
    result = await build_default_registry().dispatch("run_command", ctx, {"command": "pwd"})
    assert result.is_error
    assert "not permitted" in result.error


@pytest.mark.asyncio
async def test_unknown_arguments_fail_closed() -> None:
    ctx = ToolContext(sandbox=Sandbox())
    result = await build_default_registry().dispatch("read_file", ctx, {"path": "x", "surprise": True})
    assert result.is_error
    assert "Unknown arguments" in result.error
