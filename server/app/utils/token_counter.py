"""Token counting utilities.

Uses tiktoken's cl100k_base as a reasonable approximation for local code models
(deepseek-coder / qwen) which don't ship a public tokenizer for tiktoken. The
count is an estimate used for context-budget decisions, not billing, so the
approximation is acceptable. Falls back to a chars/4 heuristic if tiktoken is
unavailable.
"""

from __future__ import annotations

from functools import lru_cache

try:
    import tiktoken

    _HAS_TIKTOKEN = True
except Exception:  # pragma: no cover - optional dependency guard
    _HAS_TIKTOKEN = False


@lru_cache
def _encoder():  # type: ignore[no-untyped-def]
    if not _HAS_TIKTOKEN:
        return None
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:  # pragma: no cover
        return None


def count_tokens(text: str) -> int:
    """Estimate the number of tokens in *text*."""
    if not text:
        return 0
    enc = _encoder()
    if enc is None:
        # Heuristic: ~4 characters per token for English/code mix.
        return max(1, len(text) // 4)
    return len(enc.encode(text))


def truncate_to_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """Truncate *text* so it fits within *max_tokens*.

    Returns (possibly_truncated_text, was_truncated).
    """
    if max_tokens <= 0:
        return "", bool(text)
    enc = _encoder()
    if enc is None:
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text, False
        return text[:max_chars], True
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text, False
    return enc.decode(tokens[:max_tokens]), True
