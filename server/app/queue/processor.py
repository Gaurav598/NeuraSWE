"""End-to-end run processor: index -> agent loop -> PR creation.

Runs inside the arq worker. Also importable + callable directly (the manual
trigger endpoint awaits it in a background task for environments without a
separate worker process).
"""

from __future__ import annotations

import time

from app.agent.runtime import AgentRunStopped, AgentRuntime, IssueInput
from app.agent.types import AgentStatus
from app.config import settings
from app.db import crud
from app.db.base import SessionLocal
from app.db.models import IndexStatus, RunStatus
from app.github.client import GitHubClient
from app.github.pr_creator import PRCreator
from app.github.pr_description import build_pr_description
from app.indexer.orchestrator import IndexOrchestrator
from app.realtime.emitter import emit_run_event
from app.utils.logger import get_logger

log = get_logger("queue.processor")

_STATUS_MAP = {
    AgentStatus.SOLVED: RunStatus.SOLVED,
    AgentStatus.FAILED: RunStatus.FAILED,
    AgentStatus.TIMEOUT: RunStatus.TIMEOUT,
    AgentStatus.GAVE_UP: RunStatus.FAILED,
}


class RunStopped(Exception):
    """Raised when a user stops a queued or running job."""


async def process_run(run_id: str, *, indexer: IndexOrchestrator | None = None) -> None:
    indexer = indexer or IndexOrchestrator()
    started = time.time()

    async with SessionLocal() as session:
        run = await crud.get_run(session, run_id)
        if run is None:
            log.warning("run_not_found", run_id=run_id)
            return
        repo = await crud.get_repository(session, run.repository_id)
        if repo is None:
            log.warning("repo_not_found", run_id=run_id)
            return
        if run.status != RunStatus.QUEUED:
            log.info("run_not_queued_skipping", run_id=run_id, status=run.status.value)
            return
        owner, name = repo.owner, repo.name
        installation_id = repo.installation_id
        repo_id = repo.id
        issue = IssueInput(number=run.issue_number, title=run.issue_title, body=run.issue_body)
        await crud.update_run(session, run, status=RunStatus.RUNNING)
        await session.commit()

    await emit_run_event(run_id, "run:status", {"status": "RUNNING"})

    gh = GitHubClient(installation_id=installation_id)
    try:
        clone_url = await gh.clone_url(owner, name)
    except Exception:
        clone_url = f"https://github.com/{owner}/{name}.git"

    # Ensure the repo is indexed so search_code works (best-effort).
    code_search = await _ensure_index(indexer, repo_id, owner, name, clone_url)

    # Per-step persistence + live emit.
    async def on_step(event: dict) -> None:
        await _raise_if_run_stopped(run_id)
        await emit_run_event(run_id, "agent:step", event)
        if event.get("type") == "observe":
            async with SessionLocal() as s:
                run = await crud.get_run(s, run_id)
                if run is not None and run.status == RunStatus.RUNNING:
                    await crud.update_run(s, run, total_steps=event["step"])
                    await crud.add_step(
                        s,
                        run_id=run_id,
                        step_number=event["step"],
                        agent_name=event.get("agent_name"),
                        thought=event.get("thought"),
                        tool_name=event.get("tool"),
                        tool_args=event.get("args"),
                        observation=event.get("observation"),
                        duration_ms=event.get("duration_ms"),
                        token_count=event.get("token_count"),
                    )
                    await s.commit()
                else:
                    raise RunStopped("Run was stopped by user.")

    runtime = AgentRuntime()
    try:
        result = await runtime.solve(
            issue,
            clone_url=clone_url,
            code_search=code_search,
            on_step=on_step,
            should_stop=lambda: _is_run_stopped(run_id),
        )
    except (AgentRunStopped, RunStopped):
        await _complete_stopped_run(run_id, started)
        return
    except Exception as exc:
        error_message = _agent_exception_message(exc)
        log.warning("agent_runtime_failed", run_id=run_id, error=error_message)
        async with SessionLocal() as session:
            run = await crud.get_run(session, run_id, with_steps=True)
            if run is not None:
                await crud.update_run(
                    session,
                    run,
                    status=RunStatus.FAILED,
                    total_steps=len(run.steps),
                    duration_ms=int((time.time() - started) * 1000),
                    error_message=error_message,
                    model=settings.agent_model_name,
                )
                await session.commit()
        await emit_run_event(run_id, "run:complete", {"status": RunStatus.FAILED.value, "pr_url": None})
        return

    pr_number = pr_url = None
    pr_error = None
    try:
        await _raise_if_run_stopped(run_id)
    except RunStopped:
        await _complete_stopped_run(run_id, started)
        return

    if result.status == AgentStatus.SOLVED and result.diff:
        try:
            await emit_run_event(
                run_id,
                "agent:step",
                {
                    "type": "creating_pr",
                    "agent_name": "PR Agent",
                    "status": "executing",
                    "observation": "Creating pull request from the approved diff.",
                },
            )
            pr_number, pr_url = await _open_pr(
                gh, owner, name, run_id, issue, result
            )
            await emit_run_event(
                run_id,
                "agent:step",
                {
                    "type": "done",
                    "agent_name": "PR Agent",
                    "status": "complete",
                    "observation": f"Pull request opened: {pr_url}",
                },
            )
        except Exception as exc:
            pr_error = str(exc)
            log.warning("pr_creation_failed", error=pr_error)

    async with SessionLocal() as session:
        run = await crud.get_run(session, run_id)
        if run is not None and run.status == RunStatus.RUNNING:
            await crud.update_run(
                session,
                run,
                status=_final_run_status(result.status, pr_error),
                total_steps=len(result.trajectory),
                duration_ms=int((time.time() - started) * 1000),
                baseline_tests=result.baseline_tests,
                final_tests=result.final_tests,
                error_message=_final_error_message(result.error_message, pr_error),
                pr_number=pr_number,
                pr_url=pr_url,
                model=settings.agent_model_name,
            )
            await session.commit()
        else:
            await _complete_stopped_run(run_id, started)
            return

    await emit_run_event(
        run_id,
        "run:complete",
        {"status": _final_run_status(result.status, pr_error).value, "pr_url": pr_url},
    )
    log.info("run_complete", run_id=run_id, status=result.status.value, pr=pr_number)


