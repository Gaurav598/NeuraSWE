"""Tool base interface, shared context, and result type."""

from __future__ import annotations

import abc
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.sandbox.types import Sandbox


@dataclass
class ToolResult:
    """Structured outcome of a tool invocation.

    ``output`` is what the agent sees. ``error`` signals a recoverable problem
    the agent should reason about. ``submit`` / ``prevent_submit`` are control
    signals used only by ``submit_solution``.
    """

    output: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    submit: bool = False
    prevent_submit: bool = False

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def render(self) -> str:
        """Render to the text the agent observes."""
        if self.error:
            return f"ERROR: {self.error}"
        return self.output or "(no output)"


# A semantic search function injected by the runtime: query -> rendered results.
CodeSearchFn = Callable[[str, int], Awaitable[list[dict[str, Any]]]]


@dataclass
class ToolContext:
    """Everything a tool needs to do its job for one run."""

    sandbox: Sandbox
    code_search: CodeSearchFn | None = None
    baseline_tests: dict[str, Any] | None = None
    # Populated by submit_solution so the orchestrator can build a PR.
    last_diff: str = ""


class Tool(abc.ABC):
    name: str = ""
    description: str = ""

    @abc.abstractmethod
    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        ...

    def _require(self, args: dict[str, Any], key: str) -> Any:
        if key not in args or args[key] is None:
            raise ValueError(f"Missing required argument: '{key}'")
        return args[key]
