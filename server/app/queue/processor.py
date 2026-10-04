"""Lease-owned run processing and approval-gated, idempotent publication."""

from __future__ import annotations

import asyncio
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.agent.runtime import AgentRunStopped, AgentRuntime, IssueInput
from app.agent.trajectory import Trajectory
from app.agent.types import AgentStatus
from app.config import settings
from app.db import crud
from app.db.base import SessionLocal
from app.db.models import IndexStatus, Run, RunStatus
from app.github.client import GitHubClient
from app.github.pr_creator import PRCreator
from app.github.pr_description import build_pr_description
from app.github.safety import validate_patch_for_publication
from app.indexer.orchestrator import IndexOrchestrator
from app.metrics import increment
from app.realtime.emitter import emit_run_event
from app.utils.logger import get_logger
from app.verification import compare_verification

log = get_logger("queue.processor")


class RunStopped(Exception):
    pass


async def process_run(run_id: str, *, indexer: IndexOrchestrator | None = None) -> None:
    """Produce and validate a patch; never publish it without approval."""
    indexer = indexer or IndexOrchestrator()
    started = time.time()
    worker_id = f"{socket.gethostname()}:{uuid.uuid4().hex[:12]}"

    async with SessionLocal() as session:
        run = (
            await session.execute(select(Run).where(Run.id == run_id).with_for_update())
        ).scalar_one_or_none()
        if run is None or run.status != RunStatus.QUEUED:
            return
        repo = await crud.get_repository(session, run.repository_id)
        if repo is None:
            return
        owner, name, repo_id = repo.owner, repo.name, repo.id
        installation_id = repo.installation_id
        base_branch = (repo.config or {}).get("base_branch") or settings.github_default_base_branch
        issue = IssueInput(number=run.issue_number, title=run.issue_title, body=run.issue_body)
        now = datetime.now(timezone.utc)
        await crud.update_run(
            session, run, status=RunStatus.PREPARING, worker_id=worker_id,
            worker_attempt=run.worker_attempt + 1, heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=settings.worker_lease_seconds),
            error_message=None, approval_status="NOT_REQUESTED", pr_status="NOT_REQUESTED",
            patch_diff=None, review_summary=None, approval_comment=None,
        )
        await session.commit()

    heartbeat = asyncio.create_task(_heartbeat(run_id, worker_id))
    token_total = 0
    observed_steps = 0
    tool_counts: dict[str, int] = {}
    await emit_run_event(run_id, "run:status", {"status": RunStatus.PREPARING.value})
    gh = GitHubClient(installation_id=installation_id)
    try:
        try:
            clone_url = await gh.clone_url(owner, name)
        except Exception:
            clone_url = f"https://github.com/{owner}/{name}.git"
        repository_archive = await _run_while_owned(
            gh.download_archive(owner, name, base_branch),
            run_id, worker_id,
        )

        await _transition_owned(run_id, worker_id, RunStatus.ANALYZING)
        code_search = await _run_while_owned(
            _ensure_index(indexer, repo_id, clone_url), run_id, worker_id
        )
        await _transition_owned(run_id, worker_id, RunStatus.PLANNING)
        await _transition_owned(run_id, worker_id, RunStatus.IMPLEMENTING)

        async def on_step(event: dict) -> None:
            nonlocal observed_steps, token_total
            await _assert_worker(run_id, worker_id)
            safe_event = _safe_operational_event(event)
            await emit_run_event(run_id, "agent:step", safe_event)
            if event.get("type") == "observe":
                observed_steps = max(observed_steps, int(event.get("step") or 0))
                token_total += int(event.get("token_count") or 0)
                if event.get("tool"):
                    tool = str(event["tool"])
                    tool_counts[tool] = tool_counts.get(tool, 0) + 1
                async with SessionLocal() as step_session:
                    owned = await crud.get_run(step_session, run_id)
                    if owned is None or owned.worker_id != worker_id:
                        raise RunStopped("Worker lease lost")
                    await crud.update_run(step_session, owned, total_steps=event["step"])
                    await crud.add_step(
                        step_session, run_id=run_id, step_number=event["step"],
                        agent_name=event.get("agent_name"), thought=None,
                        tool_name=event.get("tool"), tool_args=safe_event.get("args"),
                        observation=str(event.get("observation") or "")[:8000], duration_ms=event.get("duration_ms"),
                        token_count=event.get("token_count"),
                    )
                    await step_session.commit()

        result = await AgentRuntime().solve(
            issue, clone_url=None, repository_archive=repository_archive,
            code_search=code_search, on_step=on_step,
            should_stop=lambda: _should_stop(run_id, worker_id),
        )
        await _transition_owned(run_id, worker_id, RunStatus.VALIDATING)
        if result.status != AgentStatus.SOLVED or not result.diff.strip():
            terminal = RunStatus.TIMED_OUT if result.status == AgentStatus.TIMEOUT else RunStatus.FAILED
            await _finish_failure(run_id, worker_id, terminal, result.error_message, started, result)
            return
        changed_files = validate_patch_for_publication(result.diff)

        reported_tokens = result.provider_tokens or token_total
        review = {
            "root_cause": result.review_summary.get("root_cause", "Not provided by the model."),
            "proposed_solution": result.review_summary.get("proposed_solution", "Generated patch is ready for human review."),
            "modified_files": changed_files,
            "risks": result.review_summary.get("risks", []), "limitations": [],
            "tests_not_executed": (
                ["No supported test command was detected"]
                if (result.final_tests or {}).get("classification") == "UNEXECUTED" else []
            ),
            "token_usage": reported_tokens,
            "token_usage_source": "provider" if result.provider_tokens else "estimated_prompt",
            "validation_comparison": compare_verification(result.baseline_tests, result.final_tests),
        }
        async with SessionLocal() as session:
            run = await crud.get_run(session, run_id)
            if run is None or run.worker_id != worker_id or run.cancellation_requested_at:
                raise RunStopped("Run cancelled or lease lost")
            await crud.update_run(
                session, run, status=RunStatus.AWAITING_APPROVAL, approval_status="PENDING",
                pr_status="AWAITING_APPROVAL", patch_diff=result.diff, review_summary=review,
                baseline_tests=result.baseline_tests, final_tests=result.final_tests,
                total_steps=observed_steps, duration_ms=int((time.time() - started) * 1000),
                model_requests=result.model_requests, total_tokens=reported_tokens,
                tool_counts=tool_counts,
                worker_id=None, lease_expires_at=None, heartbeat_at=datetime.now(timezone.utc),
            )
            await session.commit()
        await emit_run_event(run_id, "run:status", {"status": RunStatus.AWAITING_APPROVAL.value})
    except (AgentRunStopped, RunStopped):
        await _mark_cancelled_if_requested(run_id, started)
    except asyncio.CancelledError:
        if await _has_cancellation_intent(run_id):
            await _mark_cancelled_if_requested(run_id, started)
        else:
            await _finish_failure(
                run_id, worker_id, RunStatus.TIMED_OUT,
                "Worker job timeout or shutdown interrupted the run", started, None,
            )
        raise
    except Exception as exc:
        log.exception("run_failed", run_id=run_id, error=str(exc))
        lowered = str(exc).lower()
        if "provider" in lowered or "llm" in lowered or "429" in lowered:
            await increment("provider_failures_total")
        if "sandbox" in lowered or "docker" in lowered:
            await increment("sandbox_failures_total")
        await _finish_failure(run_id, worker_id, RunStatus.FAILED, str(exc), started, None)
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)


