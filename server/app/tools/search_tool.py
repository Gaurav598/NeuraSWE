"""Semantic code search tool (RAG). Delegates to a search function the runtime
injects via ToolContext.code_search, so the tool stays decoupled from ChromaDB.
"""

from __future__ import annotations

from typing import Any

from app.tools.base import Tool, ToolContext, ToolResult


class SearchCodeTool(Tool):
    name = "search_code"
    description = (
        "Semantic search over the codebase using natural language. Returns the "
        "most relevant code chunks with file paths and line numbers."
    )

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        query = self._require(args, "query")
        if ctx.code_search is None:
            return ToolResult(
                error="Semantic search is unavailable (index not built). Use grep instead."
            )
        try:
            results = await ctx.code_search(query, 10)
        except Exception as exc:  # pragma: no cover - defensive
            return ToolResult(error=f"search_code failed: {exc}. Use grep instead.")
        if not results:
            return ToolResult(output=f"No semantic matches for: {query}. Try grep for exact terms.")

        lines = [f"Found {len(results)} relevant code chunks:"]
        for i, r in enumerate(results, 1):
            score = r.get("relevance_score")
            score_str = f" (relevance {score:.2f})" if isinstance(score, (int, float)) else ""
            lines.append(
                f"\n{i}. {r['file_path']}:{r['start_line']}-{r['end_line']}{score_str}"
            )
            snippet = (r.get("content") or "").strip()
            if len(snippet) > 600:
                snippet = snippet[:600] + "\n  [...]"
            lines.append(snippet)
        return ToolResult(output="\n".join(lines), metadata={"count": len(results)})
