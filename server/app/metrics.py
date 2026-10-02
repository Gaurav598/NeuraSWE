"""Small Redis-backed operational counters shared by API and workers."""

from __future__ import annotations

import redis.asyncio as redis

from app.config import settings

KEY = "neuraswe:metrics"


async def increment(name: str) -> None:
    client = redis.from_url(settings.redis_url)
    try:
        await client.hincrby(KEY, name, 1)
    except Exception:
        pass
    finally:
        close = getattr(client, "aclose", None) or client.close
        await close()


async def snapshot() -> dict[str, int]:
    client = redis.from_url(settings.redis_url)
    try:
        rows = await client.hgetall(KEY)
        return {key.decode(): int(value) for key, value in rows.items()}
    finally:
        close = getattr(client, "aclose", None) or client.close
        await close()
