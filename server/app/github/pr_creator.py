"""Create a branch + PR from a captured unified diff.

The agent's sandbox is ephemeral, so rather than push from inside it, we apply
the captured diff to a fresh host-side clone and push. This keeps the agent and
the publishing step decoupled and lets us recreate a PR even after a run ends.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from app.github.client import GitHubClient
from app.utils.logger import get_logger

log = get_logger("github.pr_creator")


class PRCreator:
    def __init__(self, client: GitHubClient) -> None:
        self.client = client

    async def create(
        self,
        *,
        owner: str,
        repo: str,
        branch: str,
        base: str,
        diff: str,
        commit_message: str,
        pr_title: str,
        pr_body: str,
    ) -> dict:
        clone_url = await self.client.clone_url(owner, repo)
        workdir = tempfile.mkdtemp(prefix="neuraswe-pr-")
        try:
            await self._git(["clone", "--depth", "1", clone_url, workdir])
            await self._git(["checkout", "-b", branch], cwd=workdir)

            patch_path = os.path.join(workdir, ".neuraswe.patch")
            with open(patch_path, "w", encoding="utf-8") as fh:
                fh.write(diff if diff.endswith("\n") else diff + "\n")

            applied = await self._git(
                ["apply", "--whitespace=fix", ".neuraswe.patch"], cwd=workdir, check=False
            )
            if applied != 0:
                # Fall back to a 3-way apply for fuzzier patches.
                applied = await self._git(["apply", "--3way", ".neuraswe.patch"], cwd=workdir, check=False)
            if applied != 0:
                raise RuntimeError("Unable to apply generated patch")
            os.remove(patch_path)

            await self._git(["config", "user.email", "neuraswe@bot"], cwd=workdir)
            await self._git(["config", "user.name", "NeuraSWE"], cwd=workdir)
            await self._git(["add", "-A"], cwd=workdir)
            committed = await self._git(["commit", "-m", commit_message], cwd=workdir, check=False)
            if committed != 0:
                raise RuntimeError("No commit was created from generated patch")
            await self._git(["push", "-u", "origin", branch], cwd=workdir)
        finally:
            await asyncio.to_thread(_rmtree, workdir)

        pr = await self.client.create_pull_request(
            owner, repo, title=pr_title, head=branch, base=base, body=pr_body
        )
        log.info("pr_created", owner=owner, repo=repo, number=pr.get("number"))
        return pr

    async def _git(self, args: list[str], cwd: str | None = None, check: bool = True) -> int:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        _, err = await proc.communicate()
        code = proc.returncode or 0
        if check and code != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {err.decode('utf-8', 'replace')}")
        return code


def _rmtree(path: str) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
