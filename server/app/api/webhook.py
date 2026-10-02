"""GitHub webhook receiver."""

from __future__ import annotations

from fastapi import APIRouter, Header, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import crud
from app.db.base import SessionLocal
from app.db.models import WebhookDelivery
from app.github.webhook import (
    DEFAULT_TRIGGER_LABEL,
    parse_issue_event,
    should_trigger,
    verify_signature,
)
from app.metrics import increment
from app.utils.logger import get_logger

log = get_logger("api.webhook")
router = APIRouter(prefix="/api/webhook", tags=["webhook"])


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
) -> Response:
    raw = await request.body()
    if not verify_signature(raw, x_hub_signature_256):
        return Response(status_code=401, content="invalid signature")

    if x_github_event != "issues":
        return Response(status_code=200, content="ignored")
    if not x_github_delivery:
        return Response(status_code=400, content="missing delivery id")

    body = await request.json()
    event = parse_issue_event(body)
    if event is None:
        return Response(status_code=200, content="ignored")

    async with SessionLocal() as session:
        session.add(WebhookDelivery(provider="github", delivery_id=x_github_delivery))
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            return Response(status_code=200, content="duplicate")
        repo = await _resolve_repository(session, event.owner, event.repo, event.installation_id)
        if repo is None:
            return Response(status_code=404, content="repository is not connected")
        trigger_label = repo.config.get("trigger_label") or DEFAULT_TRIGGER_LABEL
        if not should_trigger(event, trigger_label):
            return Response(status_code=200, content="not triggered")

        run = await crud.create_run(
            session,
            repository_id=repo.id,
            issue_number=event.issue_number,
            issue_title=event.title,
            issue_body=event.body,
            model=settings.agent_model_name,
            owner_id=repo.owner_id,
        )
        await session.commit()
        delivery = (
            await session.execute(
                select(WebhookDelivery).where(
                    WebhookDelivery.provider == "github",
                    WebhookDelivery.delivery_id == x_github_delivery,
                )
            )
        ).scalar_one()
        delivery.run_id = run.id
        await session.commit()
        run_id = run.id

    await _dispatch(run_id)
    await increment("runs_created_total")
    log.info("webhook_run_queued", run_id=run_id, issue=event.issue_number)
    return Response(status_code=202, content="queued")


async def _resolve_repository(
    session: AsyncSession, owner: str, name: str, installation_id: int | None
):
    matches = await crud.list_repositories_by_full_name(session, owner, name)
    if installation_id is not None:
        matches = [repo for repo in matches if repo.installation_id == installation_id]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        log.error(
            "ambiguous_webhook_repository_owner",
            owner=owner,
            repo=name,
            installation_id=installation_id,
        )
        return None
    if settings.is_production:
        return None
    # Local development remains convenient, but production never creates an
    # authorization record merely because an inbound issue names a repository.
    return await crud.upsert_repository(
        session, owner=owner, name=name, installation_id=installation_id, owner_id="local"
    )


async def _dispatch(run_id: str) -> None:
    import asyncio

    from app.queue.config import enqueue_run

    try:
        await enqueue_run(run_id)
    except Exception as exc:
        if settings.is_production:
            log.error("enqueue_failed", run_id=run_id, error=str(exc))
            return
        log.warning("enqueue_failed_running_inline", error=str(exc))
        from app.queue.processor import process_run

        asyncio.create_task(process_run(run_id))
