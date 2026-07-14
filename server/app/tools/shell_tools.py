"""Shell-oriented tools: grep, run_command, run_tests, git_diff."""

from __future__ import annotations

import json
import re
import shlex
from typing import Any

from app.tools.base import Tool, ToolContext, ToolResult

BLOCKED_COMMAND_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "rm -rf .",
    "rm -rf *",
    "mkfs",
    "dd if=",
    ":(){",
    "fork bomb",
    "> /dev/sd",
    "shutdown",
    "reboot",
    "curl | bash",
    "wget | bash",
]

SOURCE_GLOB = "*.{ts,tsx,js,jsx,py,java,go,rs,cpp,cc,c,h,hpp,rb,php,cs,kt,swift}"
PACKAGE_DIRS = ("client", "frontend", "web", "app", "server")


class GrepTool(Tool):
    name = "grep"
    description = (
        "Exact text/regex search across source files. Use for specific symbols, "
        "imports, or error messages. Optionally scope to a path."
    )

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        pattern = self._require(args, "pattern")
        path = args.get("path") or "."
        cmd = (
            f"grep -PrnI --include='{SOURCE_GLOB}' "
            f"--exclude-dir=node_modules --exclude-dir=.git "
            f"{shlex.quote(pattern)} {shlex.quote(path)} | head -50"
        )
        res = await ctx.sandbox.exec(cmd)
        if not res.ok and res.stderr.strip():
            return ToolResult(error=res.stderr.strip())
        if not res.stdout.strip():
            return ToolResult(output=f"No matches for pattern: {pattern}")
        return ToolResult(output=res.stdout)


class RunCommandTool(Tool):
    name = "run_command"
    description = (
        "Run a shell command in the repo directory (install deps, run scripts, check "
        "versions). Destructive commands are blocked."
    )

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        command = self._require(args, "command")
        lowered = command.lower()
        if any(b in lowered for b in BLOCKED_COMMAND_PATTERNS):
            return ToolResult(error="Command blocked for safety.")
        res = await ctx.sandbox.exec(command, timeout=60)
        out = res.stdout[:3000]
        if res.stderr:
            out += f"\n[stderr]\n{res.stderr[:1000]}"
        out += f"\n[exit code: {res.exit_code}]"
        return ToolResult(output=out, metadata={"exit_code": res.exit_code})


class RunTestsTool(Tool):
    name = "run_tests"
    description = "Run the project's test suite (auto-detected). Optionally target a test path."

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        test_path = args.get("test_path")
        cmd = await self._detect_command(ctx, test_path)
        if cmd is None:
            return ToolResult(error="Could not detect a test runner for this project.")
        res = await ctx.sandbox.exec(cmd, timeout=180)
        summary = _parse_test_summary(res.stdout + "\n" + res.stderr, res.exit_code)
        tail = (res.stdout + "\n" + res.stderr)[-3000:]
        return ToolResult(
            output=f"$ {cmd}\n{tail}\n\nSummary: {json.dumps(summary)}",
            metadata={"summary": summary, "command": cmd},
        )

    async def _detect_command(self, ctx: ToolContext, test_path: str | None) -> str | None:
        if test_path:
            owning_dir = test_path.split("/", 1)[0]
            if owning_dir in PACKAGE_DIRS:
                cmd = await self._npm_test_command(ctx, owning_dir, test_path)
                if cmd:
                    return cmd

        cmd = await self._npm_test_command(ctx, ".", test_path)
        if cmd:
            return cmd

        for package_dir in PACKAGE_DIRS:
            cmd = await self._npm_test_command(ctx, package_dir, test_path)
            if cmd:
                return cmd

        if await ctx.sandbox.file_exists("pytest.ini") or await ctx.sandbox.file_exists(
            "pyproject.toml"
        ) or await ctx.sandbox.file_exists("setup.py"):
            target = f" {test_path}" if test_path else ""
            return f"python -m pytest{target} -q"
        if await ctx.sandbox.file_exists("pom.xml"):
            return "mvn -q test"
        if await ctx.sandbox.file_exists("go.mod"):
            return "go test ./..."
        return None

    async def _npm_test_command(
        self, ctx: ToolContext, package_dir: str, test_path: str | None
    ) -> str | None:
        package_file = "package.json" if package_dir == "." else f"{package_dir}/package.json"
        if not await ctx.sandbox.file_exists(package_file):
            return None

        content = await ctx.sandbox.read_file(package_file)
        try:
            pkg = json.loads(content)
        except json.JSONDecodeError:
            return None

        script = pkg.get("scripts", {}).get("test")
        if not script or _is_placeholder_npm_test(script):
            return None

        scoped_path = _scope_test_path(package_dir, test_path)
        if test_path and scoped_path is None:
            return None

        command = _npm_test_invocation(script, scoped_path)
        command = f"([ -d node_modules ] || npm install) && {command}"
        if package_dir == ".":
            return command
        return f"cd {shlex.quote(package_dir)} && {command}"


class GitDiffTool(Tool):
    name = "git_diff"
    description = "Show the current diff of changes made so far."

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        res = await ctx.sandbox.exec("git add -A && git diff --cached")
        diff = res.stdout.strip()
        ctx.last_diff = diff
        return ToolResult(output=diff or "No changes yet.")


def _parse_test_summary(text: str, exit_code: int) -> dict[str, Any]:
    """Best-effort extraction of pass/fail counts across common runners."""
    passed = failed = None
    # pytest: "5 passed, 1 failed"
    m = re.search(r"(\d+)\s+passed", text)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", text)
    if m:
        failed = int(m.group(1))
    # jest: "Tests: 1 failed, 46 passed, 47 total"
    if passed is None:
        m = re.search(r"(\d+)\s+pass", text, re.IGNORECASE)
        passed = int(m.group(1)) if m else None
    if failed is None:
        m = re.search(r"(\d+)\s+fail", text, re.IGNORECASE)
        failed = int(m.group(1)) if m else None
    return {
        "passed": passed if passed is not None else "?",
        "failed": failed if failed is not None else (0 if exit_code == 0 else "?"),
        "success": exit_code == 0,
        "exit_code": exit_code,
    }


def _is_placeholder_npm_test(script: str) -> bool:
    lowered = script.lower()
    return "no test specified" in lowered and "exit 1" in lowered


def _scope_test_path(package_dir: str, test_path: str | None) -> str | None:
    if not test_path:
        return None
    if package_dir == ".":
        return test_path
    prefix = f"{package_dir}/"
    if test_path.startswith(prefix):
        return test_path[len(prefix):]
    return None


def _npm_test_invocation(script: str, test_path: str | None) -> str:
    if "react-scripts test" in script:
        target = f" {shlex.quote(test_path)}" if test_path else ""
        return f"CI=true npm test -- --watchAll=false{target}"
    target = f" -- {shlex.quote(test_path)}" if test_path else ""
    return f"npm test{target}"
