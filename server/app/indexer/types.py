"""Indexer data types."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class CodeChunk:
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str
    embedding: list[float] | None = field(default=None, repr=False)

    @property
    def id(self) -> str:
        raw = f"{self.file_path}:{self.start_line}-{self.end_line}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def embed_text(self) -> str:
        """The text fed to the embedding model — includes location context."""
        return (
            f"File: {self.file_path}\n"
            f"Lines: {self.start_line}-{self.end_line}\n\n"
            f"{self.content}"
        )
