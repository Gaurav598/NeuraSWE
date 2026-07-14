"""Context-window management: token budgeting, observation truncation, and
sliding-window trajectory compaction with LLM summarization of the middle.
"""

from __future__ import annotations

from app.agent.llm import OllamaChat
from app.agent.trajectory import Trajectory
from app.config import settings
from app.utils.logger import get_logger
from app.utils.token_counter import count_tokens, truncate_to_tokens

log = get_logger("agent.context")

# Budget split for an 8K-context model (configurable via settings).
SYSTEM_PROMPT_RESERVE = 3000
RESPONSE_RESERVE = 1000
MAX_OBSERVATION_TOKENS = 1500
KEEP_RECENT_STEPS = 7
KEEP_INITIAL_STEPS = 3


class ContextManager:
    def __init__(self, llm: OllamaChat) -> None:
        self.llm = llm
        self.max_context = settings.agent_max_context_tokens
        self.full_steps = settings.agent_full_trajectory_steps

    @property
    def trajectory_budget(self) -> int:
        return max(1000, self.max_context - SYSTEM_PROMPT_RESERVE - RESPONSE_RESERVE)

    def truncate_observation(self, observation: str) -> str:
        truncated, was = truncate_to_tokens(observation, MAX_OBSERVATION_TOKENS)
        if was:
            truncated += (
                "\n\n[Output truncated. Use read_file with a line range or grep "
                "to inspect specific sections.]"
            )
        return truncated

    async def maybe_compact(self, trajectory: Trajectory) -> None:
        """Compact the trajectory if it exceeds the budget.

        Strategy: keep the first KEEP_INITIAL_STEPS (initial exploration) and the
        last KEEP_RECENT_STEPS verbatim; summarize the middle into one paragraph.
        """
        if len(trajectory) <= self.full_steps:
            return
        if trajectory.token_estimate() <= self.trajectory_budget:
            return

        steps = trajectory.steps
        head = steps[:KEEP_INITIAL_STEPS]
        tail = steps[-KEEP_RECENT_STEPS:]
        middle = steps[KEEP_INITIAL_STEPS : len(steps) - KEEP_RECENT_STEPS]
        if not middle:
            return

        middle_text = "\n\n".join(Trajectory.render_step(s) for s in middle)
        try:
            new_summary = await self.llm.summarize(
                middle_text,
                "Summarize these agent exploration steps into ONE dense paragraph, "
                "preserving file paths, line numbers, function names, the root-cause "
                "hypothesis, and what has been tried.",
            )
        except Exception as exc:  # pragma: no cover - network guard
            log.warning("summarize_failed", error=str(exc))
            new_summary = f"(Compacted {len(middle)} earlier steps.)"

        prefix = trajectory.summary + "\n" if trajectory.summary else ""
        trajectory.summary = (prefix + new_summary).strip()
        trajectory.steps = head + tail
        log.info("trajectory_compacted", kept=len(trajectory.steps), summarized=len(middle))

    def count(self, text: str) -> int:
        return count_tokens(text)
