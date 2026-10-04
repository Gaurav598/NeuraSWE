"""Repository endpoints: list, connect, reindex, config."""

from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.db.base import get_session
from app.db.models import IndexStatus
from app.db.schemas import (
    GitHubIssueLabel,
    GitHubIssueOut,
    PaginatedGitHubIssues,
    RepoConfigUpdate,
    RepositoryOut,
)
from app.github.client import GitHubClient
from app.indexer.orchestrator import IndexOrchestrator
from app.security.auth import Principal, current_principal, require_owner
from app.utils.logger import get_logger

log = get_logger("api.repositories")
router = APIRouter(prefix="/api/repositories", tags=["repositories"])


class ConnectRepoRequest(BaseModel):
    owner: str
    name: str
    installation_id: int | None = None


@router.get("", response_model=list[RepositoryOut])
async def list_repositories(
    session: AsyncSession = Depends(get_session), principal: Principal = Depends(current_principal)
) -> list[RepositoryOut]:
    repos = await crud.list_repositories(session, owner_id=principal.user_id)
    return [RepositoryOut.model_validate(r) for r in repos]


@router.post("", response_model=RepositoryOut, status_code=201)
async def connect_repository(
    req: ConnectRepoRequest, session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(current_principal),
) -> RepositoryOut:
    gh = GitHubClient(installation_id=req.installation_id)
    try:
        metadata = await gh.get_repository(req.owner, req.name)
        permissions = metadata.get("permissions") or {}
        can_push = bool(
            permissions.get("push") or permissions.get("admin") or permissions.get("maintain")
        )
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Repository is not accessible with the configured GitHub integration") from exc
    repo = await crud.upsert_repository(
        session, owner=req.owner, name=req.name, installation_id=req.installation_id,
        owner_id=principal.user_id,
    )
    config = dict(repo.config or {})
    config.update({"integration_state": "connected", "can_push": can_push, "private": bool(metadata.get("private"))})
    repo.config = config
    await session.commit()
    asyncio.create_task(_index_repo(repo.id, repo.owner, repo.name, repo.installation_id))
    return RepositoryOut.model_validate(repo)


@router.post("/{repo_id}/reindex", status_code=202)
async def reindex(repo_id: str, session: AsyncSession = Depends(get_session), principal: Principal = Depends(current_principal)) -> dict:
    repo = await crud.get_repository(session, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    require_owner(repo.owner_id, principal)
    asyncio.create_task(_index_repo(repo.id, repo.owner, repo.name, repo.installation_id))
    return {"status": "indexing_started", "repo_id": repo_id}


@router.get("/{repo_id}/issues", response_model=PaginatedGitHubIssues)
async def list_repository_issues(
    repo_id: str,
    state: str = Query("open", pattern="^(open|closed|all)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(current_principal),
) -> PaginatedGitHubIssues:
    repo = await crud.get_repository(session, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    require_owner(repo.owner_id, principal)

    gh = GitHubClient(installation_id=repo.installation_id)
    try:
        rows = await gh.list_issues(
            repo.owner,
            repo.name,
            state=state,
            page=page,
            per_page=page_size,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            detail = "GitHub credentials are missing, invalid, or rate-limited"
        elif status == 404:
            detail = "GitHub repository not found or not accessible"
        else:
            detail = "Unable to fetch GitHub issues"
        raise HTTPException(status_code=status if status < 500 else 502, detail=detail) from exc

    issues = [_issue_out(row) for row in rows if "pull_request" not in row]
    return PaginatedGitHubIssues(
        items=issues,
        page=page,
        page_size=page_size,
        has_more=len(rows) == page_size,
    )


@router.patch("/{repo_id}/config", response_model=RepositoryOut)
async def update_config(
    repo_id: str, body: RepoConfigUpdate, session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(current_principal),
) -> RepositoryOut:
    repo = await crud.get_repository(session, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    require_owner(repo.owner_id, principal)
    config = dict(repo.config or {})
    config.update({k: v for k, v in body.model_dump().items() if v is not None})
    repo.config = config
    await session.flush()
    await session.commit()
    return RepositoryOut.model_validate(repo)


async def _index_repo(repo_id: str, owner: str, name: str, installation_id: int | None) -> None:
    from app.db.base import SessionLocal

    gh = GitHubClient(installation_id=installation_id)
    try:
        clone_url = await gh.clone_url(owner, name)
    except Exception:
        clone_url = f"https://github.com/{owner}/{name}.git"

    indexer = IndexOrchestrator()
    async with SessionLocal() as s:
        repo = await crud.get_repository(s, repo_id)
        if repo:
            await crud.set_index_status(s, repo, IndexStatus.INDEXING)
            await s.commit()
    try:
        async def progress(done: int, total: int) -> None:
            async with SessionLocal() as progress_session:
                current = await crud.get_repository(progress_session, repo_id)
                if current:
                    current.indexing_progress = int(done * 100 / max(total, 1))
                    await progress_session.commit()

        stats = await indexer.index_repository(repo_id, clone_url, progress=progress)
        async with SessionLocal() as s:
            repo = await crud.get_repository(s, repo_id)
            if repo:
                await crud.set_index_status(
                    s, repo, IndexStatus.READY,
                    files_indexed=stats["files"], last_indexed_sha=stats["sha"], indexing_progress=100,
                )
                await s.commit()
    except Exception as exc:
        log.warning("index_failed", repo_id=repo_id, error=str(exc))
        async with SessionLocal() as s:
            repo = await crud.get_repository(s, repo_id)
            if repo:
                await crud.set_index_status(s, repo, IndexStatus.FAILED, index_error=str(exc)[:2000])
                await s.commit()


def _issue_out(row: dict) -> GitHubIssueOut:
    user = row.get("user") or {}
    labels = [
        GitHubIssueLabel(name=label.get("name", ""), color=label.get("color"))
        for label in row.get("labels", [])
        if label.get("name")
    ]
    return GitHubIssueOut(
        number=row["number"],
        title=row.get("title") or f"Issue #{row['number']}",
        body=row.get("body") or "",
        state=row.get("state") or "open",
        author=user.get("login"),
        labels=labels,
        html_url=row.get("html_url", ""),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
