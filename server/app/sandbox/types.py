"""Sandbox shared types and the abstract Sandbox interface."""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class Sandbox(abc.ABC):
    """A working copy of a repository the agent can read, edit, and run.

    Implementations: DockerSandbox (isolated container) and LocalSandbox
    (host temp dir, for environments without a Docker daemon).
    """

    workdir: str

    @abc.abstractmethod
    async def exec(self, command: str, *, timeout: int = 30) -> ExecResult:
        """Run a shell command inside the sandbox working directory."""

    @abc.abstractmethod
    async def read_file(self, path: str) -> str:
        ...

    @abc.abstractmethod
    async def write_file(self, path: str, content: str) -> None:
        ...

    @abc.abstractmethod
    async def file_exists(self, path: str) -> bool:
        ...

    @abc.abstractmethod
    async def destroy(self) -> None:
        ...
