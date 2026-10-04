"""Local (host) sandbox.

Runs commands in a temporary directory on the host. This is NOT isolated and is
intended for development / CI where a Docker daemon isn't available. The Docker
sandbox should be preferred in production (see manager.py).
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import signal
import tarfile
import tempfile

from app.config import settings
from app.sandbox.types import ExecResult, Sandbox
from app.security.archive import normalized_repository_tar
from app.security.workspace import resolve_local_path
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
        return self.validate_path(path)

    def validate_path(self, path: str, *, for_write: bool = False) -> str:
        return resolve_local_path(self.root, path, for_write=for_write)

    async def exec(self, command: str, *, timeout: int = 30) -> ExecResult:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=self.workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={
                "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                "LANG": os.environ.get("LANG", "C.UTF-8"),
                "HOME": self.root,
                "TMPDIR": self.root,
                "GIT_TERMINAL_PROMPT": "0",
            },
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            os.killpg(proc.pid, signal.SIGKILL)
            await proc.wait()
            return ExecResult(stdout="", stderr=f"Command timed out after {timeout}s", exit_code=124, timed_out=True)
        except asyncio.CancelledError:
            os.killpg(proc.pid, signal.SIGKILL)
            await proc.wait()
            raise
        decoded_out = stdout.decode("utf-8", "replace")
        decoded_err = stderr.decode("utf-8", "replace")
        limit = settings.sandbox_output_limit_bytes
        truncated = len(stdout) + len(stderr) > limit
        if truncated:
            decoded_out = decoded_out[:limit]
            decoded_err = decoded_err[: max(0, limit - len(decoded_out))]
        return ExecResult(
            stdout=decoded_out,
            stderr=decoded_err,
            exit_code=proc.returncode if proc.returncode is not None else -1,
            truncated=truncated,
        )

    async def read_file(self, path: str) -> str:
        abs_path = self.validate_path(path, for_write=True)
        return await asyncio.to_thread(_read, abs_path)

    async def write_file(self, path: str, content: str) -> None:
        abs_path = self._abs(path)
        os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
        await asyncio.to_thread(_write, abs_path, content)

    async def file_exists(self, path: str) -> bool:
        return os.path.isfile(self._abs(path))

    async def seed_archive(self, archive: bytes) -> None:
        normalized = await asyncio.to_thread(normalized_repository_tar, archive)

        def _extract() -> None:
            with tarfile.open(fileobj=io.BytesIO(normalized), mode="r:") as bundle:
                bundle.extractall(self.root)

        await asyncio.to_thread(_extract)

    async def destroy(self) -> None:
        await asyncio.to_thread(shutil.rmtree, self.root, True)
        log.info("local_sandbox_destroyed", root=self.root)


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
