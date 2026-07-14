"""Local (host) sandbox.

Runs commands in a temporary directory on the host. This is NOT isolated and is
intended for development / CI where a Docker daemon isn't available. The Docker
sandbox should be preferred in production (see manager.py).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

from app.sandbox.types import ExecResult, Sandbox
from app.utils.logger import get_logger

log = get_logger("sandbox.local")


class LocalSandbox(Sandbox):
    def __init__(self, root: str) -> None:
        self.root = root
        self.workdir = root

    @classmethod
    async def create(cls) -> LocalSandbox:
        root = tempfile.mkdtemp(prefix="neuraswe-local-")
        log.info("local_sandbox_created", root=root)
        return cls(root)

    def _abs(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(self.workdir, path))

    async def exec(self, command: str, *, timeout: int = 30) -> ExecResult:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=self.workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return ExecResult(stdout="", stderr=f"Command timed out after {timeout}s", exit_code=124)
        return ExecResult(
            stdout=stdout.decode("utf-8", "replace"),
            stderr=stderr.decode("utf-8", "replace"),
            exit_code=proc.returncode if proc.returncode is not None else -1,
        )

    async def read_file(self, path: str) -> str:
        abs_path = self._abs(path)
        return await asyncio.to_thread(_read, abs_path)

    async def write_file(self, path: str, content: str) -> None:
        abs_path = self._abs(path)
        os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
        await asyncio.to_thread(_write, abs_path, content)

    async def file_exists(self, path: str) -> bool:
        return os.path.isfile(self._abs(path))

    async def destroy(self) -> None:
        await asyncio.to_thread(shutil.rmtree, self.root, True)
        log.info("local_sandbox_destroyed", root=self.root)


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
