"""Health check — verifies DB, Redis, agent LLM, Ollama embeddings, and ChromaDB."""

from __future__ import annotations

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.db.base import engine
from app.db.schemas import HealthOut

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=HealthOut)
async def health() -> HealthOut:
    services = {
        "database": await _check_db(),
        "redis": await _check_redis(),
        "agent_llm": await _check_agent_llm(),
        "ollama": await _check_ollama(),
        "chromadb": await _check_http(f"{settings.chroma_url}/api/v1/heartbeat"),
    }
    status = "ok" if all(services.values()) else "degraded"
    return HealthOut(status=status, services=services)


async def _check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _check_redis() -> bool:
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url)
        await client.ping()
        await _close_redis_client(client)
        return True
    except Exception:
        return False


async def _check_http(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(url)
            return resp.status_code < 500
    except Exception:
        return False


async def _fetch_ollama_models(url: str) -> set[str]:
    async with httpx.AsyncClient(timeout=3) as client:
        resp = await client.get(f"{url}/api/tags")
        resp.raise_for_status()
        data = resp.json()
    return {
        model.get("name", "")
        for model in data.get("models", [])
        if isinstance(model, dict) and model.get("name")
    }


async def _check_ollama() -> bool:
    try:
        models = await _fetch_ollama_models(settings.ollama_url)
    except Exception:
        return False

    required = {settings.ollama_embed_model}
    provider = settings.llm_provider.strip().lower()
    if provider == "ollama" or settings.llm_local_fallback_enabled:
        required.add(settings.ollama_chat_model)
    return all(_ollama_model_available(model, models) for model in required)


def _ollama_model_available(required: str, available: set[str]) -> bool:
    if required in available:
        return True
    if ":" not in required and f"{required}:latest" in available:
        return True
    return False


async def _check_agent_llm() -> bool:
    provider = settings.llm_provider.strip().lower()
    if provider in {"openai", "openai-compatible", "compatible", "hosted"}:
        if settings.llm_api_key or settings.gemini_api_key or settings.groq_api_key:
            return True
        if settings.openrouter_api_key:
            return True
        if settings.llm_local_fallback_enabled:
            return await _check_ollama()
        return False
    if provider == "ollama":
        return await _check_ollama()
    return False


async def _close_redis_client(client) -> None:  # type: ignore[no-untyped-def]
    close = getattr(client, "aclose", None) or client.close
    await close()