async def _raise_if_run_stopped(run_id: str) -> None:
    if await _is_run_stopped(run_id):
        raise RunStopped("Run was stopped by user.")


async def _is_run_stopped(run_id: str) -> bool:
    async with SessionLocal() as session:
        run = await crud.get_run(session, run_id)
        return run is None or run.status not in (RunStatus.QUEUED, RunStatus.RUNNING)


async def _complete_stopped_run(run_id: str, started: float) -> None:
    async with SessionLocal() as session:
        run = await crud.get_run(session, run_id)
        if run is not None and run.status in (RunStatus.QUEUED, RunStatus.RUNNING):
            await crud.update_run(
                session,
                run,
                status=RunStatus.FAILED,
                duration_ms=int((time.time() - started) * 1000),
                error_message="Stopped by user.",
            )
            await session.commit()
    await emit_run_event(run_id, "run:complete", {"status": RunStatus.FAILED.value, "pr_url": None})


async def _ensure_index(indexer, repo_id, owner, name, clone_url):  # type: ignore[no-untyped-def]
    try:
        count = await indexer.store.count(repo_id)
    except Exception:
        count = 0

    if count == 0:
        try:
            async with SessionLocal() as s:
                repo = await crud.get_repository(s, repo_id)
                if repo:
                    await crud.set_index_status(s, repo, IndexStatus.INDEXING)
                    await s.commit()
            stats = await indexer.index_repository(repo_id, clone_url)
            async with SessionLocal() as s:
                repo = await crud.get_repository(s, repo_id)
                if repo:
                    await crud.set_index_status(
                        s, repo, IndexStatus.READY,
                        files_indexed=stats["files"], last_indexed_sha=stats["sha"],
                    )
                    await s.commit()
        except Exception as exc:
            log.warning("indexing_failed_continuing_with_grep_only", error=str(exc))
            return None

    async def search(query: str, n: int) -> list[dict]:
        return await indexer.search(repo_id, query, n)

    return search


async def _open_pr(gh, owner, name, run_id, issue, result):  # type: ignore[no-untyped-def]
    pr_body = build_pr_description(
        issue_number=issue.number,
        issue_title=issue.title,
        trajectory=result.trajectory,
        status=result.status,
        baseline_tests=result.baseline_tests,
        final_tests=result.final_tests,
        model=settings.agent_model_name,
        duration_ms=result.duration_ms,
        dashboard_url=settings.cors_origin_list[0] if settings.cors_origin_list else "",
        run_id=run_id,
    )
    creator = PRCreator(gh)
    branch = f"{result.branch}-{run_id[:8]}"
    pr = await creator.create(
        owner=owner,
        repo=name,
        branch=branch,
        base=settings.github_default_base_branch,
        diff=result.diff,
        commit_message=f"fix: {issue.title} (NeuraSWE #{issue.number})",
        pr_title=f"fix: {issue.title} (NeuraSWE #{issue.number})",
        pr_body=pr_body,
    )
    number = pr.get("number")
    url = pr.get("html_url")
    try:
        await gh.create_issue_comment(
            owner, name, issue.number,
            f"🤖 NeuraSWE opened a fix: #{number}",
        )
    except Exception:
        pass
    return number, url


def _final_run_status(agent_status: AgentStatus, pr_error: str | None) -> RunStatus:
    if agent_status == AgentStatus.SOLVED and pr_error:
        return RunStatus.FAILED
    return _STATUS_MAP.get(agent_status, RunStatus.FAILED)


def _final_error_message(agent_error: str | None, pr_error: str | None) -> str | None:
    if pr_error:
        return f"Pull request creation failed: {pr_error}"
    return agent_error


def _agent_exception_message(exc: Exception) -> str:
    root = _root_exception(exc)
    text = str(root)
    lowered = text.lower()
    if "429" in text and ("openai" in lowered or "x.ai" in lowered or "too many requests" in lowered):
        return (
            "Agent LLM request failed: provider returned 429 Too Many Requests. "
            "Check API billing/quota, project rate limits, or use a model/key with available capacity."
        )
    return f"Agent runtime failed: {root.__class__.__name__}: {text}"


def _root_exception(exc: Exception) -> Exception:
    last_attempt = getattr(exc, "last_attempt", None)
    if last_attempt is not None:
        attempt_exception = getattr(last_attempt, "exception", None)
        if callable(attempt_exception):
            nested = attempt_exception()
            if isinstance(nested, Exception):
                return _root_exception(nested)
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if isinstance(cause, Exception):
        return _root_exception(cause)
    return exc
