"""GitHub webhook receiver."""

from __future__ import annotations

from fastapi import APIRouter, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import crud
from app.db.base import SessionLocal
from app.github.webhook import (
    DEFAULT_TRIGGER_LABEL,
    parse_issue_event,
    should_trigger,
    verify_signature,
)
from app.utils.logger import get_logger

log = get_logger("api.webhook")
router = APIRouter(prefix="/api/webhook", tags=["webhook"])


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> Response:
    raw = await request.body()
    if not verify_signature(raw, x_hub_signature_256):
        return Response(status_code=401, content="invalid signature")

    if x_github_event != "issues":
        return Response(status_code=200, content="ignored")

    body = await request.json()
    event = parse_issue_event(body)
    if event is None:
        return Response(status_code=200, content="ignored")

    async with SessionLocal() as session:
        trigger_label = await _trigger_label(session, event.owner, event.repo)
        if not should_trigger(event, trigger_label):
            return Response(status_code=200, content="not triggered")

        repo = await crud.upsert_repository(
            session, owner=event.owner, name=event.repo, installation_id=event.installation_id
        )
        run = await crud.create_run(
            session,
            repository_id=repo.id,
            issue_number=event.issue_number,
            issue_title=event.title,
            issue_body=event.body,
            model=settings.agent_model_name,
        )
        await session.commit()
        run_id = run.id

    await _dispatch(run_id)
    log.info("webhook_run_queued", run_id=run_id, issue=event.issue_number)
    return Response(status_code=202, content="queued")


async def _trigger_label(session: AsyncSession, owner: str, name: str) -> str:
    repo = await crud.get_repository_by_full_name(session, owner, name)
    if repo and repo.config.get("trigger_label"):
        return repo.config["trigger_label"]
    return DEFAULT_TRIGGER_LABEL


async def _dispatch(run_id: str) -> None:
    import asyncio

    from app.queue.config import enqueue_run

    try:
        await enqueue_run(run_id)
    except Exception as exc:
        log.warning("enqueue_failed_running_inline", error=str(exc))
        from app.queue.processor import process_run

        asyncio.create_task(process_run(run_id))
