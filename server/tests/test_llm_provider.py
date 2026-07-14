import json

import httpx
import pytest

from app.agent.llm import OpenAICompatibleChat, build_chat_client
from app.config import Settings


@pytest.mark.asyncio
async def test_openai_compatible_chat_requests_json_mode():
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"thought":"x","action":{"tool":"git_diff","args":{}}}'
                        }
                    }
                ]
            },
        )

    chat = OpenAICompatibleChat(
        api_key="test-key",
        model="gpt-test",
        transport=httpx.MockTransport(handler),
    )

    raw = await chat.chat("system", "user")

    assert json.loads(raw)["action"]["tool"] == "git_diff"
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert requests[0]["model"] == "gpt-test"


def test_build_chat_client_selects_openai_compatible_provider(monkeypatch):
    monkeypatch.setattr("app.agent.llm.settings.llm_fallback_enabled", False)

    client = build_chat_client(provider="openai-compatible", llm_api_key="test-key")

    assert isinstance(client, OpenAICompatibleChat)


def test_provider_neutral_llm_config_does_not_reuse_legacy_openai_key():
    settings = Settings(
        LLM_PROVIDER="openai-compatible",
        LLM_BASE_URL="https://api.groq.com/openai/v1",
        LLM_MODEL="llama-3.3-70b-versatile",
        LLM_TIMEOUT_S=180,
        OPENAI_API_KEY="legacy-openai-key",
        _env_file=None,
    )

    assert settings.llm_api_key == ""
    assert settings.llm_base_url == "https://api.groq.com/openai/v1"
    assert settings.llm_model == "llama-3.3-70b-versatile"


def test_legacy_openai_config_still_falls_back_when_no_llm_config_is_set():
    settings = Settings(
        LLM_PROVIDER="openai",
        OPENAI_API_KEY="legacy-openai-key",
        OPENAI_MODEL="gpt-4.1-mini",
        _env_file=None,
    )

    assert settings.llm_api_key == "legacy-openai-key"
    assert settings.llm_model == "gpt-4.1-mini"


def test_build_chat_client_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        build_chat_client(provider="unknown")
