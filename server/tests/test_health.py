"""Tests for health-check compatibility helpers."""

import pytest

from app.api import health
from app.api.health import _close_redis_client


class RedisFiveClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class RedisFourClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_close_redis_client_uses_aclose_when_available():
    client = RedisFiveClient()

    await _close_redis_client(client)

    assert client.closed is True


@pytest.mark.asyncio
async def test_close_redis_client_falls_back_to_close():
    client = RedisFourClient()

    await _close_redis_client(client)

    assert client.closed is True


@pytest.mark.asyncio
async def test_agent_llm_health_requires_llm_key(monkeypatch):
    monkeypatch.setattr(health.settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(health.settings, "llm_api_key", "")
    monkeypatch.setattr(health.settings, "gemini_api_key", "")
    monkeypatch.setattr(health.settings, "groq_api_key", "")
    monkeypatch.setattr(health.settings, "openrouter_api_key", "")
    monkeypatch.setattr(health.settings, "llm_local_fallback_enabled", False)

    assert await health._check_agent_llm() is False

    monkeypatch.setattr(health.settings, "llm_api_key", "set")
    assert await health._check_agent_llm() is True


@pytest.mark.asyncio
async def test_ollama_health_requires_configured_models(monkeypatch):
    monkeypatch.setattr(health.settings, "ollama_chat_model", "chat-model")
    monkeypatch.setattr(health.settings, "ollama_embed_model", "embed-model")
    monkeypatch.setattr(health.settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(health.settings, "llm_local_fallback_enabled", True)

    async def fake_tags(_url: str) -> set[str]:
        return {"embed-model:latest"}

    monkeypatch.setattr(health, "_fetch_ollama_models", fake_tags)

    assert await health._check_ollama() is False

    async def all_tags(_url: str) -> set[str]:
        return {"embed-model:latest", "chat-model"}

    monkeypatch.setattr(health, "_fetch_ollama_models", all_tags)

    assert await health._check_ollama() is True
