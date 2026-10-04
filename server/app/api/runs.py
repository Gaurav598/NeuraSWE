"""Run endpoints: list, detail, stats, manual trigger."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import crud
from app.db.base import get_session
from app.db.models import Run, RunStatus
from app.db.schemas import (
    ManualRunRequest,
    PaginatedRuns,
    ReviewDecisionRequest,
    RunDetail,
    RunEventOut,
    RunSummary,
    StatsOut,
)
from app.github.client import GitHubClient
from app.metrics import increment
from app.queue.config import enqueue_run
from app.realtime.emitter import emit_run_event
from app.run_state import TERMINAL, is_active
from app.security.auth import Principal, current_principal, require_owner
from app.utils.logger import get_logger

log = get_logger("api.runs")
router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/stats", response_model=StatsOut)
async def get_stats(session: AsyncSession = Depends(get_session), principal: Principal = Depends(current_principal)) -> StatsOut:
    data = await crud.compute_stats(session, owner_id=principal.user_id)
    data["recent"] = [RunSummary.model_validate(r) for r in data["recent"]]
    return StatsOut(**data)


@router.get("", response_model=PaginatedRuns)
async def list_runs(
    repository_id: str | None = None,
    status: RunStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(current_principal),
) -> PaginatedRuns:
    rows, total = await crud.list_runs(
        session, repository_id=repository_id, status=status, page=page, page_size=page_size,
        owner_id=principal.user_id,
    )
    return PaginatedRuns(
        items=[RunSummary.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/failed")
async def delete_failed_runs(session: AsyncSession = Depends(get_session), principal: Principal = Depends(current_principal)) -> dict[str, int]:
    rows = (
        await session.execute(
            select(Run).where(Run.owner_id == principal.user_id, Run.status.in_([RunStatus.FAILED, RunStatus.TIMEOUT, RunStatus.TIMED_OUT, RunStatus.CANCELLED, RunStatus.REJECTED]))
        )
    ).scalars().all()

    for run in rows:
        await session.delete(run)

    await session.commit()
    return {"deleted": len(rows)}


@router.post("/stop-active", response_model=list[RunSummary])
async def stop_active_runs(session: AsyncSession = Depends(get_session), principal: Principal = Depends(current_principal)) -> list[RunSummary]:
    rows = (
        await session.execute(
            select(Run)
            .where(Run.owner_id == principal.user_id, Run.status.not_in(list(TERMINAL)))
            .with_for_update()
        )
    ).scalars().all()

    stopped: list[RunSummary] = []
    for run in rows:
        await _stop_run(session, run)
        stopped.append(RunSummary.model_validate(run))

    if stopped:
        await session.commit()
        for _ in stopped:
            await increment("runs_cancelled_total")
        for run in rows:
            await emit_run_event(run.id, "run:complete", {"status": RunStatus.CANCELLED.value, "pr_url": None})

    return stopped


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, session: AsyncSession = Depends(get_session), principal: Principal = Depends(current_principal)) -> RunDetail:
    run = await crud.get_run(session, run_id, with_steps=True)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    require_owner(run.owner_id, principal)
    return RunDetail.model_validate(run)


@router.get("/{run_id}/events", response_model=list[RunEventOut])
async def get_run_events(
    run_id: str, after_sequence: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(current_principal),
) -> list[RunEventOut]:
    from app.db.models import RunEvent

    run = await crud.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    require_owner(run.owner_id, principal)
    rows = (
        await session.execute(
            select(RunEvent).where(
                RunEvent.run_id == run_id, RunEvent.sequence > after_sequence
            ).order_by(RunEvent.sequence).limit(1000)
        )
    ).scalars().all()
    return [RunEventOut.model_validate(row) for row in rows]


@router.delete("/{run_id}")
async def delete_run(run_id: str, session: AsyncSession = Depends(get_session), principal: Principal = Depends(current_principal)) -> dict[str, str]:
    run = await crud.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    require_owner(run.owner_id, principal)
    if is_active(run.status):
        raise HTTPException(status_code=409, detail="Stop the run before deleting it")

    await session.delete(run)
    await session.commit()
    return {"deleted": run_id}


@router.post("/{run_id}/stop", response_model=RunSummary)
async def stop_run(run_id: str, session: AsyncSession = Depends(get_session), principal: Principal = Depends(current_principal)) -> RunSummary:
    run = (
        await session.execute(
            select(Run)
            .where(Run.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    require_owner(run.owner_id, principal)

    if await _stop_run(session, run):
        await session.commit()
        await increment("runs_cancelled_total")
        await emit_run_event(run_id, "run:complete", {"status": RunStatus.CANCELLED.value, "pr_url": None})

    return RunSummary.model_validate(run)


async def _stop_run(session: AsyncSession, run: Run) -> bool:
    if run.status in TERMINAL:
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
        status=RunStatus.CANCELLED,
        cancellation_requested_at=datetime.now(timezone.utc),
        duration_ms=duration_ms,
        error_message="Stopped by user.",
    )
    return True


@router.post("/manual", response_model=RunSummary, status_code=202)
async def trigger_manual(
    req: ManualRunRequest, session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(current_principal),
) -> RunSummary:
    repo = await crud.get_repository(session, req.repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    require_owner(repo.owner_id, principal)

    if req.idempotency_key:
        existing = await crud.get_run_by_idempotency(
            session, owner_id=principal.user_id, idempotency_key=req.idempotency_key
        )
        if existing is not None:
            if existing.status == RunStatus.QUEUED:
                await _dispatch(existing.id)
            return RunSummary.model_validate(existing)

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
        owner_id=principal.user_id,
        idempotency_key=req.idempotency_key,
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if not req.idempotency_key:
            raise
        existing = await crud.get_run_by_idempotency(
            session, owner_id=principal.user_id, idempotency_key=req.idempotency_key
        )
        if existing is None:
            raise
        if existing.status == RunStatus.QUEUED:
            await _dispatch(existing.id)
        return RunSummary.model_validate(existing)
    await increment("runs_created_total")
    await _dispatch(run.id)
    return RunSummary.model_validate(run)


@router.post("/{run_id}/review", response_model=RunSummary)
async def review_run(
    run_id: str, body: ReviewDecisionRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(current_principal),
) -> RunSummary:
    # Do permission/network checks without holding a row lock, then lock and
    # revalidate immediately before the state mutation.
    run = await crud.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    require_owner(run.owner_id, principal)
    decision = body.decision.strip().upper()
    if decision == "APPROVE" and run.approval_status == "APPROVED" and run.status in {
        RunStatus.PR_CREATING, RunStatus.COMPLETED,
    }:
        return RunSummary.model_validate(run)
    if run.status != RunStatus.AWAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="Run is not awaiting approval")
    if decision == "APPROVE":
        repo = await crud.get_repository(session, run.repository_id)
        if repo is None:
            raise HTTPException(status_code=404, detail="Repository not found")
        try:
            can_push = await GitHubClient(installation_id=repo.installation_id).can_push(
                repo.owner, repo.name
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Unable to verify GitHub repository permission") from exc
        if not can_push:
            raise HTTPException(status_code=403, detail="GitHub integration lacks push permission for this repository")

    run = (
        await session.execute(
            select(Run)
            .where(Run.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    require_owner(run.owner_id, principal)
    if decision == "APPROVE" and run.approval_status == "APPROVED" and run.status in {
        RunStatus.PR_CREATING, RunStatus.COMPLETED,
    }:
        return RunSummary.model_validate(run)
    if run.status != RunStatus.AWAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="Run is not awaiting approval")

    if decision == "APPROVE":
        await crud.update_run(
            session, run, status=RunStatus.PR_CREATING, approval_status="APPROVED",
            approval_comment=body.comment, approved_at=datetime.now(timezone.utc),
            pr_status="CREATING", error_message=None,
        )
    elif decision == "REJECT":
        await crud.update_run(
            session, run, status=RunStatus.REJECTED, approval_status="REJECTED",
            approval_comment=body.comment,
        )
    elif decision == "REQUEST_CHANGES":
        await crud.update_run(
            session, run, status=RunStatus.CHANGES_REQUESTED, approval_status="CHANGES_REQUESTED",
            approval_comment=body.comment, remote_branch=None, commit_sha=None,
        )
    else:
        raise HTTPException(status_code=422, detail="decision must be APPROVE, REJECT, or REQUEST_CHANGES")
    await session.commit()
    if decision == "APPROVE":
        from app.queue.config import enqueue_publish
        try:
            await enqueue_publish(run.id)
        except Exception as exc:
            if settings.is_production:
                log.error("publish_enqueue_failed", run_id=run.id, error=str(exc))
                await crud.update_run(
                    session, run, status=RunStatus.AWAITING_APPROVAL,
                    approval_status="PENDING", approved_at=None, pr_status="FAILED",
                    error_message="PR publication queue is unavailable; approval was not accepted.",
                )
                await session.commit()
                raise HTTPException(
                    status_code=503,
                    detail="PR publication queue is unavailable; retry approval later",
                ) from exc
            log.warning("publish_enqueue_failed_running_inline", run_id=run.id, error=str(exc))
            from app.queue.processor import publish_approved_run
            asyncio.create_task(publish_approved_run(run.id))
    elif decision == "REQUEST_CHANGES":
        await crud.update_run(session, run, status=RunStatus.QUEUED)
        await session.commit()
        await _dispatch(run.id)
    await emit_run_event(run.id, "run:review", {"decision": decision, "status": run.status.value})
    return RunSummary.model_validate(run)


async def _dispatch(run_id: str) -> None:
    """Enqueue via arq if Redis is reachable; otherwise run in-process."""
    try:
        await enqueue_run(run_id)
    except Exception as exc:
        if settings.is_production:
            log.error("enqueue_failed", run_id=run_id, error=str(exc))
            raise HTTPException(status_code=503, detail="Run queue is unavailable") from exc
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
