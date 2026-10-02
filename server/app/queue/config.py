"""arq queue configuration and enqueue helpers."""

from __future__ import annotations

from urllib.parse import urlparse

from arq import create_pool
from arq.connections import RedisSettings

from app.config import settings


def redis_settings() -> RedisSettings:
    parsed = urlparse(settings.redis_url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int((parsed.path or "/0").lstrip("/") or 0),
        password=parsed.password,
    )


async def enqueue_run(run_id: str) -> None:
    """Enqueue an agent run by its DB id."""
    pool = await create_pool(redis_settings())
    try:
        # Duplicate deliveries are harmless: the database claim is atomic and only
        # one worker can move QUEUED -> PREPARING.
        await pool.enqueue_job("process_run", run_id)
    finally:
        await pool.close()


async def enqueue_publish(run_id: str) -> None:
    """Enqueue idempotent publication after an explicit approval."""
    pool = await create_pool(redis_settings())
    try:
        await pool.enqueue_job("publish_run", run_id)
    finally:
        await pool.close()