async def publish_approved_run(run_id: str) -> None:
    """Publish exactly one PR for an approved run; safe to retry."""
    publisher_id = f"publisher:{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
    async with SessionLocal() as session:
        run = (
            await session.execute(select(Run).where(Run.id == run_id).with_for_update())
        ).scalar_one_or_none()
        if run is None or run.status != RunStatus.PR_CREATING or run.approval_status != "APPROVED":
            return
        now = datetime.now(timezone.utc)
        if run.worker_id and run.lease_expires_at and run.lease_expires_at > now:
            return
        run.worker_id = publisher_id
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(seconds=settings.worker_lease_seconds)
        if run.pr_url:
            await crud.update_run(session, run, status=RunStatus.COMPLETED, pr_status="CREATED")
            run.worker_id = None
            run.lease_expires_at = None
            await session.commit()
            return
        repo = await crud.get_repository(session, run.repository_id)
        if repo is None or not run.patch_diff:
            await crud.update_run(session, run, status=RunStatus.FAILED, pr_status="FAILED", error_message="Missing repository or patch")
            run.worker_id = None
            run.lease_expires_at = None
            await session.commit()
            return
        branch = run.remote_branch or f"neuraswe/run-{run.id}-v{run.worker_attempt}"
        run.remote_branch = branch
        await session.commit()
        issue = IssueInput(run.issue_number, run.issue_title, run.issue_body)
        owner, name, installation_id = repo.owner, repo.name, repo.installation_id
        base_branch = (repo.config or {}).get("base_branch") or settings.github_default_base_branch
        patch_diff, baseline, final = run.patch_diff, run.baseline_tests, run.final_tests
        model, duration_ms = run.model, run.duration_ms or 0
        total_steps = run.total_steps
        review_summary = run.review_summary or {}

    heartbeat = asyncio.create_task(_heartbeat(run_id, publisher_id))
    gh = GitHubClient(installation_id=installation_id)
    try:
        validate_patch_for_publication(patch_diff)
        existing = await _run_while_owned(
            gh.find_pull_request(owner, name, head=branch), run_id, publisher_id
        )
        if existing is None:
            body = build_pr_description(
                issue_number=issue.number, issue_title=issue.title, trajectory=Trajectory(),
                status=AgentStatus.SOLVED, baseline_tests=baseline, final_tests=final,
                model=model, duration_ms=duration_ms,
                dashboard_url=settings.cors_origin_list[0] if settings.cors_origin_list else "", run_id=run_id,
                root_cause_override=review_summary.get("root_cause"),
                modified_files=review_summary.get("modified_files") or [],
                total_steps=total_steps,
            )
            existing = await _run_while_owned(
                PRCreator(gh).create(
                    owner=owner, repo=name, branch=branch, base=base_branch,
                    diff=patch_diff, commit_message=f"fix: {issue.title} (NeuraSWE #{issue.number})",
                    pr_title=f"fix: {issue.title} (NeuraSWE #{issue.number})", pr_body=body,
                ),
                run_id, publisher_id,
            )
        async with SessionLocal() as session:
            current = await crud.get_run(session, run_id)
            if current is None or current.status != RunStatus.PR_CREATING or current.worker_id != publisher_id:
                return
            await crud.update_run(
                session, current, status=RunStatus.COMPLETED, pr_status="CREATED",
                pr_number=existing.get("number"), pr_url=existing.get("html_url"),
                commit_sha=(existing.get("_neuraswe_commit_sha") or (existing.get("head") or {}).get("sha") or current.commit_sha),
            )
            current.worker_id = None
            current.lease_expires_at = None
            await session.commit()
        await emit_run_event(run_id, "run:complete", {"status": "COMPLETED", "pr_url": existing.get("html_url")})
        await increment("runs_completed_total")
        await increment("pr_created_total")
    except RunStopped:
        # An approved publication may have crossed the remote boundary just before
        # cancellation. Reconcile and record it without overwriting CANCELLED.
        try:
            existing = await gh.find_pull_request(owner, name, head=branch)
        except Exception:
            existing = None
        async with SessionLocal() as session:
            current = await crud.get_run(session, run_id)
            if current:
                if existing:
                    current.pr_status = "CREATED_AFTER_CANCELLATION"
                    current.pr_number = existing.get("number")
                    current.pr_url = existing.get("html_url")
                    current.commit_sha = (existing.get("head") or {}).get("sha")
                else:
                    current.pr_status = "CANCELLED_AMBIGUOUS"
                current.worker_id = None
                current.lease_expires_at = None
                await session.commit()
        return
    except Exception as exc:
        async with SessionLocal() as session:
            current = await crud.get_run(session, run_id)
            if current and current.status == RunStatus.PR_CREATING and current.worker_id == publisher_id:
                await crud.update_run(
                    session, current, status=RunStatus.AWAITING_APPROVAL, pr_status="FAILED",
                    error_message=f"PR creation failed: {exc}",
                )
                current.worker_id = None
                current.lease_expires_at = None
                await session.commit()
        await emit_run_event(run_id, "run:status", {"status": "AWAITING_APPROVAL", "pr_status": "FAILED"})
        await increment("pr_failed_total")
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)


