import pytest

from app.github.pr_creator import PRCreator


class FakeGitHubClient:
    async def clone_url(self, owner: str, repo: str) -> str:
        return f"https://github.com/{owner}/{repo}.git"

    async def create_pull_request(self, owner: str, repo: str, *, title: str, head: str, base: str, body: str) -> dict:
        return {"number": 1, "html_url": "https://github.com/octo/repo/pull/1"}


class FakePRCreator(PRCreator):
    def __init__(self, git_results: dict[tuple[str, ...], int]) -> None:
        super().__init__(FakeGitHubClient())
        self.git_results = git_results
        self.commands: list[tuple[str, ...]] = []

    async def _git(self, args: list[str], cwd: str | None = None, check: bool = True) -> int:
        command = tuple(args)
        self.commands.append(command)
        code = self.git_results.get(command, 0)
        if check and code != 0:
            raise RuntimeError("git failed")
        return code


@pytest.mark.asyncio
async def test_pr_creator_raises_when_patch_cannot_be_applied():
    creator = FakePRCreator(
        {
            ("apply", "--whitespace=fix", ".neuraswe.patch"): 1,
            ("apply", "--3way", ".neuraswe.patch"): 1,
        }
    )

    with pytest.raises(RuntimeError, match="Unable to apply generated patch"):
        await creator.create(
            owner="octo",
            repo="repo",
            branch="neuraswe/issue-1",
            base="main",
            diff="diff --git a/a.txt b/a.txt\n",
            commit_message="fix",
            pr_title="fix",
            pr_body="body",
        )

    assert ("push", "-u", "origin", "neuraswe/issue-1") not in creator.commands


@pytest.mark.asyncio
async def test_pr_creator_raises_when_patch_creates_no_commit():
    creator = FakePRCreator({("commit", "-m", "fix"): 1})

    with pytest.raises(RuntimeError, match="No commit was created"):
        await creator.create(
            owner="octo",
            repo="repo",
            branch="neuraswe/issue-1",
            base="main",
            diff="diff --git a/a.txt b/a.txt\n",
            commit_message="fix",
            pr_title="fix",
            pr_body="body",
        )

    assert ("push", "-u", "origin", "neuraswe/issue-1") not in creator.commands
