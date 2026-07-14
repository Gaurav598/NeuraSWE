"""Chat clients used by the agent runtime.

This module provides three things:

* ``OllamaChat`` — local model client (kept for offline / embedding-only setups).
* ``OpenAICompatibleChat`` — a single OpenAI-compatible provider (Groq, Gemini's
  OpenAI-compat endpoint, OpenRouter, OpenAI, ...). It rotates across multiple
  API keys and is *rate-limit aware*: on HTTP 429 it reads ``Retry-After`` and
  raises :class:`RateLimited` instead of blindly hammering the endpoint.
* ``FallbackChatClient`` — chains several providers together. When one provider
  is throttled or failing, it transparently falls through to the next and keeps
  a short cooldown so a known-throttled provider isn't retried immediately.

The goal: run reliably on free API tiers by stacking several of them.
"""

from __future__ import annotations

import asyncio
import time
from email.utils import parsedate_to_datetime
from typing import Protocol

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("agent.llm")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class ProviderError(RuntimeError):
    """A provider failed in a way that should trigger fallback to the next one."""


class RateLimited(ProviderError):
    """Provider returned HTTP 429 / quota exhausted."""

    def __init__(self, provider: str, retry_after: float | None = None) -> None:
        self.provider = provider
        self.retry_after = retry_after
        super().__init__(f"{provider} rate-limited (retry_after={retry_after})")


class AuthError(ProviderError):
    """Provider rejected the API key (401/403)."""


# --------------------------------------------------------------------------- #
# Protocol
# --------------------------------------------------------------------------- #
class ChatClient(Protocol):
    async def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> str:
        ...

    async def summarize(self, text: str, instruction: str) -> str:
        ...


