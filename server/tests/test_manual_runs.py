import pytest
from fastapi import HTTPException

from app.api import runs


class FakeGitHubClient:
    def __init__(self, installation_id=None) -> None:
        self.installation_id = installation_id

    async def get_issue(self, owner: str, repo: str, number: int) -> dict:
        assert owner == "octo"
        assert repo == "repo"
        assert number == 42
        return {"title": "Real bug title", "body": "Actual issue body"}


class FailingGitHubClient:
    def __init__(self, installation_id=None) -> None:
        self.installation_id = installation_id

    async def get_issue(self, owner: str, repo: str, number: int) -> dict:
        raise RuntimeError("github unavailable")


@pytest.mark.asyncio
async def test_fetch_issue_metadata_uses_real_github_issue(monkeypatch):
    monkeypatch.setattr(runs, "GitHubClient", FakeGitHubClient)

    title, body = await runs._fetch_issue_metadata("octo", "repo", 42, 123)

    assert title == "Real bug title"
    assert body == "Actual issue body"


@pytest.mark.asyncio
async def test_fetch_issue_metadata_fails_when_github_issue_cannot_be_loaded(monkeypatch):
    monkeypatch.setattr(runs, "GitHubClient", FailingGitHubClient)

    with pytest.raises(HTTPException) as exc:
        await runs._fetch_issue_metadata("octo", "repo", 42, None)

    assert exc.value.status_code == 502
    assert "Unable to fetch GitHub issue" in exc.value.detail
