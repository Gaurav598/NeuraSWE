"""Tool base interface, shared context, and result type."""

from __future__ import annotations

import abc
import enum
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


class ToolPermission(str, enum.Enum):
    READ = "read"
    WORKSPACE_WRITE = "workspace_write"
    SHELL = "shell"
    GIT_MUTATION = "git_mutation"
    EXTERNAL_API = "external_api"
    DESTRUCTIVE = "destructive"


@dataclass
class ToolContext:
    """Everything a tool needs to do its job for one run."""

    sandbox: Sandbox
    code_search: CodeSearchFn | None = None
    baseline_tests: dict[str, Any] | None = None
    # Populated by submit_solution so the orchestrator can build a PR.
    last_diff: str = ""
    review_summary: dict[str, Any] = field(default_factory=dict)
    allowed_permissions: set[ToolPermission] = field(default_factory=lambda: {
        ToolPermission.READ, ToolPermission.WORKSPACE_WRITE,
        ToolPermission.SHELL, ToolPermission.GIT_MUTATION,
    })


class Tool(abc.ABC):
    name: str = ""
    description: str = ""
    permission: ToolPermission = ToolPermission.READ
    argument_types: dict[str, type] = {}
    required_arguments: set[str] = set()

    def validate_args(self, args: dict[str, Any]) -> None:
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be an object")
        unknown = set(args) - set(self.argument_types)
        if unknown:
            raise ValueError(f"Unknown arguments for {self.name}: {', '.join(sorted(unknown))}")
        missing = self.required_arguments - set(args)
        if missing:
            raise ValueError(f"Missing required argument: '{sorted(missing)[0]}'")
        for key, value in args.items():
            expected = self.argument_types[key]
            if value is not None and not isinstance(value, expected):
                raise ValueError(f"Argument '{key}' must be {expected.__name__}")

    @abc.abstractmethod
    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        ...

    def _require(self, args: dict[str, Any], key: str) -> Any:
        if key not in args or args[key] is None:
            raise ValueError(f"Missing required argument: '{key}'")
        return args[key]
