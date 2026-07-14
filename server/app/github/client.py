"""GitHub REST client.

Supports two auth modes:
- GitHub App (App ID + private key -> JWT -> installation token). Production path.
- Personal Access Token (GITHUB_PAT). Convenient for local testing.

Implemented directly over httpx + PyJWT to avoid heavy SDK dependencies.
"""

from __future__ import annotations

import time

import httpx
import jwt

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("github.client")

API = "https://api.github.com"


class GitHubClient:
    def __init__(self, installation_id: int | None = None) -> None:
        self.installation_id = installation_id
        self._token: str | None = None
        self._token_expires: float = 0.0

    # ----------------------------- auth ----------------------------- #
    def _app_jwt(self) -> str:
        private_key = _read_private_key()
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": settings.github_app_id}
        return jwt.encode(payload, private_key, algorithm="RS256")

    async def _installation_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        headers = {
            "Authorization": f"Bearer {self._app_jwt()}",
            "Accept": "application/vnd.github+json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{API}/app/installations/{self.installation_id}/access_tokens",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        self._token = data["token"]
        self._token_expires = time.time() + 50 * 60
        return self._token

    async def token(self) -> str:
        if settings.github_pat:
            return settings.github_pat
        if self.installation_id and settings.github_app_id:
            return await self._installation_token()
        raise RuntimeError("No GitHub credentials configured (set GITHUB_PAT or App creds).")

    async def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {await self.token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def clone_url(self, owner: str, repo: str) -> str:
        tok = await self.token()
        return f"https://x-access-token:{tok}@github.com/{owner}/{repo}.git"

    # ----------------------------- api ------------------------------ #
    async def get_issue(self, owner: str, repo: str, number: int) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{API}/repos/{owner}/{repo}/issues/{number}", headers=await self._headers()
            )
            resp.raise_for_status()
            return resp.json()

    async def list_issues(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        page: int = 1,
        per_page: int = 50,
    ) -> list[dict]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{API}/repos/{owner}/{repo}/issues",
                headers=await self._headers(),
                params={
                    "state": state,
                    "page": page,
                    "per_page": per_page,
                    "sort": "updated",
                    "direction": "desc",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def create_pull_request(
        self, owner: str, repo: str, *, title: str, head: str, base: str, body: str
    ) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{API}/repos/{owner}/{repo}/pulls",
                headers=await self._headers(),
                json={"title": title, "head": head, "base": base, "body": body},
            )
            resp.raise_for_status()
            return resp.json()

    async def create_issue_comment(
        self, owner: str, repo: str, number: int, body: str
    ) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{API}/repos/{owner}/{repo}/issues/{number}/comments",
                headers=await self._headers(),
                json={"body": body},
            )
            resp.raise_for_status()
            return resp.json()


def _read_private_key() -> str:
    with open(settings.github_private_key_path, encoding="utf-8") as fh:
        return fh.read()
