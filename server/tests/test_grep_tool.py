import pytest

from app.sandbox.types import ExecResult
from app.tools.base import ToolContext
from app.tools.shell_tools import GrepTool


class FakeSandbox:
    workdir = "/tmp/fake"

    def __init__(self, result: ExecResult) -> None:
        self.result = result
        self.commands: list[str] = []

    async def exec(self, command: str, *, timeout: int = 30) -> ExecResult:
        self.commands.append(command)
        return self.result

    async def read_file(self, path: str) -> str:
        raise NotImplementedError

    async def write_file(self, path: str, content: str) -> None:
        raise NotImplementedError

    async def file_exists(self, path: str) -> bool:
        raise NotImplementedError

    async def destroy(self) -> None:
        pass


@pytest.mark.asyncio
async def test_grep_uses_perl_regex_for_common_llm_patterns():
    sandbox = FakeSandbox(ExecResult(stdout="client/src/Socket.js:10:return io(url);", stderr="", exit_code=0))

    result = await GrepTool().run(ToolContext(sandbox=sandbox), {"pattern": r"io\(.*?\)"})

    assert "client/src/Socket.js" in result.output
    assert "grep -PrnI" in sandbox.commands[0]


@pytest.mark.asyncio
async def test_grep_surfaces_regex_errors():
    sandbox = FakeSandbox(ExecResult(stdout="", stderr="grep: missing closing parenthesis", exit_code=2))

    result = await GrepTool().run(ToolContext(sandbox=sandbox), {"pattern": "("})

    assert result.is_error
    assert "missing closing parenthesis" in result.error
