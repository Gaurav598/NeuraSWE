"""ChromaDB vector store wrapper. One collection per repository."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from app.config import settings
from app.indexer.types import CodeChunk
from app.utils.logger import get_logger

log = get_logger("indexer.store")


class VectorStore:
    """Thin async wrapper over the (sync) chromadb HttpClient."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            import chromadb  # imported lazily so the package is optional at import time

            parsed = urlparse(settings.chroma_url)
            self._client = chromadb.HttpClient(
                host=parsed.hostname or "localhost",
                port=parsed.port or 8000,
            )
        return self._client

    def _collection_name(self, repo_id: str) -> str:
        return f"repo_{repo_id.replace('-', '')[:48]}"

    async def reset_collection(self, repo_id: str) -> None:
        def _do() -> None:
            client = self._get_client()
            name = self._collection_name(repo_id)
            try:
                client.delete_collection(name)
            except Exception:
                pass
            client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})

        await asyncio.to_thread(_do)

    async def add_chunks(self, repo_id: str, chunks: list[CodeChunk]) -> None:
        embedded = [c for c in chunks if c.embedding is not None]
        if not embedded:
            return

        def _do() -> None:
            client = self._get_client()
            collection = client.get_or_create_collection(
                self._collection_name(repo_id), metadata={"hnsw:space": "cosine"}
            )
            collection.add(
                ids=[c.id for c in embedded],
                embeddings=[c.embedding for c in embedded],
                documents=[c.content for c in embedded],
                metadatas=[
                    {
                        "file_path": c.file_path,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                        "language": c.language,
                    }
                    for c in embedded
                ],
            )

        await asyncio.to_thread(_do)

    async def delete_by_file(self, repo_id: str, file_path: str) -> None:
        def _do() -> None:
            client = self._get_client()
            collection = client.get_or_create_collection(self._collection_name(repo_id))
            collection.delete(where={"file_path": file_path})

        await asyncio.to_thread(_do)

    async def query(
        self, repo_id: str, query_embedding: list[float], n_results: int = 10
    ) -> list[dict[str, Any]]:
        def _do() -> list[dict[str, Any]]:
            client = self._get_client()
            collection = client.get_or_create_collection(self._collection_name(repo_id))
            res = collection.query(query_embeddings=[query_embedding], n_results=n_results)
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            out: list[dict[str, Any]] = []
            for doc, meta, dist in zip(docs, metas, dists):
                out.append(
                    {
                        "content": doc,
                        "file_path": meta.get("file_path"),
                        "start_line": meta.get("start_line"),
                        "end_line": meta.get("end_line"),
                        "language": meta.get("language"),
                        "relevance_score": 1.0 - float(dist) if dist is not None else None,
                    }
                )
            return out

        return await asyncio.to_thread(_do)

    async def count(self, repo_id: str) -> int:
        def _do() -> int:
            client = self._get_client()
            try:
                collection = client.get_collection(self._collection_name(repo_id))
                return collection.count()
            except Exception:
                return 0

        return await asyncio.to_thread(_do)
