"""Docker-backed sandbox.

Each issue gets its own container with the repo cloned inside. Resource limits
(memory, CPU) keep a runaway agent from harming the host. Tools execute commands
through ``exec`` which runs inside the container's working directory.
"""

from __future__ import annotations

import asyncio
import base64
import shlex

from app.config import settings
from app.sandbox.types import ExecResult, Sandbox
from app.utils.logger import get_logger

log = get_logger("sandbox.docker")

try:
    from docker.models.containers import Container  # type: ignore

    _HAS_DOCKER = True
except Exception:  # pragma: no cover
    _HAS_DOCKER = False
    Container = object  # type: ignore


class DockerSandbox(Sandbox):
    def __init__(self, client, container: Container) -> None:  # type: ignore[no-untyped-def]
        self._client = client
        self._container = container
        self.workdir = settings.sandbox_workdir

    @property
    def container(self):  # type: ignore[no-untyped-def]
        return self._container

    async def exec(self, command: str, *, timeout: int = 30) -> ExecResult:
        # docker-py exec is blocking; run it in a thread. ``timeout`` is enforced
        # by wrapping the in-container command with the coreutils `timeout`.
        wrapped = f"timeout {timeout} bash -lc {shlex.quote(command)}"

        def _run() -> ExecResult:
            res = self._container.exec_run(
                cmd=["bash", "-lc", wrapped],
                workdir=self.workdir,
                demux=True,
            )
            out, err = res.output if isinstance(res.output, tuple) else (res.output, None)
            return ExecResult(
                stdout=(out or b"").decode("utf-8", "replace"),
                stderr=(err or b"").decode("utf-8", "replace"),
                exit_code=res.exit_code if res.exit_code is not None else -1,
            )

        return await asyncio.to_thread(_run)

    async def read_file(self, path: str) -> str:
        res = await self.exec(f"cat {shlex.quote(self._abs(path))}")
        return res.stdout

    async def write_file(self, path: str, content: str) -> None:
        # Pipe through base64 to avoid any quoting/escaping problems.
        b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        target = self._abs(path)
        dirname = target.rsplit("/", 1)[0] if "/" in target else "."
        cmd = (
            f"mkdir -p {shlex.quote(dirname)} && "
            f"echo {shlex.quote(b64)} | base64 -d > {shlex.quote(target)}"
        )
        res = await self.exec(cmd)
        if not res.ok:
            raise RuntimeError(f"write_file failed: {res.stderr}")

    async def file_exists(self, path: str) -> bool:
        res = await self.exec(f"test -f {shlex.quote(self._abs(path))} && echo yes || echo no")
        return res.stdout.strip() == "yes"

    def _abs(self, path: str) -> str:
        if path.startswith("/"):
            return path
        return f"{self.workdir}/{path}"

    async def destroy(self) -> None:
        def _stop() -> None:
            try:
                self._container.stop(timeout=5)
            except Exception:  # AutoRemove handles cleanup; ignore races.
                pass

        await asyncio.to_thread(_stop)
        log.info("docker_sandbox_destroyed", container=self._container.id[:12])
