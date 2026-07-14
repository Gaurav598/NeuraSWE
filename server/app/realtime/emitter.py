"""Socket.IO server + run-scoped event emitter.

The worker process and the API process are separate, so we use the Redis-backed
AsyncRedisManager so events emitted from the worker reach clients connected to
the API server. Clients join a room ``run:{run_id}`` to receive that run's steps.
"""

from __future__ import annotations

from typing import Any

import socketio

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("realtime")

# Redis manager lets multiple processes publish to the same rooms.
_mgr = socketio.AsyncRedisManager(settings.redis_url)

sio = socketio.AsyncServer(
    async_mode="asgi",
    client_manager=_mgr,
    cors_allowed_origins=settings.cors_origin_list or "*",
    logger=False,
    engineio_logger=False,
)


@sio.event
async def connect(sid: str, environ: dict, auth: Any = None) -> None:  # noqa: ARG001
    log.info("socket_connected", sid=sid)


@sio.event
async def disconnect(sid: str) -> None:
    log.info("socket_disconnected", sid=sid)


@sio.on("subscribe")
async def subscribe(sid: str, data: dict) -> None:
    run_id = (data or {}).get("run_id")
    if run_id:
        await sio.enter_room(sid, f"run:{run_id}")
        await sio.emit("subscribed", {"run_id": run_id}, to=sid)


@sio.on("unsubscribe")
async def unsubscribe(sid: str, data: dict) -> None:
    run_id = (data or {}).get("run_id")
    if run_id:
        await sio.leave_room(sid, f"run:{run_id}")


async def emit_run_event(run_id: str, event: str, payload: dict) -> None:
    """Emit *event* to everyone subscribed to *run_id* (and a global feed)."""
    enriched = {"run_id": run_id, **payload}
    await sio.emit(event, enriched, room=f"run:{run_id}")
    await sio.emit(event, enriched, room="global")
