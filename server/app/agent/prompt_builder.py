"""Constructs the system prompt and the per-turn user prompt."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.agent.trajectory import Trajectory
from app.tools.registry import ToolRegistry

_PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache
def _load(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


class PromptBuilder:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def system_prompt(self) -> str:
        template = _load("system.txt")
        return template.replace("{tool_descriptions}", self.registry.describe())

    def issue_block(self, title: str, body: str, labels: list[str] | None = None) -> str:
        label_str = f"\nLabels: {', '.join(labels)}" if labels else ""
        return f"GITHUB ISSUE\nTitle: {title}{label_str}\n\n{body}".strip()

    def user_prompt(
        self,
        *,
        issue_block: str,
        trajectory: Trajectory,
        baseline: dict | None = None,
    ) -> str:
        sections = [issue_block]
        if baseline:
            sections.append(_render_baseline(baseline))
        rendered = trajectory.render()
        if rendered:
            sections.append("TRAJECTORY SO FAR:\n" + rendered)
        sections.append(
            "What should I do next? Think step by step, then choose ONE tool.\n"
            "Respond with exactly one THOUGHT line and one ACTION line (JSON)."
        )
        return "\n\n".join(sections)


def _render_baseline(baseline: dict) -> str:
    passed = baseline.get("passed", "?")
    failed = baseline.get("failed", "?")
    exit_code = baseline.get("exit_code", "?")
    if baseline.get("success") is True:
        return f"BASELINE TESTS: passing before changes (passed: {passed}, failed: {failed})."
    if baseline.get("success") is False:
        return (
            "BASELINE TESTS: failing/blocked before changes "
            f"(exit code: {exit_code}, passed: {passed}, failed: {failed}). "
            "Do not fix unrelated baseline test infrastructure; keep the issue fix focused."
        )
    return f"BASELINE TESTS: unknown status (passed: {passed}, failed: {failed})."
