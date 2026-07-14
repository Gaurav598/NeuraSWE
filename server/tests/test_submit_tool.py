import json

import pytest

from app.sandbox.types import ExecResult
from app.tools.base import ToolContext
from app.tools.submit_tool import SubmitSolutionTool


class FakeSandbox:
    workdir = "/tmp/fake"

    def __init__(self, test_result: ExecResult, diff: str) -> None:
        self.test_result = test_result
        self.diff = diff

    async def exec(self, command: str, *, timeout: int = 30) -> ExecResult:
        if "git diff --cached" in command:
            return ExecResult(stdout=self.diff, stderr="", exit_code=0)
        return self.test_result

    async def read_file(self, path: str) -> str:
        return json.dumps({"scripts": {"test": "pytest"}})

    async def write_file(self, path: str, content: str) -> None:
        pass

    async def file_exists(self, path: str) -> bool:
        return path == "package.json"

    async def destroy(self) -> None:
        pass


@pytest.mark.asyncio
async def test_submit_allows_pr_when_baseline_tests_already_failed():
    sandbox = FakeSandbox(
        ExecResult(stdout="FirebaseError: missing apiKey", stderr="", exit_code=1),
        diff="diff --git a/client/src/Socket.js b/client/src/Socket.js\n+const backendUrl = 'x';",
    )
    ctx = ToolContext(sandbox=sandbox, baseline_tests={"success": False, "exit_code": 1})

    result = await SubmitSolutionTool().run(ctx, {})

    assert result.submit is True
    assert result.metadata["summary"]["success"] is False
    assert "baseline tests were already failing" in result.output


@pytest.mark.asyncio
async def test_submit_blocks_new_test_failures_when_baseline_was_green():
    sandbox = FakeSandbox(
        ExecResult(stdout="Tests: 1 failed, 0 passed", stderr="", exit_code=1),
        diff="diff --git a/file b/file\n+change",
    )
    ctx = ToolContext(sandbox=sandbox, baseline_tests={"success": True, "exit_code": 0})

    result = await SubmitSolutionTool().run(ctx, {})

    assert result.submit is False
    assert result.is_error
    assert "Tests are failing" in result.error
