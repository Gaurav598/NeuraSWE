"""Indexing pipeline: clone -> walk -> chunk -> embed -> store.

Also exposes a ``search`` helper used by the agent's search_code tool and an
incremental re-index path for changed files.
"""

from __future__ import annotations

import os
from typing import Any

from app.indexer import cloner
from app.indexer.chunker import chunk_file
from app.indexer.embedder import Embedder
from app.indexer.store import VectorStore
from app.indexer.types import CodeChunk
from app.indexer.walker import detect_language, walk_source_files
from app.utils.logger import get_logger

log = get_logger("indexer.orchestrator")


class IndexOrchestrator:
    def __init__(self, embedder: Embedder | None = None, store: VectorStore | None = None) -> None:
        self.embedder = embedder or Embedder()
        self.store = store or VectorStore()

    async def index_repository(
        self, repo_id: str, clone_url: str, *, local_path: str | None = None
    ) -> dict[str, Any]:
        """Full (re)index. Returns {files, chunks, sha}."""
        path = local_path or await cloner.clone_repo(clone_url)
        sha = await cloner.head_sha(path)
        files = walk_source_files(path)
        log.info("indexing_started", repo_id=repo_id, files=len(files))

        await self.store.reset_collection(repo_id)
        total_chunks = 0
        batch: list[CodeChunk] = []

        for rel in files:
            chunks = self._chunk_path(path, rel)
            batch.extend(chunks)
            if len(batch) >= 64:
                total_chunks += await self._flush(repo_id, batch)
                batch = []
        if batch:
            total_chunks += await self._flush(repo_id, batch)

        log.info("indexing_complete", repo_id=repo_id, chunks=total_chunks, sha=sha[:8])
        return {"files": len(files), "chunks": total_chunks, "sha": sha}

    async def reindex_changed(
        self, repo_id: str, repo_path: str, since_sha: str
    ) -> dict[str, Any]:
        new_sha = await cloner.pull_latest(repo_path)
        changed = await cloner.changed_files(repo_path, since_sha)
        re_chunked = 0
        for rel in changed:
            if detect_language(rel) is None:
                continue
            await self.store.delete_by_file(repo_id, rel)
            if os.path.isfile(os.path.join(repo_path, rel)):
                chunks = self._chunk_path(repo_path, rel)
                re_chunked += await self._flush(repo_id, chunks)
        return {"changed_files": len(changed), "chunks": re_chunked, "sha": new_sha}

    async def search(self, repo_id: str, query: str, n_results: int = 10) -> list[dict[str, Any]]:
        embedding = await self.embedder.embed_query(query)
        return await self.store.query(repo_id, embedding, n_results)

    # ------------------------------------------------------------------ #
    def _chunk_path(self, root: str, rel: str) -> list[CodeChunk]:
        language = detect_language(rel)
        if language is None:
            return []
        full = os.path.join(root, rel)
        try:
            with open(full, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            return []
        return chunk_file(rel, content, language)

    async def _flush(self, repo_id: str, chunks: list[CodeChunk]) -> int:
        if not chunks:
            return 0
        await self.embedder.embed_chunks(chunks)
        await self.store.add_chunks(repo_id, chunks)
        return len(chunks)
