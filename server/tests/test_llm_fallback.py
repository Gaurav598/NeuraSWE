"""Tests for rate-limit-aware rotation and the provider fallback chain."""

import httpx
import pytest

from app.agent.llm import (
    FallbackChatClient,
    OpenAICompatibleChat,
    RateLimited,
    _build_fallback_clients,
    _parse_retry_after,
)


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": '{"thought":"x","action":{"tool":"git_diff","args":{}}}'}}]},
    )


@pytest.mark.asyncio
async def test_rotates_keys_on_429():
    seen_keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers["authorization"].removeprefix("Bearer ")
        seen_keys.append(key)
        if key == "key-1":  # first key is throttled
            return httpx.Response(429, headers={"retry-after": "30"}, json={"error": "rate"})
        return _ok_response()

    chat = OpenAICompatibleChat(
        api_keys=["key-1", "key-2"],
        model="m",
        base_url="https://x/v1",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )

    raw = await chat.chat("system", "user")
    assert '"tool"' in raw
    assert seen_keys == ["key-1", "key-2"]  # rotated to the second key


@pytest.mark.asyncio
async def test_raises_ratelimited_when_all_keys_throttled():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "12"}, json={"error": "rate"})

    chat = OpenAICompatibleChat(
        api_keys=["k1", "k2"],
        model="m",
        base_url="https://x/v1",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )

    with pytest.raises(RateLimited) as exc:
        await chat.chat("system", "user")
    assert exc.value.retry_after == 12


@pytest.mark.asyncio
async def test_fallback_chain_uses_secondary_when_primary_throttled():
    def throttled(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "60"}, json={"error": "rate"})

    def healthy(request: httpx.Request) -> httpx.Response:
        return _ok_response()

    primary = OpenAICompatibleChat(
        api_key="p", model="m", base_url="https://groq/v1",
        transport=httpx.MockTransport(throttled), name="primary", max_retries=0,
    )
    secondary = OpenAICompatibleChat(
        api_key="s", model="m", base_url="https://gemini/v1",
        transport=httpx.MockTransport(healthy), name="gemini", max_retries=0,
    )

    chain = FallbackChatClient([("primary", primary), ("gemini", secondary)])
    raw = await chain.chat("system", "user")
    assert '"tool"' in raw

    # Primary is now in cooldown; a second call should be served by gemini too.
    raw2 = await chain.chat("system", "user")
    assert '"tool"' in raw2


@pytest.mark.asyncio
async def test_fallback_chain_raises_when_all_fail():
    def throttled(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate"})

    a = OpenAICompatibleChat(api_key="a", model="m", base_url="https://a/v1",
                             transport=httpx.MockTransport(throttled), name="a", max_retries=0)
    b = OpenAICompatibleChat(api_key="b", model="m", base_url="https://b/v1",
                             transport=httpx.MockTransport(throttled), name="b", max_retries=0)
    chain = FallbackChatClient([("a", a), ("b", b)])

    with pytest.raises(RuntimeError, match="All LLM providers failed"):
        await chain.chat("system", "user")


def test_parse_retry_after_seconds():
    resp = httpx.Response(429, headers={"retry-after": "45"})
    assert _parse_retry_after(resp) == 45.0


def test_build_fallback_clients_respects_order_and_adds_local_ollama(monkeypatch):
    monkeypatch.setattr("app.agent.llm.settings.llm_fallback_order", "openrouter,gemini,groq,ollama")
    monkeypatch.setattr("app.agent.llm.settings.openrouter_api_key", "or-key")
    monkeypatch.setattr("app.agent.llm.settings.openrouter_model", "or-model")
    monkeypatch.setattr("app.agent.llm.settings.openrouter_base_url", "https://openrouter.test/v1")
    monkeypatch.setattr("app.agent.llm.settings.openrouter_requests_per_minute", 20)
    monkeypatch.setattr("app.agent.llm.settings.gemini_api_key", "gem-key")
    monkeypatch.setattr("app.agent.llm.settings.gemini_model", "gem-model")
    monkeypatch.setattr("app.agent.llm.settings.gemini_base_url", "https://gemini.test/v1")
    monkeypatch.setattr("app.agent.llm.settings.gemini_requests_per_minute", 15)
    monkeypatch.setattr("app.agent.llm.settings.groq_api_key", "groq-key")
    monkeypatch.setattr("app.agent.llm.settings.groq_model", "groq-model")
    monkeypatch.setattr("app.agent.llm.settings.groq_base_url", "https://groq.test/v1")
    monkeypatch.setattr("app.agent.llm.settings.groq_requests_per_minute", 30)
    monkeypatch.setattr("app.agent.llm.settings.llm_local_fallback_enabled", True)

    clients = _build_fallback_clients(primary_base_url="https://primary.test/v1")

    assert [name for name, _client in clients] == ["openrouter", "gemini", "groq", "ollama"]
