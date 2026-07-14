"""The ReAct agent runtime — the heart of NeuraSWE.

Loop: REASON (LLM thought) -> ACT (tool call) -> OBSERVE (tool result), repeated
until the agent submits a solution, gives up, or hits the step budget. Each step
is streamed via an optional async callback (used for Socket.IO + DB persistence).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.agent.context_manager import ContextManager
from app.agent.llm import ChatClient, build_chat_client
from app.agent.prompt_builder import PromptBuilder
from app.agent.response_parser import parse_response
from app.agent.trajectory import Trajectory
from app.agent.types import Action, AgentStatus, TrajectoryStep
from app.config import settings
from app.sandbox.manager import SandboxManager
from app.tools.base import CodeSearchFn, ToolContext
from app.tools.registry import ToolRegistry, build_default_registry
from app.utils.logger import get_logger

log = get_logger("agent.runtime")

MAX_PARSE_FAILURES = 3
MAX_UNSUPPORTED_TOOL_FAILURES = 2


@dataclass
class IssueInput:
    number: int
    title: str
    body: str
    labels: list[str] = field(default_factory=list)


@dataclass
class AgentResult:
    status: AgentStatus
    trajectory: Trajectory
    diff: str = ""
    baseline_tests: dict[str, Any] | None = None
    final_tests: dict[str, Any] | None = None
    error_message: str | None = None
    branch: str = ""
    duration_ms: int = 0


# Callback signature for streaming step lifecycle events.
StepCallback = Callable[[dict[str, Any]], Awaitable[None]]
StopCallback = Callable[[], Awaitable[bool]]


class AgentRunStopped(Exception):
    """Raised when the queue processor asks the agent loop to stop."""


class AgentRuntime:
    def __init__(
        self,
        *,
        sandbox_manager: SandboxManager | None = None,
        registry: ToolRegistry | None = None,
        llm: ChatClient | None = None,
    ) -> None:
        self.sandbox_manager = sandbox_manager or SandboxManager()
        self.registry = registry or build_default_registry()
        self.llm = llm or build_chat_client()
        self.prompt_builder = PromptBuilder(self.registry)
        self.context = ContextManager(self.llm)
        self.max_steps = settings.agent_max_steps

    async def solve(
        self,
        issue: IssueInput,
        *,
        clone_url: str | None,
        code_search: CodeSearchFn | None = None,
        on_step: StepCallback | None = None,
        should_stop: StopCallback | None = None,
    ) -> AgentResult:
        started = time.time()
        trajectory = Trajectory()
        branch = f"neuraswe/issue-{issue.number}"

        sandbox = await self.sandbox_manager.create(clone_url=clone_url, branch=None)
        ctx = ToolContext(sandbox=sandbox, code_search=code_search)

        try:
            await self._raise_if_stopped(should_stop)
            # Baseline tests + working branch.
            baseline = await self._baseline(ctx)
            await self._raise_if_stopped(should_stop)
            ctx.baseline_tests = baseline
            await sandbox.exec("git config user.email neuraswe@bot && git config user.name NeuraSWE")
            await self._raise_if_stopped(should_stop)
            await sandbox.exec(f"git checkout -b {branch}")

            await self._emit(on_step, {"type": "setup", "baseline": baseline, "branch": branch})
            await self._raise_if_stopped(should_stop)

            system_prompt = self.prompt_builder.system_prompt()
            issue_block = self.prompt_builder.issue_block(issue.title, issue.body, issue.labels)
            parse_failures = 0
            unsupported_tool_failures = 0

            for step_num in range(1, self.max_steps + 1):
                await self._raise_if_stopped(should_stop)
                step_started = time.time()

                user_prompt = self.prompt_builder.user_prompt(
                    issue_block=issue_block, trajectory=trajectory, baseline=baseline
                )
                token_count = self.context.count(system_prompt + user_prompt)

                # REASON + decide ACT (single LLM call returns both).
                raw = await self.llm.chat(system_prompt, user_prompt, max_tokens=1024)
                await self._raise_if_stopped(should_stop)
                parsed = parse_response(raw)
                thought = parsed.thought or "(no explicit reasoning)"
                action = parsed.action
                agent_name = _agent_for_action(action)

                await self._emit(
                    on_step,
                    {
                        "type": "think",
                        "step": step_num,
                        "agent_name": agent_name,
                        "thought": thought,
                        "status": "executing",
                    },
                )
                await self._raise_if_stopped(should_stop)

                # Handle parse failures / control actions.
                if action is None:
                    parse_failures += 1
                    observation = (
                        f"Could not parse an ACTION ({parsed.parse_error}). "
                        "Respond with a THOUGHT line and an ACTION line containing JSON."
                    )
                    trajectory.add(
                        TrajectoryStep(step_num, thought, None, observation, token_count=token_count)
                    )
                    await self._raise_if_stopped(should_stop)
                    await self._persist_step(on_step, step_num, agent_name, thought, None, observation,
                                             step_started, token_count)
                    if parse_failures >= MAX_PARSE_FAILURES:
                        return self._result(
                            AgentStatus.FAILED,
                            trajectory,
                            ctx,
                            baseline,
                            branch,
                            started,
                            error="Model repeatedly failed the action protocol.",
                        )
                    continue
                parse_failures = 0

                if action.tool in ("give_up", "cannot_solve"):
                    return self._result(
                        AgentStatus.GAVE_UP, trajectory, ctx, baseline, branch, started,
                        error="Agent declared it cannot solve the issue.",
                    )

                if action.tool not in self.registry.names():
                    unsupported_tool_failures += 1
                    observation = (
                        f"Unsupported tool '{action.tool}'. Available tools: "
                        f"{', '.join(self.registry.names())}."
                    )
                    trajectory.add(
                        TrajectoryStep(step_num, thought, action, observation, token_count=token_count)
                    )
                    await self._persist_step(
                        on_step, step_num, agent_name, thought, action, observation, step_started, token_count
                    )
                    if unsupported_tool_failures >= MAX_UNSUPPORTED_TOOL_FAILURES:
                        return self._result(
                            AgentStatus.FAILED,
                            trajectory,
                            ctx,
                            baseline,
                            branch,
                            started,
                            error=(
                                "Model repeatedly requested an unsupported tool. "
                                "Use a stronger hosted model or adjust the prompt/tool schema."
                            ),
                        )
                    continue
                unsupported_tool_failures = 0

                await self._emit(
                    on_step,
                    {
                        "type": "act",
                        "step": step_num,
                        "agent_name": agent_name,
                        "tool": action.tool,
                        "args": action.args,
                    },
                )
                await self._raise_if_stopped(should_stop)

                # ACT
                result = await self.registry.dispatch(action.tool, ctx, action.args)
                await self._raise_if_stopped(should_stop)

                # Submission gate.
                if action.tool == "submit_solution" and result.submit:
                    diff = ctx.last_diff
                    final_tests = result.metadata.get("summary")
                    observation = result.render()
                    trajectory.add(
                        TrajectoryStep(step_num, thought, action, observation, token_count=token_count)
                    )
                    await self._raise_if_stopped(should_stop)
                    await self._persist_step(on_step, step_num, agent_name, thought, action, observation,
                                             step_started, token_count)
                    return self._result(
                        AgentStatus.SOLVED, trajectory, ctx, baseline, branch, started,
                        diff=diff, final_tests=final_tests,
                    )

                observation = self.context.truncate_observation(result.render())

                # OBSERVE
                step = TrajectoryStep(
                    step_num, thought, action, observation,
                    duration_ms=int((time.time() - step_started) * 1000),
                    token_count=token_count,
                )
                trajectory.add(step)
                await self._raise_if_stopped(should_stop)
                await self._persist_step(on_step, step_num, agent_name, thought, action, observation,
                                         step_started, token_count)

                await self.context.maybe_compact(trajectory)

            return self._result(
                AgentStatus.TIMEOUT, trajectory, ctx, baseline, branch, started,
                error="Max steps reached without submitting a solution.",
            )
        finally:
            await self.sandbox_manager.destroy(sandbox)

    # ------------------------------------------------------------------ #
    async def _baseline(self, ctx: ToolContext) -> dict[str, Any]:
        tool = self.registry.get("run_tests")
        if tool is None:
            return {}
        result = await tool.run(ctx, {})
        return result.metadata.get("summary", {})

    def _result(
        self,
        status: AgentStatus,
        trajectory: Trajectory,
        ctx: ToolContext,
        baseline: dict | None,
        branch: str,
        started: float,
        *,
        diff: str = "",
        final_tests: dict | None = None,
        error: str | None = None,
    ) -> AgentResult:
        return AgentResult(
            status=status,
            trajectory=trajectory,
            diff=diff or ctx.last_diff,
            baseline_tests=baseline,
            final_tests=final_tests,
            error_message=error,
            branch=branch,
            duration_ms=int((time.time() - started) * 1000),
        )

    async def _emit(self, cb: StepCallback | None, payload: dict[str, Any]) -> None:
        if cb is not None:
            try:
                await cb(payload)
            except Exception as exc:  # pragma: no cover - never let UI break the loop
                log.warning("step_callback_failed", error=str(exc))

    async def _raise_if_stopped(self, should_stop: StopCallback | None) -> None:
        if should_stop is not None and await should_stop():
            raise AgentRunStopped("Run was stopped by user.")

    async def _persist_step(
        self,
        cb: StepCallback | None,
        step_num: int,
        agent_name: str,
        thought: str,
        action: Action | None,
        observation: str,
        started: float,
        token_count: int,
    ) -> None:
        await self._emit(
            cb,
            {
                "type": "observe",
                "step": step_num,
                "agent_name": agent_name,
                "thought": thought,
                "tool": action.tool if action else None,
                "args": action.args if action else None,
                "observation": observation,
                "duration_ms": int((time.time() - started) * 1000),
                "token_count": token_count,
                "status": "complete",
            },
        )


def _agent_for_action(action: Action | None) -> str:
    if action is None:
        return "Planner"
    if action.tool in {"search_code", "grep", "read_file"}:
        return "Researcher"
    if action.tool in {"edit_file", "create_file", "run_command"}:
        return "Coder"
    if action.tool == "run_tests":
        return "Tester"
    if action.tool == "git_diff":
        return "Reviewer"
    if action.tool == "submit_solution":
        return "PR Agent"
    return "Orchestrator"
