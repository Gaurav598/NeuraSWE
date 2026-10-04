"""arq worker entrypoint. Run with: arq app.queue.worker.WorkerSettings"""

from __future__ import annotations

import asyncio

from app.config import settings
from app.queue.config import redis_settings
from app.queue.processor import process_run as run_processor
from app.queue.processor import publish_approved_run, recover_orphaned_runs
from app.utils.logger import configure_logging, get_logger

log = get_logger("queue.worker")


async def process_run(ctx: dict, run_id: str) -> None:
    await run_processor(run_id)


async def publish_run(ctx: dict, run_id: str) -> None:
    await publish_approved_run(run_id)


async def on_startup(ctx: dict) -> None:
    configure_logging()
    await recover_orphaned_runs()
    ctx["recovery_task"] = asyncio.create_task(_recovery_loop())


async def on_shutdown(ctx: dict) -> None:
    task = ctx.get("recovery_task")
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _recovery_loop() -> None:
    interval = max(15, min(60, settings.worker_lease_seconds // 2))
    while True:
        await asyncio.sleep(interval)
        try:
            await recover_orphaned_runs()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # A later pass retries; individual recovery failures must not kill
            # the worker that is still processing owned jobs.
            log.warning("run_recovery_pass_failed", error=str(exc))
            continue


class WorkerSettings:
    functions = [process_run, publish_run]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = redis_settings()
    max_jobs = settings.worker_max_jobs
    max_tries = 1
    job_timeout = settings.worker_job_timeout_s
