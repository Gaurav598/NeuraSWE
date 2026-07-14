"""Code chunking.

Splits source into semantically meaningful chunks. For Python we use the `ast`
module to extract functions/classes precisely. For other languages we use a
brace/heuristic-aware splitter, falling back to a sliding window (100 lines,
20-line overlap) when no structure is detected.
"""

from __future__ import annotations

import ast
import re

from app.indexer.types import CodeChunk

WINDOW_SIZE = 100
WINDOW_OVERLAP = 20
MIN_CHUNK_LINES = 2
MAX_CHUNK_CHARS = 4_000

# Matches function/method/class declarations in C-like and script languages.
DECL_RE = re.compile(
    r"^\s*(?:export\s+)?(?:public\s+|private\s+|protected\s+|static\s+|async\s+)*"
    r"(?:function\s+\w+|def\s+\w+|class\s+\w+|fn\s+\w+|func\s+\w+|"
    r"(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?\(|\w+\s*\([^)]*\)\s*\{)",
)


def chunk_file(file_path: str, content: str, language: str) -> list[CodeChunk]:
    lines = content.split("\n")
    if not content.strip():
        return []

    if language == "python":
        chunks = _chunk_python(file_path, content, lines)
        if chunks:
            return _split_large_chunks(chunks)

    chunks = _chunk_by_declarations(file_path, lines, language)
    if chunks:
        return _split_large_chunks(chunks)

    return _split_large_chunks(_sliding_window(file_path, lines, language))


def _chunk_python(file_path: str, content: str, lines: list[str]) -> list[CodeChunk]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    chunks: list[CodeChunk] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start) or start
            body = "\n".join(lines[start - 1 : end])
            if end - start + 1 >= MIN_CHUNK_LINES:
                chunks.append(
                    CodeChunk(file_path, start, end, body, "python")
                )
    # Capture module-level code outside any def/class (imports, constants).
    if not chunks and lines:
        chunks.append(CodeChunk(file_path, 1, len(lines), content, "python"))
    return chunks


def _chunk_by_declarations(file_path: str, lines: list[str], language: str) -> list[CodeChunk]:
    boundaries = [i for i, line in enumerate(lines) if DECL_RE.match(line)]
    if len(boundaries) < 2:
        return []

    chunks: list[CodeChunk] = []
    boundaries.append(len(lines))
    for idx in range(len(boundaries) - 1):
        start = boundaries[idx]
        end = boundaries[idx + 1]
        body = "\n".join(lines[start:end])
        if end - start >= MIN_CHUNK_LINES:
            chunks.append(CodeChunk(file_path, start + 1, end, body, language))
    return chunks


def _sliding_window(file_path: str, lines: list[str], language: str) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    step = max(1, WINDOW_SIZE - WINDOW_OVERLAP)
    i = 0
    n = len(lines)
    while i < n:
        end = min(i + WINDOW_SIZE, n)
        body = "\n".join(lines[i:end])
        if body.strip():
            chunks.append(CodeChunk(file_path, i + 1, end, body, language))
        if end == n:
            break
        i += step
    return chunks


def _split_large_chunks(chunks: list[CodeChunk]) -> list[CodeChunk]:
    bounded: list[CodeChunk] = []
    for chunk in chunks:
        if len(chunk.content) <= MAX_CHUNK_CHARS:
            bounded.append(chunk)
            continue
        bounded.extend(_split_chunk_by_size(chunk))
    return bounded


def _split_chunk_by_size(chunk: CodeChunk) -> list[CodeChunk]:
    lines = chunk.content.split("\n")
    parts: list[CodeChunk] = []
    part_lines: list[str] = []
    part_start = chunk.start_line
    current_len = 0

    for offset, line in enumerate(lines):
        line_len = len(line) + (1 if part_lines else 0)
        if part_lines and current_len + line_len > MAX_CHUNK_CHARS:
            part_end = part_start + len(part_lines) - 1
            parts.append(
                CodeChunk(
                    chunk.file_path,
                    part_start,
                    part_end,
                    "\n".join(part_lines),
                    chunk.language,
                )
            )
            part_start = chunk.start_line + offset
            part_lines = []
            current_len = 0

        part_lines.append(line)
        current_len += len(line) + (1 if len(part_lines) > 1 else 0)

    if part_lines:
        part_end = part_start + len(part_lines) - 1
        parts.append(
            CodeChunk(
                chunk.file_path,
                part_start,
                part_end,
                "\n".join(part_lines),
                chunk.language,
            )
        )

    return parts
