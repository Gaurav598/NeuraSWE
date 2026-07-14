"""Ollama embeddings client."""

from __future__ import annotations

import asyncio

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.indexer.types import CodeChunk
from app.utils.logger import get_logger

log = get_logger("indexer.embedder")


class Embedder:
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or settings.ollama_embed_model
        self.base_url = (base_url or settings.ollama_url).rstrip("/")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=5))
    async def embed_one(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
            resp = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            resp.raise_for_status()
            data = resp.json()
        embedding = data.get("embedding")
        if not embedding:
            raise RuntimeError("Ollama returned an empty embedding")
        return embedding

    async def embed_chunks(self, chunks: list[CodeChunk], concurrency: int | None = None) -> list[CodeChunk]:
        concurrency = concurrency or settings.ollama_embed_concurrency
        sem = asyncio.Semaphore(concurrency)

        async def _do(chunk: CodeChunk) -> None:
            async with sem:
                chunk.embedding = await self.embed_one(chunk.embed_text())

        await asyncio.gather(*(_do(c) for c in chunks))
        return chunks

    async def embed_query(self, query: str) -> list[float]:
        return await self.embed_one(query)