async def recover_orphaned_runs() -> dict[str, int]:
    """Recover expired worker leases without duplicating external side effects."""
    now = datetime.now(timezone.utc)
    retry_ids: list[str] = []
    publish_ids: list[str] = []
    cancelled = 0
    async with SessionLocal() as session:
        rows = list((await session.execute(
            select(Run).where(
                Run.lease_expires_at.is_not(None),
                Run.lease_expires_at < now,
            ).with_for_update(skip_locked=True)
        )).scalars().all())
        queued = list((await session.execute(select(Run).where(Run.status == RunStatus.QUEUED))).scalars().all())
        retry_ids.extend(run.id for run in queued)
        pending_publications = list((await session.execute(
            select(Run).where(Run.status == RunStatus.PR_CREATING)
        )).scalars().all())
        publish_ids.extend(run.id for run in pending_publications)
        for run in rows:
            run.worker_id = None
            run.lease_expires_at = None
            if run.cancellation_requested_at:
                await crud.update_run(session, run, status=RunStatus.CANCELLED)
                cancelled += 1
            elif run.status == RunStatus.PR_CREATING:
                run.state_version += 1
                publish_ids.append(run.id)
            elif run.status in {
                RunStatus.PREPARING, RunStatus.ANALYZING, RunStatus.PLANNING,
                RunStatus.IMPLEMENTING, RunStatus.VALIDATING, RunStatus.RUNNING,
            }:
                # These phases have no committed external side effect and are safe to restart.
                await crud.update_run(session, run, status=RunStatus.QUEUED)
                retry_ids.append(run.id)
        await session.commit()
    from app.queue.config import enqueue_publish, enqueue_run
    retry_ids = list(dict.fromkeys(retry_ids))
    for run_id in retry_ids:
        await enqueue_run(run_id)
    publish_ids = list(dict.fromkeys(publish_ids))
    for run_id in publish_ids:
        await enqueue_publish(run_id)
    return {"retried": len(retry_ids), "publication_checked": len(publish_ids), "cancelled": cancelled}