def _parse_retry_after(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        try:
            dt = parsedate_to_datetime(raw)
            return max(0.0, dt.timestamp() - time.time())
        except (TypeError, ValueError):
            return None


# --------------------------------------------------------------------------- #
# Local (Ollama)
# --------------------------------------------------------------------------- #
class OllamaChat:
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or settings.ollama_chat_model
        self.base_url = (base_url or settings.ollama_url).rstrip("/")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    async def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        message = data.get("message", {})
        content = message.get("content", "")
        if not content:
            raise RuntimeError("Ollama returned an empty response")
        return content

    async def summarize(self, text: str, instruction: str) -> str:
        return await self.chat(
            system="You are a concise technical summarizer.",
            user=f"{instruction}\n\n{text}",
            temperature=0.2,
            max_tokens=400,
        )


# --------------------------------------------------------------------------- #
# Hosted (OpenAI-compatible) — key rotation + rate-limit aware
# --------------------------------------------------------------------------- #
def _split_keys(value: str | None) -> list[str]:
    if not value:
        return []
    return [k.strip() for k in value.split(",") if k.strip()]


class OpenAICompatibleChat:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_keys: list[str] | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        name: str = "hosted",
        max_retries: int | None = None,
        requests_per_minute: int | None = None,
    ) -> None:
        if api_keys is not None:
            keys = [k for k in api_keys if k]
        elif api_key is not None:
            keys = _split_keys(api_key)
        else:
            keys = _split_keys(settings.llm_api_key)
        if not keys:
            raise RuntimeError(
                "LLM_API_KEY is required when using an OpenAI-compatible LLM provider"
            )
        self.api_keys = keys
        self.name = name
        self.model = model or settings.llm_model
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.timeout = timeout or settings.llm_timeout_s
        self.transport = transport
        self.max_retries = settings.llm_max_retries if max_retries is None else max_retries
        rpm = settings.llm_requests_per_minute if requests_per_minute is None else requests_per_minute
        # Proactive pacing: minimum seconds between requests to stay under RPM.
        self._min_interval = (60.0 / rpm) if rpm and rpm > 0 else 0.0
        self._pace_lock = asyncio.Lock()
        self._last_request = 0.0

    async def _throttle(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._pace_lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()

    async def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> str:
        return await self._chat(
            system=(
                system
                + "\n\nFor this request, return ONLY one valid JSON object in this shape: "
                '{"thought":"reasoning","action":{"tool":"tool_name","args":{}}}.'
            ),
            user=user,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )

    async def summarize(self, text: str, instruction: str) -> str:
        return await self._chat(
            system="You are a concise technical summarizer.",
            user=f"{instruction}\n\n{text}",
            temperature=0.2,
            max_tokens=400,
            json_mode=False,
        )

    async def _chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_error: Exception | None = None
        # Rotate across keys; within a key, retry only transient (5xx/network) errors.
        for key in self.api_keys:
            for attempt in range(self.max_retries + 1):
                try:
                    return await self._request(payload, key)
                except RateLimited as exc:
                    # Don't burn retries on a throttled key — rotate to the next.
                    last_error = exc
                    break
                except AuthError as exc:
                    last_error = exc
                    break
                except (httpx.TransportError, httpx.TimeoutException, _Transient) as exc:
                    last_error = exc
                    if attempt < self.max_retries:
                        await asyncio.sleep(min(2 ** attempt, 8))
                        continue
                    break
        assert last_error is not None
        raise last_error

    async def _request(self, payload: dict, api_key: str) -> str:
        await self._throttle()
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )

        if resp.status_code == 429:
            raise RateLimited(self.name, retry_after=_parse_retry_after(resp))
        if resp.status_code in (401, 403):
            raise AuthError(f"{self.name}: provider rejected the API key ({resp.status_code})")
        if resp.status_code >= 500:
            raise _Transient(f"{self.name}: provider {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()

        choices = data.get("choices") or []
        content = (choices[0].get("message", {}) if choices else {}).get("content", "")
        if not content:
            raise _Transient(f"{self.name}: empty response")
        return content


class _Transient(RuntimeError):
    """Retryable provider error (5xx / empty body)."""


# --------------------------------------------------------------------------- #
# Fallback chain across multiple providers
# --------------------------------------------------------------------------- #
class FallbackChatClient:
    def __init__(self, clients: list[tuple[str, ChatClient]]) -> None:
        if not clients:
            raise ValueError("FallbackChatClient requires at least one provider")
        self._clients = clients
        self._cooldown: dict[str, float] = {}

    async def chat(self, *args, **kwargs) -> str:
        return await self._run("chat", *args, **kwargs)

    async def summarize(self, *args, **kwargs) -> str:
        return await self._run("summarize", *args, **kwargs)

    async def _run(self, method: str, *args, **kwargs) -> str:
        now = time.monotonic()
        ready = [(n, c) for n, c in self._clients if self._cooldown.get(n, 0) <= now]
        cooling = [(n, c) for n, c in self._clients if self._cooldown.get(n, 0) > now]
        # Prefer providers not in cooldown; fall back to cooling ones as last resort.
        ordered = ready + cooling

        errors: list[str] = []
        for name, client in ordered:
            try:
                result = await getattr(client, method)(*args, **kwargs)
                if len(self._clients) > 1 and (name, client) != self._clients[0]:
                    log.info("llm_fallback_served", provider=name)
                return result
            except RateLimited as exc:
                cooldown = exc.retry_after if exc.retry_after else 60.0
                self._cooldown[name] = time.monotonic() + cooldown
                errors.append(f"{name}: rate-limited (cooldown={cooldown:.0f}s)")
                log.warning("llm_provider_rate_limited", provider=name, retry_after=exc.retry_after)
            except ProviderError as exc:
                errors.append(f"{name}: {exc}")
                log.warning("llm_provider_failed", provider=name, error=str(exc))
            except Exception as exc:  # noqa: BLE001 - keep trying remaining providers
                errors.append(f"{name}: {exc}")
                log.warning("llm_provider_error", provider=name, error=str(exc))

        raise RuntimeError("All LLM providers failed: " + " | ".join(errors))


# --------------------------------------------------------------------------- #
# Hedged / racing client — fire every provider at once, take the first VALID
# --------------------------------------------------------------------------- #
def _is_valid_action(text: str) -> bool:
    """A response is 'valid' if the parser can extract a tool action from it.

    Imported lazily to avoid any import-order coupling with the agent package.
    """
    try:
        from app.agent.response_parser import parse_response

        return parse_response(text).action is not None
    except Exception:
        return False


class HedgedChatClient:
    """Race all providers concurrently; return the first response that parses
    into a valid tool action, cancelling the losers.

    Why: the ReAct loop is sequential, so per-step LLM latency dominates wall
    time. Issuing the same prompt to every provider (Gemini + Groq + OpenRouter
    + local Ollama) and taking the fastest *valid* answer collapses each step to
    the latency of whichever provider is quickest right now, and transparently
    skips one that's slow or throttled. Trade-off: one call per provider per
    step. ``summarize`` is not latency-critical, so it just delegates to the
    first provider that succeeds.
    """

    def __init__(
        self,
        clients: list[tuple[str, ChatClient]],
        *,
        grace_s: float = 0.0,
    ) -> None:
        if not clients:
            raise ValueError("HedgedChatClient requires at least one provider")
        self._clients = clients
        self._grace_s = max(0.0, grace_s)

    async def chat(self, *args, **kwargs) -> str:
        return await self._race(validate=True, *args, **kwargs)

    async def summarize(self, *args, **kwargs) -> str:
        # Summaries aren't on the critical path and don't need JSON validity.
        return await self._race(validate=False, method="summarize", *args, **kwargs)

    async def _race(self, *args, validate: bool, method: str = "chat", **kwargs) -> str:
        tasks: dict[asyncio.Task, str] = {}
        for name, client in self._clients:
            coro = getattr(client, method)(*args, **kwargs)
            task = asyncio.ensure_future(coro)
            tasks[task] = name

        pending = set(tasks.keys())
        first_any: str | None = None
        errors: list[str] = []
        try:
            while pending:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    name = tasks[task]
                    try:
                        result = task.result()
                    except asyncio.CancelledError:
                        continue
                    except Exception as exc:  # noqa: BLE001 - try the other racers
                        errors.append(f"{name}: {exc}")
                        log.warning("llm_race_provider_failed", provider=name, error=str(exc))
                        continue
                    if first_any is None:
                        first_any = result
                    if not validate or _is_valid_action(result):
                        log.info("llm_race_won", provider=name, validated=validate)
                        return result
                    # Valid-but-not-yet: keep waiting for a better one.
                    log.info("llm_race_invalid_response", provider=name)
        finally:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        if first_any is not None:
            log.info("llm_race_fallback_to_first_any")
            return first_any
        raise RuntimeError("All racing LLM providers failed: " + " | ".join(errors))


OpenAIChat = OpenAICompatibleChat


# --------------------------------------------------------------------------- #
# Builder
# --------------------------------------------------------------------------- #
def _provider_order() -> list[str]:
    configured = [
        name.strip().lower()
        for name in settings.llm_fallback_order.split(",")
        if name.strip()
    ]
    supported = {"primary", "gemini", "openrouter", "groq", "ollama"}
    ordered = [name for name in configured if name in supported]
    for name in ("gemini", "openrouter", "groq", "ollama"):
        if name not in ordered:
            ordered.append(name)
    return ordered


def _build_fallback_clients(primary_base_url: str = "") -> list[tuple[str, ChatClient]]:
    """Build optional fallback providers from settings.

    A provider whose base URL matches the primary is skipped, so configuring
    Gemini as the primary doesn't add a duplicate Gemini fallback.
    """
    primary = primary_base_url.rstrip("/")
    specs = {
        "gemini": (
            "gemini",
            settings.gemini_api_key,
            settings.gemini_model,
            settings.gemini_base_url,
            settings.gemini_requests_per_minute,
        ),
        "groq": (
            "groq",
            settings.groq_api_key,
            settings.groq_model,
            settings.groq_base_url,
            settings.groq_requests_per_minute,
        ),
        "openrouter": (
            "openrouter",
            settings.openrouter_api_key,
            settings.openrouter_model,
            settings.openrouter_base_url,
            settings.openrouter_requests_per_minute,
        ),
    }

    clients: list[tuple[str, ChatClient]] = []
    for provider_name in _provider_order():
        if provider_name == "primary":
            continue
        if provider_name == "ollama":
            if settings.llm_local_fallback_enabled:
                clients.append(("ollama", OllamaChat()))
            continue

        name, api_key, model, base_url, rpm = specs[provider_name]
        if not api_key:
            continue
        if base_url.rstrip("/") == primary:
            continue  # already the primary provider
        clients.append(
            (
                name,
                OpenAICompatibleChat(
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                    name=name,
                    requests_per_minute=rpm,
                ),
            )
        )
    return clients


def build_chat_client(
    *,
    provider: str | None = None,
    llm_api_key: str | None = None,
    openai_api_key: str | None = None,
) -> ChatClient:
    selected = (provider or settings.llm_provider).strip().lower()
    if selected == "ollama":
        return OllamaChat()
    if selected in {"openai", "openai-compatible", "compatible", "hosted"}:
        api_key = llm_api_key if llm_api_key is not None else openai_api_key
        if not settings.llm_fallback_enabled:
            return OpenAICompatibleChat(api_key=api_key, name="primary")

        clients: list[tuple[str, ChatClient]] = []
        primary_base_url = ""
        primary_key = api_key if api_key is not None else settings.llm_api_key
        if primary_key:
            primary = OpenAICompatibleChat(api_key=api_key, name="primary")
            primary_base_url = primary.base_url
            clients.append(("primary", primary))

        fallbacks = _build_fallback_clients(primary_base_url=primary_base_url)
        clients.extend(fallbacks)
        if not clients:
            return OpenAICompatibleChat(api_key=api_key, name="primary")

        ordered_clients: list[tuple[str, ChatClient]] = []
        for provider_name in _provider_order():
            ordered_clients.extend((name, client) for name, client in clients if name == provider_name)
        ordered_names = {name for name, _client in ordered_clients}
        ordered_clients.extend(
            (name, client)
            for name, client in clients
            if name not in ordered_names
        )
        if len(ordered_clients) == 1:
            return ordered_clients[0][1]
        if settings.llm_race_enabled:
            # Speed mode: hit every provider in parallel, take the fastest valid
            # answer. Falls back to sequential ordering when racing is off.
            return HedgedChatClient(ordered_clients, grace_s=settings.llm_race_grace_s)
        return FallbackChatClient(ordered_clients)
    raise ValueError(f"Unsupported LLM_PROVIDER: {selected}")
