"""Jira webhook receiver.

Starts an NeuraSWE run when a Jira issue transitions into a configured
automation status (default: NeuraSWE).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import crud
from app.db.base import get_session
from app.db.models import Run, RunStatus
from app.queue.config import enqueue_run
from app.realtime.emitter import emit_run_event
from app.utils.logger import get_logger

log = get_logger("api.jira_webhook")
router = APIRouter(prefix="/api/webhook/jira", tags=["jira"])


@router.post("", status_code=202)
async def jira_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    secret: str | None = Query(default=None),
    x_neuraswe_secret: str | None = Header(default=None),
) -> dict[str, Any]:
    _verify_secret(secret or x_neuraswe_secret)
    payload = await _read_payload(request)

    if not _changed_to_auto_status(payload):
        return {"status": "ignored", "reason": "status_not_configured_for_neuraswe"}

    issue = payload.get("issue") or {}
    fields = issue.get("fields") or {}
    issue_key = issue.get("key")
    project_key = ((fields.get("project") or {}).get("key") or "").upper()
    if not issue_key or not project_key:
        raise HTTPException(status_code=400, detail="Jira payload is missing issue key/project")

    repo_target = settings.jira_repo_map.get(project_key)
    if repo_target is None:
        raise HTTPException(
            status_code=400,
            detail=f"No GitHub repo mapping configured for Jira project {project_key}",
        )
    owner, repo_name = repo_target

    existing = await crud.get_active_run_by_external_issue(
        session, source="jira", external_issue_key=issue_key
    )

    repo = await crud.upsert_repository(session, owner=owner, name=repo_name)
    title = fields.get("summary") or issue_key
    body = _jira_issue_body(issue)
    issue_number = _issue_number(issue_key)
    issue_url = _issue_url(issue_key)

    replaced_run_id = None
    if existing is not None:
        replaced_run_id = existing.id
        await _stop_existing_run(session, existing)

    run = await crud.create_run(
        session,
        repository_id=repo.id,
        issue_number=issue_number,
        issue_title=title,
        issue_body=body,
        model=settings.agent_model_name,
        source="jira",
        external_issue_key=issue_key,
        external_issue_url=issue_url,
    )
    await session.commit()
    if replaced_run_id is not None:
        await emit_run_event(
            replaced_run_id,
            "run:complete",
            {"status": RunStatus.FAILED.value, "pr_url": None},
        )
    await enqueue_run(run.id)
    log.info(
        "jira_run_queued",
        run_id=run.id,
        issue=issue_key,
        repo=f"{owner}/{repo_name}",
        replaced_run_id=replaced_run_id,
    )
    return {
        "status": "requeued" if replaced_run_id else "queued",
        "run_id": run.id,
        "issue_key": issue_key,
        "replaced_run_id": replaced_run_id,
    }


def _verify_secret(provided: str | None) -> None:
    if settings.jira_webhook_secret and provided != settings.jira_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid Jira webhook secret")


async def _read_payload(request: Request) -> dict[str, Any]:
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Jira webhook body is empty")

    try:
        parsed = await request.json()
        if isinstance(parsed, dict):
            return parsed
    except (JSONDecodeError, UnicodeDecodeError, ValueError):
        pass

    return _parse_text_payload(body.decode("utf-8", errors="replace"))


def _parse_text_payload(text: str) -> dict[str, Any]:
    headers: dict[str, str] = {}
    description_lines: list[str] = []
    in_description = False

    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip("\r")
        if in_description:
            description_lines.append(line)
            continue
        if line.strip() == "DESCRIPTION:":
            in_description = True
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            headers[key.strip().upper()] = value.strip()

    issue_key = headers.get("ISSUE_KEY", "")
    project_key = headers.get("PROJECT_KEY", "")
    status = headers.get("STATUS", "")
    summary = headers.get("SUMMARY", issue_key)
    description = "\n".join(description_lines).strip()

    if not issue_key or not project_key:
        raise HTTPException(
            status_code=400,
            detail="Plain-text Jira body must include ISSUE_KEY and PROJECT_KEY",
        )

    return {
        "issue": {
            "key": issue_key,
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": description,
                "status": {"name": status},
                "labels": [],
            },
        },
        "changelog": {"items": [{"field": "status", "toString": status}]},
    }


def _changed_to_auto_status(payload: dict[str, Any]) -> bool:
    targets = settings.jira_auto_status_list
    if not targets:
        return False

    changelog = payload.get("changelog") or {}
    for item in changelog.get("items") or []:
        if str(item.get("field", "")).lower() != "status":
            continue
        if str(item.get("toString", "")).strip().lower() in targets:
            return True
    fields = (payload.get("issue") or {}).get("fields") or {}
    status = (fields.get("status") or {}).get("name")
    return str(status or "").strip().lower() in targets


def _issue_number(issue_key: str) -> int:
    match = re.search(r"(\d+)$", issue_key)
    return int(match.group(1)) if match else 0


def _issue_url(issue_key: str) -> str | None:
    if not settings.jira_base_url:
        return None
    return f"{settings.jira_base_url.rstrip('/')}/browse/{issue_key}"


async def _stop_existing_run(session: AsyncSession, run: Run) -> None:
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
        error_message="Restarted by Jira NeuraSWE transition.",
    )


def _jira_issue_body(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    parts = [f"Jira issue: {issue.get('key', 'unknown')}"]
    if description := _textify(fields.get("description")):
        parts.append(f"Description:\n{description}")
    if labels := fields.get("labels"):
        parts.append(f"Labels: {', '.join(map(str, labels))}")
    if components := fields.get("components"):
        names = [c.get("name") for c in components if c.get("name")]
        if names:
            parts.append(f"Components: {', '.join(names)}")
    return "\n\n".join(parts)


def _textify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(filter(None, (_textify(item) for item in value))).strip()
    if isinstance(value, dict):
        if "text" in value:
            return str(value["text"]).strip()
        return _textify(value.get("content"))
    return str(value).strip()
