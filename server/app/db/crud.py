"""Data-access helpers for repositories, runs, and steps.

Kept framework-agnostic: every function takes an AsyncSession so it can be used
from API handlers, the queue worker, and the agent runtime alike.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import IndexStatus, Repository, Run, RunEvent, RunStatus, Step
from app.run_state import TERMINAL, assert_transition


# --------------------------------------------------------------------------- #
# Repositories
# --------------------------------------------------------------------------- #
async def get_repository(session: AsyncSession, repo_id: str) -> Repository | None:
    return await session.get(Repository, repo_id)


async def get_repository_by_full_name(
    session: AsyncSession, owner: str, name: str, *, owner_id: str = "local"
) -> Repository | None:
    stmt = select(Repository).where(
        Repository.owner_id == owner_id, Repository.owner == owner, Repository.name == name
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_repositories_by_full_name(
    session: AsyncSession, owner: str, name: str
) -> list[Repository]:
    """Return ownership records for webhook-to-principal resolution."""
    stmt = select(Repository).where(
        Repository.owner == owner, Repository.name == name
    ).order_by(Repository.created_at)
    return list((await session.execute(stmt)).scalars().all())


async def list_repositories(session: AsyncSession, *, owner_id: str = "local") -> list[Repository]:
    stmt = select(Repository).where(Repository.owner_id == owner_id).order_by(Repository.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def upsert_repository(
    session: AsyncSession,
    owner: str,
    name: str,
    installation_id: int | None = None,
    owner_id: str = "local",
) -> Repository:
    repo = await get_repository_by_full_name(session, owner, name, owner_id=owner_id)
    if repo is None:
        repo = Repository(owner=owner, name=name, installation_id=installation_id, owner_id=owner_id)
        session.add(repo)
        await session.flush()
    elif installation_id is not None:
        repo.installation_id = installation_id
    return repo


async def set_index_status(
    session: AsyncSession,
    repo: Repository,
    status: IndexStatus,
    *,
    files_indexed: int | None = None,
    last_indexed_sha: str | None = None,
    index_error: str | None = None,
    indexing_progress: int | None = None,
) -> None:
    repo.index_status = status
    if files_indexed is not None:
        repo.files_indexed = files_indexed
    if last_indexed_sha is not None:
        repo.last_indexed_sha = last_indexed_sha
    repo.index_error = index_error
    if indexing_progress is not None:
        repo.indexing_progress = max(0, min(100, indexing_progress))
    await session.flush()


# --------------------------------------------------------------------------- #
# Runs
# --------------------------------------------------------------------------- #
async def create_run(
    session: AsyncSession,
    *,
    repository_id: str,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    model: str,
    source: str = "github",
    external_issue_key: str | None = None,
    external_issue_url: str | None = None,
    owner_id: str = "local",
    idempotency_key: str | None = None,
) -> Run:
    if idempotency_key:
        existing = (
            await session.execute(select(Run).where(
                Run.owner_id == owner_id, Run.idempotency_key == idempotency_key
            ))
        ).scalar_one_or_none()
        if existing is not None:
            return existing
    run = Run(
        repository_id=repository_id,
        issue_number=issue_number,
        issue_title=issue_title,
        issue_body=issue_body,
        source=source,
        external_issue_key=external_issue_key,
        external_issue_url=external_issue_url,
        model=model,
        status=RunStatus.QUEUED,
        owner_id=owner_id,
        idempotency_key=idempotency_key,
    )
    session.add(run)
    await session.flush()
    return run


async def get_run_by_idempotency(
    session: AsyncSession, *, owner_id: str, idempotency_key: str
) -> Run | None:
    stmt = select(Run).where(
        Run.owner_id == owner_id, Run.idempotency_key == idempotency_key
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_run(session: AsyncSession, run_id: str, *, with_steps: bool = False) -> Run | None:
    if with_steps:
        stmt = select(Run).where(Run.id == run_id).options(selectinload(Run.steps))
        return (await session.execute(stmt)).scalar_one_or_none()
    return await session.get(Run, run_id)


async def list_runs(
    session: AsyncSession,
    *,
    repository_id: str | None = None,
    status: RunStatus | None = None,
    owner_id: str = "local",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Run], int]:
    stmt = select(Run).where(Run.owner_id == owner_id)
    count_stmt = select(func.count()).select_from(Run).where(Run.owner_id == owner_id)
    if repository_id:
        stmt = stmt.where(Run.repository_id == repository_id)
        count_stmt = count_stmt.where(Run.repository_id == repository_id)
    if status:
        stmt = stmt.where(Run.status == status)
        count_stmt = count_stmt.where(Run.status == status)

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = (
        stmt.order_by(Run.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return rows, total


async def get_active_run_by_external_issue(
    session: AsyncSession,
    *,
    source: str,
    external_issue_key: str,
) -> Run | None:
    stmt = (
        select(Run)
        .where(
            Run.source == source,
            Run.external_issue_key == external_issue_key,
            Run.status.not_in(list(TERMINAL)),
        )
        .order_by(Run.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def update_run(session: AsyncSession, run: Run, **fields: Any) -> Run:
    target = fields.get("status")
    if target is not None and target != run.status:
        assert_transition(run.status, target)
        run.state_version += 1
        now = datetime.now(timezone.utc)
        run.phase_started_at = now
        timestamps = dict(run.phase_timestamps or {})
        timestamps[target.value] = now.isoformat()
        run.phase_timestamps = timestamps
    for key, value in fields.items():
        setattr(run, key, value)
    if fields.get("status") in TERMINAL:
        if run.completed_at is None:
            run.completed_at = datetime.now(timezone.utc)
    await session.flush()
    return run


async def add_run_event(
    session: AsyncSession, run: Run, event_type: str, payload: dict[str, Any]
) -> RunEvent:
    run.event_sequence += 1
    event = RunEvent(
        run_id=run.id, sequence=run.event_sequence, event_type=event_type, payload=payload
    )
    session.add(event)
    await session.flush()
    return event


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #
async def add_step(
    session: AsyncSession,
    *,
    run_id: str,
    step_number: int,
    thought: str | None,
    tool_name: str | None,
    tool_args: dict | None,
    observation: str | None,
    agent_name: str | None = None,
    duration_ms: int | None = None,
    token_count: int | None = None,
) -> Step:
    step = Step(
        run_id=run_id,
        step_number=step_number,
        agent_name=agent_name,
        thought=thought,
        tool_name=tool_name,
        tool_args=tool_args,
        observation=observation,
        duration_ms=duration_ms,
        token_count=token_count,
    )
    session.add(step)
    await session.flush()
    return step


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #
async def compute_stats(session: AsyncSession, *, owner_id: str = "local") -> dict[str, Any]:
    owned = Run.owner_id == owner_id
    total = (await session.execute(select(func.count()).select_from(Run).where(owned))).scalar_one()
    solved = (
        await session.execute(
            select(func.count()).select_from(Run).where(owned, Run.status.in_([RunStatus.SOLVED, RunStatus.COMPLETED]))
        )
    ).scalar_one()
    failed = (
        await session.execute(
            select(func.count())
            .select_from(Run)
            .where(owned, Run.status.in_([RunStatus.FAILED, RunStatus.TIMEOUT, RunStatus.TIMED_OUT]))
        )
    ).scalar_one()
    in_progress = (
        await session.execute(
            select(func.count())
            .select_from(Run)
            .where(owned, Run.status.not_in(list(TERMINAL)))
        )
    ).scalar_one()

    avg_steps = (
        await session.execute(
            select(func.coalesce(func.avg(Run.total_steps), 0.0)).where(
                owned, Run.status.in_([RunStatus.SOLVED, RunStatus.COMPLETED])
            )
        )
    ).scalar_one()
    avg_duration = (
        await session.execute(
            select(func.coalesce(func.avg(Run.duration_ms), 0.0)).where(
                owned, Run.duration_ms.is_not(None)
            )
        )
    ).scalar_one()

    completed = solved + failed
    success_rate = (solved / completed) if completed else 0.0

    recent_rows = list(
        (
            await session.execute(select(Run).where(owned).order_by(Run.created_at.desc()).limit(10))
        ).scalars().all()
    )

    return {
        "total_runs": total,
        "solved": solved,
        "failed": failed,
        "in_progress": in_progress,
        "success_rate": round(success_rate, 4),
        "avg_steps": round(float(avg_steps), 2),
        "avg_duration_ms": round(float(avg_duration), 2),
        "recent": recent_rows,
    }
