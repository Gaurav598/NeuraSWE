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
from app.security.archive import normalized_repository_tar
from app.security.workspace import validate_relative_path
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
            stdout = (out or b"").decode("utf-8", "replace")
            stderr = (err or b"").decode("utf-8", "replace")
            limit = settings.sandbox_output_limit_bytes
            truncated = len(stdout.encode()) + len(stderr.encode()) > limit
            if truncated:
                stdout = stdout[:limit]
                stderr = stderr[: max(0, limit - len(stdout))]
            return ExecResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=res.exit_code if res.exit_code is not None else -1,
                timed_out=res.exit_code == 124,
                truncated=truncated,
            )

        return await asyncio.to_thread(_run)

    async def read_file(self, path: str) -> str:
        target = self._abs(path)
        await self._ensure_confined(target)
        res = await self.exec(f"cat {shlex.quote(target)}")
        return res.stdout

    async def write_file(self, path: str, content: str) -> None:
        # Pipe through base64 to avoid any quoting/escaping problems.
        b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        target = self._abs(path)
        await self._ensure_confined(target, for_write=True)
        dirname = target.rsplit("/", 1)[0] if "/" in target else "."
        cmd = (
            f"mkdir -p {shlex.quote(dirname)} && "
            f"echo {shlex.quote(b64)} | base64 -d > {shlex.quote(target)}"
        )
        res = await self.exec(cmd)
        if not res.ok:
            raise RuntimeError(f"write_file failed: {res.stderr}")

    async def file_exists(self, path: str) -> bool:
        target = self._abs(path)
        try:
            await self._ensure_confined(target)
        except ValueError:
            return False
        res = await self.exec(f"test -f {shlex.quote(target)} && echo yes || echo no")
        return res.stdout.strip() == "yes"

    async def _ensure_confined(self, target: str, *, for_write: bool = False) -> None:
        probe = target.rsplit("/", 1)[0] if for_write else target
        command = (
            f"resolved=$(realpath -m -- {shlex.quote(probe)}) && "
            f"case \"$resolved\" in {shlex.quote(self.workdir)}|{shlex.quote(self.workdir)}/*) exit 0;; *) exit 77;; esac"
        )
        result = await self.exec(command)
        if result.exit_code != 0:
            raise ValueError("Path escapes the repository workspace through a symlink")

    async def seed_archive(self, archive: bytes) -> None:
        normalized = await asyncio.to_thread(normalized_repository_tar, archive)
        ok = await asyncio.to_thread(
            self._container.put_archive, self.workdir, normalized
        )
        if not ok:
            raise RuntimeError("Unable to seed sandbox workspace")

    def _abs(self, path: str) -> str:
        relative = validate_relative_path(path)
        return self.workdir if relative == "." else f"{self.workdir}/{relative}"

    def validate_path(self, path: str, *, for_write: bool = False) -> str:  # noqa: ARG002
        return self._abs(path)

    async def destroy(self) -> None:
        def _stop() -> None:
            try:
                self._container.stop(timeout=5)
            except Exception:  # AutoRemove handles cleanup; ignore races.
                pass

        await asyncio.to_thread(_stop)
        log.info("docker_sandbox_destroyed", container=self._container.id[:12])

    async def disable_network(self) -> None:
        """Disconnect bootstrap networking before executing repository code."""
        def _disconnect() -> None:
            try:
                self._client.api.disconnect_container_from_network(
                    self._container.id, "bridge", force=True
                )
            except Exception as exc:
                raise RuntimeError("Unable to enforce sandbox network isolation") from exc

        await asyncio.to_thread(_disconnect)
        log.info("docker_sandbox_network_disabled", container=self._container.id[:12])
