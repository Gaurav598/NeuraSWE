import json

import pytest

from app.sandbox.types import ExecResult
from app.tools.base import ToolContext
from app.tools.shell_tools import RunTestsTool


class FakeSandbox:
    workdir = "/tmp/fake"

    def __init__(self, files: dict[str, str]) -> None:
        self.files = files
        self.commands: list[str] = []

    async def exec(self, command: str, *, timeout: int = 30) -> ExecResult:
        self.commands.append(command)
        return ExecResult(stdout="Tests: 1 passed, 1 total", stderr="", exit_code=0)

    async def read_file(self, path: str) -> str:
        return self.files[path]

    async def write_file(self, path: str, content: str) -> None:
        self.files[path] = content

    async def file_exists(self, path: str) -> bool:
        return path in self.files

    async def destroy(self) -> None:
        pass


def package_json(test_script: str) -> str:
    return json.dumps({"scripts": {"test": test_script}})


@pytest.mark.asyncio
async def test_run_tests_ignores_root_placeholder_and_uses_client_package():
    sandbox = FakeSandbox(
        {
            "package.json": package_json('echo "Error: no test specified" && exit 1'),
            "client/package.json": package_json("react-scripts test"),
        }
    )

    result = await RunTestsTool().run(ToolContext(sandbox=sandbox), {})

    assert (
        result.metadata["command"]
        == "cd client && ([ -d node_modules ] || npm install) && CI=true npm test -- --watchAll=false"
    )
    assert sandbox.commands == [result.metadata["command"]]


@pytest.mark.asyncio
async def test_run_tests_scopes_client_test_path_to_client_package():
    sandbox = FakeSandbox(
        {
            "package.json": package_json('echo "Error: no test specified" && exit 1'),
            "client/package.json": package_json("react-scripts test"),
        }
    )

    result = await RunTestsTool().run(
        ToolContext(sandbox=sandbox), {"test_path": "client/src/__tests__/Socket.test.js"}
    )

    assert (
        result.metadata["command"]
        == "cd client && ([ -d node_modules ] || npm install) && CI=true npm test -- --watchAll=false src/__tests__/Socket.test.js"
    )
