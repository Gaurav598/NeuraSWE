"""Sandbox lifecycle management.

Creates a sandbox per issue, clones the repo into it, installs dependencies, and
returns a ready-to-use :class:`Sandbox`. Chooses Docker by default and falls
back to a local sandbox when ``SANDBOX_USE_LOCAL`` is set or Docker is absent.
"""

from __future__ import annotations

import asyncio

from app.config import settings
from app.sandbox.local import LocalSandbox
from app.sandbox.types import Sandbox
from app.utils.logger import get_logger

log = get_logger("sandbox.manager")

try:
    import docker  # type: ignore

    _HAS_DOCKER = True
except Exception:  # pragma: no cover
    _HAS_DOCKER = False


class SandboxManager:
    def __init__(self) -> None:
        self._use_local = settings.sandbox_use_local or not _HAS_DOCKER
        self._client = None
        if not self._use_local:
            try:
                self._client = docker.from_env()
                self._client.ping()
            except Exception as exc:  # daemon not reachable -> fall back
                log.warning("docker_unavailable_falling_back_to_local", error=str(exc))
                self._use_local = True

    @property
    def mode(self) -> str:
        return "local" if self._use_local else "docker"

    async def create(self, *, clone_url: str | None, branch: str | None = None) -> Sandbox:
        """Create a sandbox and clone *clone_url* into it (if provided)."""
        if self._use_local:
            sandbox: Sandbox = await LocalSandbox.create()
        else:
            sandbox = await self._create_docker()

        if clone_url:
            await self._clone(sandbox, clone_url, branch)
            await self._install_deps(sandbox)
        return sandbox

    async def _create_docker(self) -> Sandbox:
        from app.sandbox.docker_sandbox import DockerSandbox

        def _spawn():  # type: ignore[no-untyped-def]
            mem_bytes = settings.sandbox_memory_mb * 1024 * 1024
            container = self._client.containers.run(
                image=settings.sandbox_image,
                command=["sleep", "infinity"],
                working_dir=settings.sandbox_workdir,
                detach=True,
                auto_remove=True,
                mem_limit=mem_bytes,
                nano_cpus=int(settings.sandbox_cpu_cores * 1_000_000_000),
                network_mode="bridge",
                tty=False,
            )
            return container

        container = await asyncio.to_thread(_spawn)
        log.info("docker_sandbox_created", container=container.id[:12])
        return DockerSandbox(self._client, container)

    async def _clone(self, sandbox: Sandbox, clone_url: str, branch: str | None) -> None:
        wd = sandbox.workdir
        # Clone into a temp dir then move contents so workdir is the repo root.
        cmd = (
            f"rm -rf {wd}/.repo && git clone --depth 50 {clone_url} {wd}/.repo && "
            f"shopt -s dotglob && mv {wd}/.repo/* {wd}/ 2>/dev/null; "
            f"mv {wd}/.repo/.* {wd}/ 2>/dev/null; rm -rf {wd}/.repo; true"
        )
        res = await sandbox.exec(cmd, timeout=300)
        if not res.ok and "already exists" not in res.stderr:
            log.warning("clone_warning", stderr=res.stderr[:500])
        if branch:
            await sandbox.exec(f"git checkout {branch}", timeout=60)

    async def _install_deps(self, sandbox: Sandbox) -> None:
        """Best-effort dependency install based on detected manifest."""
        if await sandbox.file_exists("package.json"):
            log.info("installing_npm_deps")
            await sandbox.exec("npm install --no-audit --no-fund", timeout=600)
        elif await sandbox.file_exists("requirements.txt"):
            log.info("installing_pip_deps")
            await sandbox.exec(
                "pip install -r requirements.txt --break-system-packages || "
                "pip install -r requirements.txt",
                timeout=600,
            )
        elif await sandbox.file_exists("pyproject.toml"):
            await sandbox.exec("pip install -e . --break-system-packages || pip install -e .", timeout=600)

    async def destroy(self, sandbox: Sandbox) -> None:
        await sandbox.destroy()
