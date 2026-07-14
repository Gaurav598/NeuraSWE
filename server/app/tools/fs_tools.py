"""Filesystem-oriented tools: read_file, list_directory, edit_file, create_file."""

from __future__ import annotations

import shlex
from typing import Any

from app.tools.base import Tool, ToolContext, ToolResult

MAX_FILE_LINES = 200


class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Read a file's contents. Optionally specify start_line and end_line for large files."
    )

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        path = self._require(args, "path")
        start = args.get("start_line")
        end = args.get("end_line")
        if start and end:
            res = await ctx.sandbox.exec(f"sed -n '{int(start)},{int(end)}p' {shlex.quote(path)}")
            if not res.ok:
                return ToolResult(error=res.stderr.strip() or f"Could not read {path}")
            return ToolResult(output=res.stdout)

        res = await ctx.sandbox.exec(f"cat {shlex.quote(path)}")
        if not res.ok:
            return ToolResult(error=res.stderr.strip() or f"Could not read {path}")
        lines = res.stdout.split("\n")
        if len(lines) > MAX_FILE_LINES:
            shown = "\n".join(lines[:MAX_FILE_LINES])
            shown += (
                f"\n\n[... truncated: file has {len(lines)} lines. "
                "Use start_line/end_line to read specific sections.]"
            )
            return ToolResult(
                output=shown,
                metadata={"truncated": True, "total_lines": len(lines)},
            )
        return ToolResult(output=res.stdout)


class ListDirectoryTool(Tool):
    name = "list_directory"
    description = "List files and subdirectories (depth 2), skipping node_modules and .git."

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", ".")
        cmd = (
            f"find {shlex.quote(path)} -maxdepth 2 "
            "-not -path '*/node_modules/*' -not -path '*/.git/*' "
            "-not -path '*/dist/*' -not -path '*/build/*' | head -100"
        )
        res = await ctx.sandbox.exec(cmd)
        if not res.ok and not res.stdout:
            return ToolResult(error=res.stderr.strip() or f"Could not list {path}")
        return ToolResult(output=res.stdout or "(empty)")


class EditFileTool(Tool):
    name = "edit_file"
    description = (
        "Replace exact text in a file. old_text must appear exactly once. "
        "Read the file first to copy exact content."
    )

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        path = self._require(args, "path")
        old_text = self._require(args, "old_text")
        new_text = args.get("new_text", "")

        if not await ctx.sandbox.file_exists(path):
            return ToolResult(error=f"{path} does not exist. Use create_file to make a new file.")

        content = await ctx.sandbox.read_file(path)
        occurrences = content.count(old_text)
        if occurrences == 0:
            return ToolResult(
                error=f"old_text not found in {path}. Read the file first to get exact content."
            )
        if occurrences > 1:
            return ToolResult(
                error=f"old_text found {occurrences} times in {path}. "
                "Add surrounding context so it matches exactly once."
            )

        new_content = content.replace(old_text, new_text, 1)
        await ctx.sandbox.write_file(path, new_content)
        changed = len(old_text.split("\n"))
        return ToolResult(output=f"Successfully edited {path}. Replaced a {changed}-line block.")


class CreateFileTool(Tool):
    name = "create_file"
    description = "Create a new file with the given content. Fails if the file already exists."

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        path = self._require(args, "path")
        content = args.get("content", "")
        if await ctx.sandbox.file_exists(path):
            return ToolResult(error=f"{path} already exists. Use edit_file to modify it.")
        await ctx.sandbox.write_file(path, content)
        return ToolResult(output=f"Created {path} ({len(content.splitlines())} lines).")
