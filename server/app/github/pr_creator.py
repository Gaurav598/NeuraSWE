"""Create a branch + PR from a captured unified diff.

The agent's sandbox is ephemeral, so rather than push from inside it, we apply
the captured diff to a fresh host-side clone and push. This keeps the agent and
the publishing step decoupled and lets us recreate a PR even after a run ends.
"""

from __future__ import annotations

import asyncio
import os
import signal
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
        existing_branch = await self.client.get_branch(owner, repo, branch)
        if existing_branch is not None:
            # The branch name is derived from the full immutable run id. Reuse
            # it after an ambiguous timeout instead of pushing a duplicate.
            pr = await self.client.create_pull_request(
                owner, repo, title=pr_title, head=branch, base=base, body=pr_body
            )
            pr["_neuraswe_commit_sha"] = (existing_branch.get("commit") or {}).get("sha")
            return pr
        clone_url = await self.client.clone_url(owner, repo)
        workdir = tempfile.mkdtemp(prefix="neuraswe-pr-")
        commit_sha = ""
        try:
            await self._git(["clone", "--depth", "1", "--branch", base, clone_url, workdir])
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
            commit_sha = await self._git_output(["rev-parse", "HEAD"], cwd=workdir)
            await self._git(["push", "-u", "origin", branch], cwd=workdir)
        finally:
            await asyncio.to_thread(_rmtree, workdir)

        pr = await self.client.create_pull_request(
            owner, repo, title=pr_title, head=branch, base=base, body=pr_body
        )
        pr["_neuraswe_commit_sha"] = commit_sha
        log.info("pr_created", owner=owner, repo=repo, number=pr.get("number"))
        return pr

    async def _git_output(self, args: list[str], cwd: str | None = None) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=cwd, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            start_new_session=True,
        )
        try:
            out, err = await proc.communicate()
        except asyncio.CancelledError:
            os.killpg(proc.pid, signal.SIGKILL)
            await proc.wait()
            raise
        if proc.returncode:
            raise RuntimeError(f"git {' '.join(args)} failed: {err.decode('utf-8', 'replace')}")
        return out.decode("utf-8", "replace").strip()

    async def _git(self, args: list[str], cwd: str | None = None, check: bool = True) -> int:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            start_new_session=True,
        )
        try:
            _, err = await proc.communicate()
        except asyncio.CancelledError:
            os.killpg(proc.pid, signal.SIGKILL)
            await proc.wait()
            raise
        code = proc.returncode or 0
        if check and code != 0:
            operation = args[0] if args else "operation"
            raise RuntimeError(f"git {operation} failed (stderr redacted, {len(err)} bytes)")
        return code


def _rmtree(path: str) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
