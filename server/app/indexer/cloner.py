"""Git clone / pull operations for indexing (host-side, separate from sandbox)."""

from __future__ import annotations

import asyncio
import os
import tempfile

from app.utils.logger import get_logger

log = get_logger("indexer.cloner")


async def _run(cmd: list[str], cwd: str | None = None, timeout: int = 300) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


async def clone_repo(clone_url: str, dest: str | None = None) -> str:
    """Shallow-clone *clone_url* and return the local path."""
    dest = dest or tempfile.mkdtemp(prefix="neuraswe-index-")
    code, _, err = await _run(["git", "clone", "--depth", "1", clone_url, dest])
    if code != 0:
        raise RuntimeError(f"git clone failed: {err}")
    log.info("repo_cloned", dest=dest)
    return dest


async def head_sha(repo_path: str) -> str:
    code, out, _ = await _run(["git", "rev-parse", "HEAD"], cwd=repo_path, timeout=30)
    return out.strip() if code == 0 else ""


async def pull_latest(repo_path: str) -> str:
    await _run(["git", "pull", "--ff-only"], cwd=repo_path, timeout=120)
    return await head_sha(repo_path)


async def changed_files(repo_path: str, since_sha: str) -> list[str]:
    code, out, _ = await _run(
        ["git", "diff", "--name-only", since_sha, "HEAD"], cwd=repo_path, timeout=60
    )
    if code != 0:
        return []
    return [line for line in out.splitlines() if line.strip()]
