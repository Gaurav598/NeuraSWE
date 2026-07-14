"""Run endpoints: list, detail, stats, manual trigger."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import crud
from app.db.base import get_session
from app.db.models import Run, RunStatus
from app.db.schemas import (
    ManualRunRequest,
    PaginatedRuns,
    RunDetail,
    RunSummary,
    StatsOut,
)
from app.github.client import GitHubClient
from app.queue.config import enqueue_run
from app.realtime.emitter import emit_run_event
from app.utils.logger import get_logger

log = get_logger("api.runs")
router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/stats", response_model=StatsOut)
async def get_stats(session: AsyncSession = Depends(get_session)) -> StatsOut:
    data = await crud.compute_stats(session)
    data["recent"] = [RunSummary.model_validate(r) for r in data["recent"]]
    return StatsOut(**data)


@router.get("", response_model=PaginatedRuns)
async def list_runs(
    repository_id: str | None = None,
    status: RunStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> PaginatedRuns:
    rows, total = await crud.list_runs(
        session, repository_id=repository_id, status=status, page=page, page_size=page_size
    )
    return PaginatedRuns(
        items=[RunSummary.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/failed")
async def delete_failed_runs(session: AsyncSession = Depends(get_session)) -> dict[str, int]:
    rows = (
        await session.execute(
            select(Run).where(Run.status.in_([RunStatus.FAILED, RunStatus.TIMEOUT]))
        )
    ).scalars().all()

    for run in rows:
        await session.delete(run)

    await session.commit()
    return {"deleted": len(rows)}


@router.post("/stop-active", response_model=list[RunSummary])
async def stop_active_runs(session: AsyncSession = Depends(get_session)) -> list[RunSummary]:
    rows = (
        await session.execute(
            select(Run).where(Run.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]))
        )
    ).scalars().all()

    stopped: list[RunSummary] = []
    for run in rows:
        await _stop_run(session, run)
        stopped.append(RunSummary.model_validate(run))

    if stopped:
        await session.commit()
        for run in rows:
            await emit_run_event(run.id, "run:complete", {"status": RunStatus.FAILED.value, "pr_url": None})

    return stopped


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, session: AsyncSession = Depends(get_session)) -> RunDetail:
    run = await crud.get_run(session, run_id, with_steps=True)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunDetail.model_validate(run)


@router.delete("/{run_id}")
async def delete_run(run_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    run = await crud.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status in (RunStatus.QUEUED, RunStatus.RUNNING):
        raise HTTPException(status_code=409, detail="Stop the run before deleting it")

    await session.delete(run)
    await session.commit()
    return {"deleted": run_id}


@router.post("/{run_id}/stop", response_model=RunSummary)
async def stop_run(run_id: str, session: AsyncSession = Depends(get_session)) -> RunSummary:
    run = await crud.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    if await _stop_run(session, run):
        await session.commit()
        await emit_run_event(run_id, "run:complete", {"status": RunStatus.FAILED.value, "pr_url": None})

    return RunSummary.model_validate(run)


async def _stop_run(session: AsyncSession, run: Run) -> bool:
    if run.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
        return False

    duration_ms = run.duration_ms
    if duration_ms is None and run.created_at is not None:
        created_at = run.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        duration_ms = int((datetime.now(timezone.utc) - created_at).total_seconds() * 1000)

    await crud.update_run(
        session,
        run,
        status=RunStatus.FAILED,
        duration_ms=duration_ms,
        error_message="Stopped by user.",
    )
    return True


@router.post("/manual", response_model=RunSummary, status_code=202)
async def trigger_manual(
    req: ManualRunRequest, session: AsyncSession = Depends(get_session)
) -> RunSummary:
    repo = await crud.get_repository(session, req.repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    issue_title, issue_body = await _fetch_issue_metadata(
        repo.owner, repo.name, req.issue_number, repo.installation_id
    )

    run = await crud.create_run(
        session,
        repository_id=repo.id,
        issue_number=req.issue_number,
        issue_title=issue_title,
        issue_body=issue_body,
        model=settings.agent_model_name,
    )
    await session.commit()
    await _dispatch(run.id)
    return RunSummary.model_validate(run)


async def _dispatch(run_id: str) -> None:
    """Enqueue via arq if Redis is reachable; otherwise run in-process."""
    try:
        await enqueue_run(run_id)
    except Exception as exc:
        log.warning("enqueue_failed_running_inline", error=str(exc))
        from app.queue.processor import process_run

        asyncio.create_task(process_run(run_id))


async def _fetch_issue_metadata(
    owner: str, repo: str, issue_number: int, installation_id: int | None
) -> tuple[str, str]:
    try:
        issue = await GitHubClient(installation_id=installation_id).get_issue(owner, repo, issue_number)
    except Exception as exc:
        log.warning(
            "manual_issue_fetch_failed",
            owner=owner,
            repo=repo,
            issue=issue_number,
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail="Unable to fetch GitHub issue") from exc

    title = issue.get("title") or f"Issue #{issue_number}"
    body = issue.get("body") or ""
    return title, body
