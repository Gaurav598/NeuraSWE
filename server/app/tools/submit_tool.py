"""submit_solution — final gate. Runs tests, captures the diff, signals the
orchestrator to open a PR only if tests pass.
"""

from __future__ import annotations

from typing import Any

from app.tools.base import Tool, ToolContext, ToolPermission, ToolResult
from app.tools.shell_tools import GitDiffTool, RunTestsTool
from app.verification import compare_verification


class SubmitSolutionTool(Tool):
    name = "submit_solution"
    description = (
        "Submit your solution. Only call when confident and tests pass. Runs the "
        "test suite one final time and prepares a patch for human review."
    )
    permission = ToolPermission.GIT_MUTATION
    argument_types = {"root_cause": str, "solution": str, "risks": list}
    required_arguments = {"root_cause", "solution"}

    def __init__(self) -> None:
        self._tests = RunTestsTool()
        self._diff = GitDiffTool()

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        ctx.review_summary = {
            "root_cause": args["root_cause"][:4000],
            "proposed_solution": args["solution"][:4000],
            "risks": [str(risk)[:1000] for risk in args.get("risks", [])[:20]],
        }
        test_result = await self._tests.run(ctx, {})
        summary = test_result.metadata.get(
            "summary", {"classification": "UNEXECUTED", "success": None, "failed_tests": []}
        )
        comparison = compare_verification(ctx.baseline_tests, summary)
        baseline_failed = bool(ctx.baseline_tests and ctx.baseline_tests.get("success") is False)
        if summary.get("success") is False and (not baseline_failed or comparison["regression"]):
            return ToolResult(
                error="Tests are failing — fix them before submitting.\n" + test_result.output,
                prevent_submit=True,
            )

        diff_result = await self._diff.run(ctx, {})
        diff = diff_result.output
        if not diff or diff == "No changes yet.":
            return ToolResult(
                error="No changes detected. Make a fix before submitting.",
                prevent_submit=True,
            )

        ctx.last_diff = diff
        if summary.get("success") is False and baseline_failed:
            return ToolResult(
                output=(
                    "Solution submitted. Final tests still fail, but baseline tests "
                    "were already failing before the change. The patch will be held "
                    "for review with the failing test context."
                ),
                submit=True,
                metadata={"summary": summary, "diff": diff, "baseline_failed": True, "comparison": comparison},
            )

        return ToolResult(
            output="Solution submitted. Tests pass. The patch is ready for human review.",
            submit=True,
            metadata={"summary": summary, "diff": diff, "comparison": comparison},
        )
