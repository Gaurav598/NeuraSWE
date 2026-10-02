"""Sandbox lifecycle management.

Creates a sandbox per issue and fails closed when isolation is unavailable.
Host execution is an explicit, development-only unsafe mode.
"""

from __future__ import annotations

import asyncio
import shlex

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
        self._use_local = settings.sandbox_use_local
        if self._use_local and (settings.is_production or not settings.sandbox_allow_unsafe_local):
            raise RuntimeError(
                "Unsafe local sandbox requires SANDBOX_ALLOW_UNSAFE_LOCAL=true and is forbidden in production"
            )
        self._client = None
        if not self._use_local and not _HAS_DOCKER:
            raise RuntimeError("Docker sandbox support is unavailable; refusing host execution")
        if not self._use_local:
            try:
                self._client = docker.from_env()
                self._client.ping()
            except Exception as exc:
                raise RuntimeError("Docker sandbox unavailable; refusing host execution") from exc

    @property
    def mode(self) -> str:
        return "local" if self._use_local else "docker"

    async def create(
        self, *, clone_url: str | None, branch: str | None = None,
        repository_archive: bytes | None = None,
    ) -> Sandbox:
        """Create a sandbox and clone *clone_url* into it (if provided)."""
        if self._use_local:
            sandbox: Sandbox = await LocalSandbox.create()
        else:
            sandbox = await self._create_docker()
        try:
            if repository_archive is not None:
                await sandbox.seed_archive(repository_archive)
                await sandbox.exec(
                    "git init && git config user.email neuraswe@bot && git config user.name NeuraSWE "
                    "&& git add -A && git commit -m 'NeuraSWE trusted baseline'",
                    timeout=120,
                )
                if settings.sandbox_network_mode == "none" and hasattr(sandbox, "disable_network"):
                    await sandbox.disable_network()  # type: ignore[attr-defined]
                await self._install_deps(sandbox)
            elif clone_url:
                await self._clone(sandbox, clone_url, branch)
                if settings.sandbox_network_mode == "none" and hasattr(sandbox, "disable_network"):
                    await sandbox.disable_network()  # type: ignore[attr-defined]
                await self._install_deps(sandbox)
            return sandbox
        except BaseException:
            await self.destroy(sandbox)
            raise

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
                # Bootstrap clone access is removed before repository code is run.
                network_mode="bridge" if settings.sandbox_network_mode == "none" else settings.sandbox_network_mode,
                pids_limit=settings.sandbox_pids_limit,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                read_only=True,
                tmpfs={
                    "/tmp": "rw,noexec,nosuid,size=128m",
                    settings.sandbox_workdir: f"rw,nosuid,size={settings.sandbox_disk_mb}m",
                },
                user="1000:1000",
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
            f"rm -rf {shlex.quote(wd)}/.repo && git clone --depth 50 {shlex.quote(clone_url)} {shlex.quote(wd)}/.repo && "
            f"shopt -s dotglob && mv {shlex.quote(wd)}/.repo/* {shlex.quote(wd)}/ 2>/dev/null; "
            f"mv {shlex.quote(wd)}/.repo/.* {shlex.quote(wd)}/ 2>/dev/null; rm -rf {shlex.quote(wd)}/.repo; true"
        )
        res = await sandbox.exec(cmd, timeout=300)
        if not res.ok and "already exists" not in res.stderr:
            log.warning("clone_warning", stderr=res.stderr[:500])
        if branch:
            await sandbox.exec(f"git checkout {shlex.quote(branch)}", timeout=60)

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
