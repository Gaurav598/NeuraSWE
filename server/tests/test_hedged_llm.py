"""Tests for HedgedChatClient — the request-hedging (racing) speed feature.

Uses fake in-memory chat clients with simulated latency, so no network or API
keys are required. Verifies: fastest valid response wins, a fast-but-invalid
response yields to a slower valid one, failing providers are skipped, losing
tasks are cancelled, and the all-invalid / all-failed fallbacks behave.
"""

import asyncio

import pytest

from app.agent.llm import HedgedChatClient

VALID = '{"thought": "go", "action": {"tool": "grep", "args": {"pattern": "x"}}}'
VALID_B = '{"thought": "go", "action": {"tool": "read_file", "args": {"path": "a.py"}}}'
INVALID = "I am not JSON and have no action."


class FakeClient:
    def __init__(self, name, delay, response=VALID, fail=False):
        self.name = name
        self.delay = delay
        self.response = response
        self.fail = fail
        self.cancelled = False

    async def chat(self, *args, **kwargs):
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if self.fail:
            raise RuntimeError(f"{self.name} boom")
        return self.response

    async def summarize(self, *args, **kwargs):
        return await self.chat(*args, **kwargs)


async def test_fastest_valid_wins():
    fast = FakeClient("gemini", 0.01, VALID)
    slow = FakeClient("groq", 0.20, VALID_B)
    client = HedgedChatClient([("gemini", fast), ("groq", slow)])
    result = await client.chat("sys", "user")
    assert result == VALID


async def test_invalid_fast_yields_to_valid_slow():
    fast_bad = FakeClient("local", 0.01, INVALID)
    slow_good = FakeClient("gemini", 0.15, VALID)
    client = HedgedChatClient([("local", fast_bad), ("gemini", slow_good)])
    result = await client.chat("sys", "user")
    assert result == VALID


async def test_losers_are_cancelled():
    winner = FakeClient("gemini", 0.01, VALID)
    loser = FakeClient("groq", 2.0, VALID_B)
    client = HedgedChatClient([("gemini", winner), ("groq", loser)])
    await client.chat("sys", "user")
    await asyncio.sleep(0.05)  # give cancellation a chance to propagate
    assert loser.cancelled is True


async def test_all_invalid_falls_back_to_first_any():
    a = FakeClient("a", 0.01, INVALID)
    b = FakeClient("b", 0.10, "also not valid")
    client = HedgedChatClient([("a", a), ("b", b)])
    result = await client.chat("sys", "user")
    assert result == INVALID  # first response that arrived


async def test_failing_provider_is_skipped():
    boom = FakeClient("a", 0.01, fail=True)
    good = FakeClient("b", 0.10, VALID)
    client = HedgedChatClient([("a", boom), ("b", good)])
    result = await client.chat("sys", "user")
    assert result == VALID


async def test_all_fail_raises():
    a = FakeClient("a", 0.01, fail=True)
    b = FakeClient("b", 0.02, fail=True)
    client = HedgedChatClient([("a", a), ("b", b)])
    with pytest.raises(RuntimeError):
        await client.chat("sys", "user")


async def test_summarize_does_not_require_valid_json():
    a = FakeClient("a", 0.01, "a plain english summary")
    client = HedgedChatClient([("a", a)])
    result = await client.summarize("text", "instruction")
    assert result == "a plain english summary"


def test_empty_clients_rejected():
    with pytest.raises(ValueError):
        HedgedChatClient([])
