import asyncio

import pytest

from app.config import settings
from app.indexer.embedder import Embedder
from app.indexer.types import CodeChunk


class TrackingEmbedder(Embedder):
    def __init__(self) -> None:
        super().__init__(model="test-model", base_url="http://example.test")
        self.active = 0
        self.max_active = 0

    async def embed_one(self, text: str) -> list[float]:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return [1.0]


@pytest.mark.asyncio
async def test_embed_chunks_uses_configured_default_concurrency(monkeypatch):
    monkeypatch.setattr(settings, "ollama_embed_concurrency", 1, raising=False)
    chunks = [
        CodeChunk(
            file_path=f"src/file_{index}.py",
            start_line=1,
            end_line=2,
            content="print('hello')",
            language="python",
        )
        for index in range(4)
    ]
    embedder = TrackingEmbedder()

    await embedder.embed_chunks(chunks)

    assert embedder.max_active == 1
    assert all(chunk.embedding == [1.0] for chunk in chunks)