async def _heartbeat(run_id: str, worker_id: str) -> None:
    while True:
        await asyncio.sleep(max(5, settings.worker_lease_seconds // 3))
        async with SessionLocal() as session:
            run = await crud.get_run(session, run_id)
            if run is None or run.worker_id != worker_id or run.cancellation_requested_at:
                return
            now = datetime.now(timezone.utc)
            run.heartbeat_at = now
            run.lease_expires_at = now + timedelta(seconds=settings.worker_lease_seconds)
            await session.commit()


async def _assert_worker(run_id: str, worker_id: str) -> None:
    if await _should_stop(run_id, worker_id):
        raise RunStopped("Run cancelled or lease lost")


async def _run_while_owned(awaitable, run_id: str, worker_id: str):  # type: ignore[no-untyped-def]
    task = asyncio.create_task(awaitable)
    try:
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=1.0)
            if done:
                break
            await _assert_worker(run_id, worker_id)
        result = await task
        await _assert_worker(run_id, worker_id)
        return result
    except BaseException:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise


async def _should_stop(run_id: str, worker_id: str) -> bool:
    async with SessionLocal() as session:
        run = await crud.get_run(session, run_id)
        return run is None or run.worker_id != worker_id or run.cancellation_requested_at is not None or run.status in {RunStatus.CANCELLED, RunStatus.REJECTED}


async def _transition_owned(run_id: str, worker_id: str, status: RunStatus) -> None:
    async with SessionLocal() as session:
        run = await crud.get_run(session, run_id)
        if run is None or run.worker_id != worker_id or run.cancellation_requested_at:
            raise RunStopped("Run cancelled or lease lost")
        await crud.update_run(session, run, status=status)
        await session.commit()
    await emit_run_event(run_id, "run:status", {"status": status.value})


async def _finish_failure(run_id: str, worker_id: str, status: RunStatus, error: str | None, started: float, result) -> None:  # type: ignore[no-untyped-def]
    async with SessionLocal() as session:
        run = await crud.get_run(session, run_id)
        if run is None or run.worker_id != worker_id or run.status == RunStatus.CANCELLED:
            return
        await crud.update_run(
            session, run, status=status, error_message=error,
            duration_ms=int((time.time() - started) * 1000), worker_id=None, lease_expires_at=None,
            baseline_tests=getattr(result, "baseline_tests", None),
            final_tests=getattr(result, "final_tests", None),
        )
        await session.commit()
    await emit_run_event(run_id, "run:complete", {"status": status.value, "pr_url": None})
    await increment("runs_timed_out_total" if status == RunStatus.TIMED_OUT else "runs_failed_total")


async def _mark_cancelled_if_requested(run_id: str, started: float) -> None:
    newly_cancelled = False
    async with SessionLocal() as session:
        run = await crud.get_run(session, run_id)
        if run is None or not run.cancellation_requested_at:
            return
        if run.status != RunStatus.CANCELLED:
            await crud.update_run(session, run, status=RunStatus.CANCELLED)
            newly_cancelled = True
        run.worker_id = None
        run.lease_expires_at = None
        run.duration_ms = run.duration_ms or int((time.time() - started) * 1000)
        await session.commit()
    await emit_run_event(run_id, "run:complete", {"status": "CANCELLED", "pr_url": None})
    if newly_cancelled:
        await increment("runs_cancelled_total")


async def _has_cancellation_intent(run_id: str) -> bool:
    async with SessionLocal() as session:
        run = await crud.get_run(session, run_id)
        return bool(run and run.cancellation_requested_at)


async def _ensure_index(indexer: IndexOrchestrator, repo_id: str, clone_url: str):  # type: ignore[no-untyped-def]
    try:
        if await indexer.store.count(repo_id) == 0:
            stats = await indexer.index_repository(repo_id, clone_url)
            async with SessionLocal() as session:
                repo = await crud.get_repository(session, repo_id)
                if repo:
                    await crud.set_index_status(
                        session, repo, IndexStatus.READY, files_indexed=stats["files"],
                        last_indexed_sha=stats["sha"], indexing_progress=100,
                    )
                    await session.commit()
    except Exception as exc:
        log.warning("indexing_failed_continuing_with_grep_only", repo_id=repo_id, error=str(exc))
        return None

    async def search(query: str, n: int) -> list[dict]:
        return await indexer.search(repo_id, query, n)
    return search


# Compatibility helpers retained for existing focused tests and integrations.
def _final_run_status(agent_status: AgentStatus, pr_error: str | None) -> RunStatus:
    if agent_status == AgentStatus.SOLVED and not pr_error:
        return RunStatus.SOLVED
    if agent_status == AgentStatus.TIMEOUT:
        return RunStatus.TIMEOUT
    return RunStatus.FAILED


def _agent_exception_message(exc: Exception) -> str:
    root = exc
    last_attempt = getattr(exc, "last_attempt", None)
    if last_attempt is not None and callable(getattr(last_attempt, "exception", None)):
        root = last_attempt.exception() or exc
    text = str(root)
    if "429" in text and ("openai" in text.lower() or "too many requests" in text.lower()):
        return (
            "Agent LLM request failed: provider returned 429 Too Many Requests. "
            "Check API billing/quota, project rate limits, or use a model/key with available capacity."
        )
    return f"Agent runtime failed: {root.__class__.__name__}: {text}"


def _safe_operational_event(event: dict) -> dict:
    safe = {k: v for k, v in event.items() if k != "thought"}
    args = dict(safe.get("args") or {})
    for key in ("content", "old_text", "new_text"):
        if key in args:
            value = str(args[key])
            args[key] = f"[redacted content: {len(value)} characters]"
    if "command" in args:
        args["command"] = str(args["command"])[:500]
    if args:
        safe["args"] = args
    if "observation" in safe:
        safe["observation"] = str(safe["observation"])[:2000]
    return safe
