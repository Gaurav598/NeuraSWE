"""Tool registry: registration, lookup, dispatch, and prompt documentation."""

from __future__ import annotations

from typing import Any

from app.tools.base import Tool, ToolContext, ToolResult
from app.tools.fs_tools import (
    CreateFileTool,
    EditFileTool,
    ListDirectoryTool,
    ReadFileTool,
)
from app.tools.search_tool import SearchCodeTool
from app.tools.shell_tools import GitDiffTool, GrepTool, RunCommandTool, RunTestsTool
from app.tools.submit_tool import SubmitSolutionTool


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools: dict[str, Tool] = {t.name: t for t in tools}

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    async def dispatch(self, name: str, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(self._tools.keys())
            return ToolResult(
                error=f"Unknown tool '{name}'. Available tools: {available}"
            )
        try:
            return await tool.run(ctx, args or {})
        except ValueError as exc:
            return ToolResult(error=str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            return ToolResult(error=f"Tool '{name}' raised: {exc}")

    def describe(self) -> str:
        """Human-readable tool list for the system prompt."""
        return "\n".join(f"- {t.name}: {t.description}" for t in self._tools.values())


def build_default_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            SearchCodeTool(),
            GrepTool(),
            ReadFileTool(),
            ListDirectoryTool(),
            EditFileTool(),
            CreateFileTool(),
            RunCommandTool(),
            RunTestsTool(),
            GitDiffTool(),
            SubmitSolutionTool(),
        ]
    )
