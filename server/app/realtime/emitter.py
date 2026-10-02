"""Socket.IO server + run-scoped event emitter.

The worker process and the API process are separate, so we use the Redis-backed
AsyncRedisManager so events emitted from the worker reach clients connected to
the API server. Clients join a room ``run:{run_id}`` to receive that run's steps.
"""

from __future__ import annotations

import hmac
from typing import Any

import socketio
from sqlalchemy import select

from app.config import settings
from app.db import crud
from app.db.base import SessionLocal
from app.db.models import Run
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


_principals: dict[str, str] = {}


@sio.event
async def connect(sid: str, environ: dict, auth: Any = None) -> bool | None:  # noqa: ARG001
    user_id = "local"
    if settings.auth_required:
        supplied = (auth or {}).get("token", "") if isinstance(auth, dict) else ""
        user_id = ""
        for token, candidate in settings.auth_token_map.items():
            if hmac.compare_digest(supplied, token):
                user_id = candidate
                break
        if not user_id:
            log.warning("socket_auth_rejected", sid=sid)
            return False
    _principals[sid] = user_id
    log.info("socket_connected", sid=sid)
    return None


@sio.event
async def disconnect(sid: str) -> None:
    _principals.pop(sid, None)
    log.info("socket_disconnected", sid=sid)


@sio.on("subscribe")
async def subscribe(sid: str, data: dict) -> None:
    run_id = (data or {}).get("run_id")
    if run_id:
        async with SessionLocal() as session:
            run = await crud.get_run(session, run_id)
            if run is None or run.owner_id != _principals.get(sid):
                await sio.emit("subscription:error", {"run_id": run_id, "error": "not found"}, to=sid)
                return
        await sio.enter_room(sid, f"run:{run_id}")
        await sio.emit("subscribed", {"run_id": run_id}, to=sid)


@sio.on("unsubscribe")
async def unsubscribe(sid: str, data: dict) -> None:
    run_id = (data or {}).get("run_id")
    if run_id:
        await sio.leave_room(sid, f"run:{run_id}")


async def emit_run_event(run_id: str, event: str, payload: dict) -> None:
    """Persist *event* and emit it only to authorized subscribers of *run_id*."""
    sequence = 0
    try:
        async with SessionLocal() as session:
            run = (
                await session.execute(select(Run).where(Run.id == run_id).with_for_update())
            ).scalar_one_or_none()
            if run is not None:
                persisted = await crud.add_run_event(session, run, event, payload)
                sequence = persisted.sequence
                await session.commit()
    except Exception as exc:
        log.warning("run_event_persist_failed", run_id=run_id, error=str(exc))
    enriched = {"run_id": run_id, "sequence": sequence, **payload}
    await sio.emit(event, enriched, room=f"run:{run_id}")
