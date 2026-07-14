"""FastAPI + Socket.IO application bootstrap."""

from __future__ import annotations

from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, jira_webhook, repositories, runs, webhook
from app.config import settings
from app.realtime.emitter import sio
from app.utils.logger import configure_logging, get_logger

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("neuraswe_starting", env=settings.node_env, sandbox_mode="docker/local")
    # In dev without Alembic, create tables on the fly.
    if not settings.is_production:
        try:
            from app.db.base import init_models

            await init_models()
        except Exception as exc:
            log.warning("init_models_skipped", error=str(exc))
    yield
    log.info("neuraswe_shutdown")


def create_app() -> FastAPI:
    api = FastAPI(
        title="NeuraSWE",
        version="1.0.0",
        description="Autonomous Software Engineering Agent",
        lifespan=lifespan,
    )
    api.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api.include_router(health.router)
    api.include_router(runs.router)
    api.include_router(repositories.router)
    api.include_router(webhook.router)
    api.include_router(jira_webhook.router)

    @api.get("/")
    async def root() -> dict:
        return {"name": "NeuraSWE", "version": "1.0.0", "status": "ok"}

    return api


fastapi_app = create_app()

# Wrap with Socket.IO ASGI app so both HTTP and websockets share one server.
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path="socket.io")
