from typing import Any

import pytest

from app.agent.runtime import AgentRuntime, IssueInput
from app.agent.types import AgentStatus
from app.sandbox.types import ExecResult
from app.tools.base import Tool, ToolContext, ToolResult
from app.tools.registry import ToolRegistry


class FakeSandbox:
    workdir = "/tmp/fake"

    async def exec(self, command: str, *, timeout: int = 30) -> ExecResult:
        return ExecResult(stdout="", stderr="", exit_code=0)

    async def read_file(self, path: str) -> str:
        return ""

    async def write_file(self, path: str, content: str) -> None:
        pass

    async def file_exists(self, path: str) -> bool:
        return True

    async def destroy(self) -> None:
        pass


class FakeSandboxManager:
    async def create(self, *, clone_url: str | None, branch: str | None = None) -> FakeSandbox:
        return FakeSandbox()

    async def destroy(self, sandbox: FakeSandbox) -> None:
        await sandbox.destroy()


class FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.index = 0

    async def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> str:
        response = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        return response

    async def summarize(self, text: str, instruction: str) -> str:
        return "summary"


class PassingTestsTool(Tool):
    name = "run_tests"
    description = "fake tests"

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            output="tests pass",
            metadata={"summary": {"success": True, "passed": 1, "failed": 0, "exit_code": 0}},
        )


class EditFileToolFake(Tool):
    name = "edit_file"
    description = "fake edit"

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        if "path" not in args:
            return ToolResult(error="Missing required argument: 'path'")
        return ToolResult(output="edited")


@pytest.mark.asyncio
async def test_runtime_fails_fast_on_repeated_unknown_tools():
    runtime = AgentRuntime(
        sandbox_manager=FakeSandboxManager(),
        registry=ToolRegistry([PassingTestsTool(), EditFileToolFake()]),
        llm=FakeLLM(
            [
                '{"thought":"x","action":{"tool":"modify_code","args":{}}}',
                '{"thought":"x","action":{"tool":"modify_code","args":{}}}',
            ]
        ),
    )
    runtime.max_steps = 5

    result = await runtime.solve(IssueInput(number=1, title="bug", body="body"), clone_url=None)

    assert result.status == AgentStatus.FAILED
    assert "unsupported tool" in result.error_message.lower()


@pytest.mark.asyncio
async def test_runtime_fails_fast_on_repeated_parse_failures():
    runtime = AgentRuntime(
        sandbox_manager=FakeSandboxManager(),
        registry=ToolRegistry([PassingTestsTool(), EditFileToolFake()]),
        llm=FakeLLM(["not an action", "still not an action", "again not an action"]),
    )
    runtime.max_steps = 5

    result = await runtime.solve(IssueInput(number=1, title="bug", body="body"), clone_url=None)

    assert result.status == AgentStatus.FAILED
    assert "action protocol" in result.error_message.lower()
